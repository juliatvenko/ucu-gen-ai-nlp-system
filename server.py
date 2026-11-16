"""TrialMatch API and web interface. Run with: python -m uvicorn server:app --port 8000

Only transport lives here. Every decision stays in trialmatch/, so evals cover what the interface shows.
"""
import json
import re
import threading
from collections.abc import Callable, Iterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Path as PathParam, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from trialmatch import case_reports, trace
from trialmatch.llm import LLMError, get_client
from trialmatch.pipeline import iter_cohort, iter_match
from trialmatch.parsing import parse_criteria
from trialmatch.patient_search import best_sentence, rank_patients, warm_up
from trialmatch.retrieval import get_trial_details, get_trials, search_for_picker
from trialmatch.schemas import Trial

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "web" / "dist"
MAX_TEXT = 20_000
MAX_PATIENTS = 30
NCT_PATTERN = r"^NCT\d{8}$"

@asynccontextmanager
async def lifespan(_: FastAPI):
    # Reading and indexing the case reports takes about 10 s, so do it before the first search asks.
    threading.Thread(target=lambda: warm_up(case_reports.load()), daemon=True).start()
    yield


app = FastAPI(title="TrialMatch", lifespan=lifespan)


class MatchRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT)


class CohortRequest(BaseModel):
    nct_id: str = Field(pattern=NCT_PATTERN)
    patients: dict[str, str] = Field(min_length=1, max_length=MAX_PATIENTS)


def _dump(value):
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, dict):
        return {k: _dump(v) for k, v in value.items()}
    return value


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(_dump(data))}\n\n"


def _stream(steps: Callable[[], Iterator[tuple[str, dict]]]) -> StreamingResponse:
    """Failures become an error event: headers are already sent, and no partial result may look final."""
    def generate():
        try:
            for event, data in steps():
                yield _sse(event, data)
        except LLMError as e:
            yield _sse("error", {"message": f"The model call failed, so there is no result to show. {e}"})
        except Exception as e:  # network errors from ClinicalTrials.gov
            yield _sse("error", {"message": f"The check could not finish ({type(e).__name__}). Please try again."})

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/api/status")
def status() -> dict:
    client = get_client()
    return {"mode": "model" if client else "offline", "model": client.model if client else None}


@app.get("/api/examples")
def examples() -> list[dict]:
    """Published case reports with their credit. The synthetic vignettes are eval data only, not demo examples."""
    published = ROOT / "data" / "pmc_examples.json"
    return json.loads(published.read_text()) if published.exists() else []


@app.post("/api/match")
def match(request: MatchRequest) -> StreamingResponse:
    return _stream(lambda: iter_match(request.text.strip(), get_client(), fallback=True))


@app.post("/api/cohort")
def cohort(request: CohortRequest) -> StreamingResponse:
    patients = {name: text.strip() for name, text in request.patients.items() if text.strip()}
    if not patients:
        raise HTTPException(422, "Add at least one patient.")

    def steps():
        found = get_trials([request.nct_id])
        if not found:
            yield "error", {"message": f"No trial found for {request.nct_id}."}
            return
        yield "trial", {"trial": found[0]}
        yield from iter_cohort(found[0], patients, get_client(), fallback=True)

    return _stream(steps)


def _brief(trial: Trial) -> dict:
    return {
        "nct_id": trial.nct_id, "title": trial.title, "conditions": trial.conditions, "status": trial.status,
        "min_age": trial.min_age, "max_age": trial.max_age, "sex": trial.sex,
    }


def _registry(call):
    try:
        return call()
    except Exception as e:  # network errors from ClinicalTrials.gov
        raise HTTPException(502, f"ClinicalTrials.gov didn't respond ({type(e).__name__}). Please try again.") from e


@app.get("/api/trials/suggested")
def suggested_trials() -> list[dict]:
    """Hand-picked trials that fit the example patients. Status is live, since trials close."""
    picks = json.loads((ROOT / "data" / "suggested_trials.json").read_text())
    found = {t.nct_id: t for t in _registry(lambda: get_trials([p["nct_id"] for p in picks]))}
    return [{**_brief(found[p["nct_id"]]), "note": p["note"]} for p in picks if p["nct_id"] in found]


@app.get("/api/trials/search")
def search_trials_for_picker(q: str = Query(min_length=2, max_length=100)) -> list[dict]:
    """A condition finds recruiting trials. An NCT ID finds that trial, in any status."""
    text = q.strip().upper()
    if re.fullmatch(NCT_PATTERN, text):
        trial = _registry(lambda: get_trial_details(text))
        return [_brief(trial)] if trial else []
    return [_brief(t) for t in _registry(lambda: search_for_picker(q.strip()))]


@app.get("/api/trials/{nct_id}")
def trial_details(nct_id: str = PathParam(pattern=NCT_PATTERN)) -> dict:
    """The preview: summary plus the criteria exactly as the engine will check them."""
    trial = _registry(lambda: get_trial_details(nct_id))
    if trial is None:
        raise HTTPException(404, f"No trial found for {nct_id}.")
    criteria = parse_criteria(trial.eligibility_text, trial.nct_id)
    return {**_brief(trial), "summary": trial.summary, "criteria": [c.model_dump() for c in criteria]}


@app.get("/api/trials/{nct_id}/case-reports")
def case_report_candidates(nct_id: str = PathParam(pattern=NCT_PATTERN), k: int = Query(10, ge=1, le=MAX_PATIENTS)) -> dict:
    """Cohort search over published case reports: a shortlist to screen, not a verdict."""
    reports = case_reports.load()
    if not reports:
        return {"available": False, "searched": 0, "ruled_out": 0, "candidates": []}
    trial = _registry(lambda: get_trial_details(nct_id))
    if trial is None:
        raise HTTPException(404, f"No trial found for {nct_id}.")
    ranked = rank_patients(trial, {uid: r["text"] for uid, r in reports.items()},
                           known={uid: (r["age"], r["sex"]) for uid, r in reports.items()})
    kept = [c for c in ranked if not c.ruled_out and c.score > 0]
    trace.log("patient_search", "code", nct_id=nct_id, searched=len(ranked), top=[c.patient_id for c in kept[:k]])
    return {
        "available": True,
        "searched": len(ranked),
        "ruled_out": sum(bool(c.ruled_out) for c in ranked),
        "candidates": [{**reports[c.patient_id], "score": c.score, "why": best_sentence(trial, reports[c.patient_id]["text"])}
                       for c in kept[:k]],
    }


@app.get("/api/trace")
def get_trace(limit: int = 100) -> list[dict]:
    return trace.recent(min(limit, 500))


@app.delete("/api/trace")
def clear_trace() -> dict:
    trace.clear()
    return {"cleared": True}


if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def index(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(404)
        # no-cache: a rebuild renames the asset files, and a cached page would point at files that are gone
        return FileResponse(DIST / "index.html", headers={"Cache-Control": "no-cache"})
