"""JSONL trace of pipeline steps, for debugging and for showing LLM calls in the demo."""
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRACE_DIR = ROOT / "traces"

_events: list[dict] = []


def log(component: str, kind: str, **payload) -> None:
    """kind is one of: code, model, tool."""
    event = {"ts": round(time.time(), 3), "component": component, "kind": kind, **payload}
    _events.append(event)
    TRACE_DIR.mkdir(exist_ok=True)
    with open(TRACE_DIR / f"{time.strftime('%Y%m%d')}.jsonl", "a") as f:
        f.write(json.dumps(event, default=str) + "\n")


def recent(n: int = 200) -> list[dict]:
    return _events[-n:]


def clear() -> None:
    _events.clear()
