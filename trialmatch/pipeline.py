"""Wires the components. Both modes share evaluate(); only direction and aggregation differ."""
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import aggregate as agg, trace
from .checker import check_criteria, check_rule
from .followup import generate_questions
from .llm import LLMClient, LLMError
from .parsing import parse_criteria
from .profile import extract_profile, extract_rule
from .retrieval import retrieve
from .safety import assess
from .schemas import MatchResult, PatientProfile, Trial, TrialVerdict


def evaluate(trial: Trial, patient_text: str, profile: PatientProfile, client: LLMClient | None = None, fallback: bool = False) -> TrialVerdict:
    """The shared engine: one patient against one trial.

    fallback is for the interface only. Evals keep it off, so an outage can't pass rule results off as model scores.
    """
    criteria = parse_criteria(trial.eligibility_text, trial.nct_id)
    used_rules = False
    try:
        checks = check_criteria(criteria, patient_text, profile, client)
    except LLMError as e:
        if not fallback:
            raise
        trace.log("checker", "code", fallback_to_rules=str(e), trial=trial.nct_id)
        checks = check_rule(criteria, patient_text, profile)
        used_rules = True
    verdict = agg.aggregate(trial, criteria, checks)
    verdict.fallback = used_rules
    return verdict


def _profile_or_rules(patient_text: str, client: LLMClient | None, fallback: bool) -> tuple[PatientProfile, bool]:
    try:
        return extract_profile(patient_text, client), False
    except LLMError as e:
        if not fallback:
            raise
        trace.log("profile", "code", fallback_to_rules=str(e))
        return extract_rule(patient_text), True


def iter_match(patient_text: str, client: LLMClient | None = None, top_k: int = 5, candidates: int = 50, fallback: bool = False) -> Iterator[tuple[str, dict]]:
    """Matcher mode as (event, data) steps, so an interface can show progress. Ends with a "result" event."""
    yield "stage", {"stage": "profile"}
    profile, used_rules = _profile_or_rules(patient_text, client, fallback)
    if used_rules:
        client = None  # the provider just failed after retries, so don't wait through them again for each trial
    safety = assess(patient_text, profile)
    if safety.action != "proceed":
        yield "result", {"result": MatchResult(safety=safety, profile=profile, fallback=used_rules)}
        return
    yield "stage", {"stage": "search", "query": profile.diagnoses[0]}
    query, ranked = retrieve(profile, page_size=candidates)
    if not ranked:
        yield "result", {"result": MatchResult(safety=safety, profile=profile, query=query, fallback=used_rules, note=(
            f"No recruiting trials on ClinicalTrials.gov passed the age and sex filters for “{query}”. "
            "I won't suggest trials for other conditions."
        ))}
        return
    top = ranked[:top_k]
    yield "stage", {"stage": "check", "done": 0, "total": len(top), "query": query, "candidates": len(ranked)}
    verdicts: list[TrialVerdict | None] = [None] * len(top)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(evaluate, t, patient_text, profile, client, fallback): i for i, t in enumerate(top)}
        for done, future in enumerate(as_completed(futures), 1):
            verdict = future.result()
            verdict.fallback = verdict.fallback or used_rules
            verdicts[futures[future]] = verdict  # by index: ties in rank() keep retrieval order
            yield "stage", {"stage": "check", "done": done, "total": len(top), "query": query, "candidates": len(ranked)}
    ordered = agg.rank(verdicts)
    yield "result", {"result": MatchResult(
        safety=safety, profile=profile, query=query, candidates=len(ranked),
        verdicts=ordered, questions=generate_questions(ordered, patient_text=patient_text),
        fallback=used_rules or any(v.fallback for v in ordered),
    )}


def match_patient(patient_text: str, client: LLMClient | None = None, top_k: int = 5, candidates: int = 50) -> MatchResult:
    """Matcher mode: one patient, ranked trials."""
    for event, data in iter_match(patient_text, client, top_k, candidates):
        if event == "result":
            return data["result"]
    raise RuntimeError("iter_match ended without a result")


def iter_cohort(trial: Trial, patients: dict[str, str], client: LLMClient | None = None, fallback: bool = False) -> Iterator[tuple[str, dict]]:
    """Cohort mode as (event, data) steps. Ends with a "result" event."""
    def run(name: str) -> TrialVerdict:
        profile, used_rules = _profile_or_rules(patients[name], client, fallback)
        verdict = evaluate(trial, patients[name], profile, None if used_rules else client, fallback)
        verdict.fallback = verdict.fallback or used_rules
        return verdict

    yield "stage", {"stage": "check", "done": 0, "total": len(patients)}
    verdicts: dict[str, TrialVerdict] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(run, name): name for name in patients}
        for done, future in enumerate(as_completed(futures), 1):
            verdicts[futures[future]] = future.result()
            yield "stage", {"stage": "check", "done": done, "total": len(patients)}
    yield "result", {"result": {name: verdicts[name] for name in patients}}


def screen_cohort(trial: Trial, patients: dict[str, str], client: LLMClient | None = None) -> dict[str, TrialVerdict]:
    """Cohort mode: one trial, a set of patients, same engine."""
    def run(item):
        name, text = item
        return name, evaluate(trial, text, extract_profile(text, client), client)

    with ThreadPoolExecutor(max_workers=4) as pool:
        return dict(pool.map(run, patients.items()))
