"""Single gateway for model calls: provider choice, JSON validation, disk cache, tracing."""
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from . import trace

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / ".cache" / "llm"
ANTHROPIC_DEFAULT = "claude-opus-5-5"
OPENROUTER_DEFAULT = "openrouter/free"
OPENROUTER_URL = "https://openrouter.ai/api/v1"
FALLBACK_MODELS = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-1")


class LLMError(RuntimeError):
    pass


class LLMInvalidOutput(LLMError):
    """The model answered, but not with valid JSON. Quota and network failures stay plain LLMError."""


def parse_json(text: str) -> dict:
    """Accept bare JSON or JSON wrapped in fences or prose."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("no JSON object in response")
        text = text[start : end + 1]
    return json.loads(text)


class LLMClient:
    def __init__(self, provider: str, model: str, api_key: str, base_url: str | None = None, use_cache: bool = True):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.use_cache = use_cache
        self.calls = 0
        self._anthropic = None
        rpm = float(os.getenv("LLM_RPM") or 0)
        self._min_interval = 60 / rpm if rpm else 0.0
        self._next_slot = 0.0
        self._lock = threading.Lock()

    def _wait_for_slot(self) -> None:
        """Space calls out across threads, so a per-minute limit isn't hit in the first place."""
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next_slot)
            self._next_slot = slot + self._min_interval
        if slot > now:
            time.sleep(slot - now)

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}"

    def _call_anthropic(self, system: str, user: str) -> tuple[str, dict]:
        import anthropic

        if self._anthropic is None:
            self._anthropic = anthropic.Anthropic(api_key=self.api_key)
        kwargs = {}
        if self.model in FALLBACK_MODELS:
            kwargs = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
        resp = self._anthropic.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            output_config={"effort": "medium"},
            system=system,
            messages=[{"role": "user", "content": user}],
            **kwargs,
        )
        if resp.stop_reason == "refusal":
            raise LLMError("model declined the request")
        if resp.stop_reason == "max_tokens":
            raise LLMError("response cut off at max_tokens")
        text = "".join(b.text for b in resp.content if b.type == "text")
        return text, {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}

    def _call_openai_compatible(self, system: str, user: str) -> tuple[str, dict]:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
        }
        if self.provider == "openrouter" or "generativelanguage.googleapis.com" in (self.base_url or ""):
            body["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self.api_key}"}
        for attempt in range(5):
            try:
                r = httpx.post(f"{self.base_url}/chat/completions", json=body, headers=headers, timeout=180)
            except httpx.TransportError as e:
                if attempt == 4:
                    raise LLMError(f"connection failed: {e}") from e
                time.sleep(2**attempt)
                continue
            if r.status_code == 429 and re.search(r"per-?day", r.text, re.I):
                raise LLMError("Daily free-model limit reached. It resets once a day. Finished calls are cached and won't be repeated.")
            if r.status_code == 429 or r.status_code >= 500:
                if attempt == 4:
                    raise LLMError("The model provider is overloaded right now. Please try again in a few minutes. Finished calls are cached and won't be repeated.")
                time.sleep(2 ** (attempt + 1))
                continue
            if r.status_code != 200:
                raise LLMError(f"HTTP {r.status_code}: {r.text[:300]}")
            data = r.json()
            if "error" in data:
                raise LLMError(str(data["error"])[:300])
            return data["choices"][0]["message"]["content"] or "", data.get("usage", {})
        raise LLMError("unreachable")

    def _raw(self, system: str, user: str) -> tuple[str, dict]:
        self.calls += 1
        self._wait_for_slot()
        if self.provider == "anthropic":
            return self._call_anthropic(system, user)
        return self._call_openai_compatible(system, user)

    def complete_json(self, component: str, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        """Return a validated object. One repair attempt on bad JSON, then LLMError."""
        system_full = (
            f"{system}\n\nReturn only one JSON object matching this JSON schema, with no other text:\n"
            f"{json.dumps(schema.model_json_schema())}"
        )
        key = hashlib.sha256(f"{self.model}\0{system_full}\0{user}".encode()).hexdigest()
        path = CACHE_DIR / f"{key}.json"
        if self.use_cache and path.exists():
            result = schema.model_validate_json(path.read_text())
            trace.log(component, "model", model=self.label, cached=True, output=result.model_dump())
            return result

        started = time.time()
        text, usage = self._raw(system_full, user)
        try:
            result = schema.model_validate(parse_json(text))
        except (ValueError, ValidationError) as first_error:
            # At temperature 0 the same prompt repeats the same mistake, so show the bad reply.
            repair = f"{user}\n\nYour previous reply was invalid ({first_error}):\n{text}\n\nReply with the corrected JSON object only."
            text, usage = self._raw(system_full, repair)
            try:
                result = schema.model_validate(parse_json(text))
            except (ValueError, ValidationError) as e:
                trace.log(component, "model", model=self.label, error=str(e), raw=text[:500])
                raise LLMInvalidOutput(f"invalid JSON from model: {e}") from e

        trace.log(
            component, "model", model=self.label, cached=False, latency_s=round(time.time() - started, 2),
            usage=usage, input=user[:2000], output=result.model_dump(),
        )
        if self.use_cache:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(result.model_dump_json())
        return result


def get_client(use_cache: bool = True) -> LLMClient | None:
    """Return a client from the environment, or None for offline mode."""
    # override: a running app must see edits to .env, not a mix of old and new values
    load_dotenv(ROOT / ".env", override=True)
    model = os.getenv("LLM_MODEL")
    if os.getenv("LLM_BASE_URL") and os.getenv("LLM_API_KEY"):
        if not model:
            raise LLMError("LLM_MODEL is required with LLM_BASE_URL")
        return LLMClient("openai-compatible", model, os.environ["LLM_API_KEY"], os.environ["LLM_BASE_URL"], use_cache)
    if os.getenv("ANTHROPIC_API_KEY"):
        return LLMClient("anthropic", model or ANTHROPIC_DEFAULT, os.environ["ANTHROPIC_API_KEY"], use_cache=use_cache)
    if os.getenv("OPENROUTER_API_KEY"):
        return LLMClient("openrouter", model or OPENROUTER_DEFAULT, os.environ["OPENROUTER_API_KEY"], OPENROUTER_URL, use_cache)
    return None
