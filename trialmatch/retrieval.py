"""Component 2: fetch candidate trials from ClinicalTrials.gov, drop hard mismatches, rerank."""
import hashlib
import json
import math
import re
import time
from collections import Counter
from pathlib import Path

import httpx

from . import trace
from .schemas import PatientProfile, Trial

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / ".cache" / "ctgov"
API = "https://clinicaltrials.gov/api/v2/studies"
FIELDS = "NCTId,BriefTitle,OfficialTitle,Condition,Keyword,OverallStatus,MinimumAge,MaximumAge,Sex,EligibilityCriteria"
# Separate field lists for the trial picker. FIELDS is part of the cache key, so changing it would refetch
# every trial the evals used, now in today's versions.
PICKER_FIELDS = "NCTId,BriefTitle,OfficialTitle,Condition,OverallStatus,MinimumAge,MaximumAge,Sex"
DETAIL_FIELDS = FIELDS + ",BriefSummary"
STOP = {"of", "the", "and", "or", "with", "in", "a", "an", "to", "for", "on", "disease", "disorder", "patients"}


def _parse_age(value: str | None) -> float | None:
    if not value:
        return None
    m = re.match(r"(\d+(?:\.\d+)?)\s*(year|month|week|day|hour|minute)", value, re.I)
    if not m:
        return None
    per_year = {"year": 1, "month": 12, "week": 52, "day": 365, "hour": 8760, "minute": 525600}
    return float(m.group(1)) / per_year[m.group(2).lower()]


def _to_trial(study: dict) -> Trial:
    p = study["protocolSection"]
    e = p.get("eligibilityModule", {})
    ident = p.get("identificationModule", {})
    return Trial(
        nct_id=ident.get("nctId", ""),
        title=ident.get("briefTitle") or ident.get("officialTitle") or "",
        conditions=p.get("conditionsModule", {}).get("conditions", []),
        keywords=p.get("conditionsModule", {}).get("keywords", []),
        status=p.get("statusModule", {}).get("overallStatus", ""),
        min_age=_parse_age(e.get("minimumAge")),
        max_age=_parse_age(e.get("maximumAge")),
        sex=e.get("sex", "ALL"),
        eligibility_text=e.get("eligibilityCriteria", ""),
        summary=p.get("descriptionModule", {}).get("briefSummary", ""),
    )


def _get(params: dict) -> dict:
    key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
    path = CACHE_DIR / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text())
    for attempt in range(4):
        try:
            r = httpx.get(API, params=params, timeout=40, headers={"User-Agent": "TrialMatch-student-project"})
            if r.status_code == 429 or r.status_code >= 500:
                raise httpx.TransportError(f"HTTP {r.status_code}")
            r.raise_for_status()
            break
        except httpx.TransportError:
            if attempt == 3:
                raise
            time.sleep(2**attempt)
    data = r.json()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return data


def search_trials(condition: str, status: str | None = "RECRUITING", page_size: int = 50) -> list[Trial]:
    params = {"query.cond": condition, "pageSize": page_size, "fields": FIELDS, "format": "json"}
    if status:
        params["filter.overallStatus"] = status
    trials = [_to_trial(s) for s in _get(params).get("studies", [])]
    trace.log("retrieval", "tool", tool="ClinicalTrials.gov API v2", query=condition, status=status, results=len(trials))
    return trials


def get_trials(nct_ids: list[str]) -> list[Trial]:
    trials: list[Trial] = []
    for i in range(0, len(nct_ids), 100):
        chunk = nct_ids[i : i + 100]
        params = {"filter.ids": ",".join(chunk), "pageSize": len(chunk), "fields": FIELDS, "format": "json"}
        trials += [_to_trial(s) for s in _get(params).get("studies", [])]
    return trials


def search_for_picker(text: str, page_size: int = 10) -> list[Trial]:
    """Recruiting trials for a condition, with only what a picker needs to show."""
    params = {"query.cond": text, "filter.overallStatus": "RECRUITING", "pageSize": page_size, "fields": PICKER_FIELDS, "format": "json"}
    return [_to_trial(s) for s in _get(params).get("studies", [])]


def get_trial_details(nct_id: str) -> Trial | None:
    """One trial with its summary, any status, for the picker's preview."""
    params = {"filter.ids": nct_id, "pageSize": 1, "fields": DETAIL_FIELDS, "format": "json"}
    studies = _get(params).get("studies", [])
    return _to_trial(studies[0]) if studies else None


def search_within(condition: str, nct_ids: list[str]) -> set[str]:
    """Which of these trials does a condition query match? Used by evals to remove depth bias."""
    found: set[str] = set()
    for i in range(0, len(nct_ids), 100):
        chunk = nct_ids[i : i + 100]
        params = {"query.cond": condition, "filter.ids": ",".join(chunk), "pageSize": len(chunk), "fields": "NCTId", "format": "json"}
        found |= {s["protocolSection"]["identificationModule"]["nctId"] for s in _get(params).get("studies", [])}
    return found


def hard_filter(profile: PatientProfile, trials: list[Trial]) -> list[Trial]:
    """Drop only what the structured fields rule out. Unknown patient values never drop a trial."""
    kept = []
    for t in trials:
        if profile.age is not None:
            if t.min_age is not None and profile.age < t.min_age:
                continue
            if t.max_age is not None and profile.age > t.max_age:
                continue
        if profile.sex and t.sex in ("MALE", "FEMALE") and t.sex.lower() != profile.sex:
            continue
        kept.append(t)
    return kept


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9][a-z0-9'-]+", text.lower()) if t not in STOP]


def _trial_doc(t: Trial) -> list[str]:
    # Conditions and title count double: they say what the trial is about.
    return _tokens(" ".join(t.conditions) * 2 + " " + t.title * 2 + " " + " ".join(t.keywords))


def rerank(profile: PatientProfile, trials: list[Trial], k1: float = 1.5, b: float = 0.75) -> list[Trial]:
    """BM25 over title, conditions, and keywords. The main diagnosis counts most."""
    query = Counter()
    for i, diagnosis in enumerate(profile.diagnoses):
        for tok in _tokens(diagnosis):
            query[tok] += 3 if i == 0 else 1
    for extra in profile.history + profile.medications:
        for tok in _tokens(extra):
            query[tok] += 0.5
    docs = [_trial_doc(t) for t in trials]
    if not docs:
        return []
    avg_len = sum(map(len, docs)) / len(docs) or 1
    df = Counter(tok for d in docs for tok in set(d))

    def score(doc: list[str]) -> float:
        counts = Counter(doc)
        total = 0.0
        for tok, weight in query.items():
            if tok in counts:
                idf = math.log(1 + (len(docs) - df[tok] + 0.5) / (df[tok] + 0.5))
                tf = counts[tok] * (k1 + 1) / (counts[tok] + k1 * (1 - b + b * len(doc) / avg_len))
                total += weight * idf * tf
        return total

    # sorted() is stable, so ties keep the API's relevance order.
    return [t for _, t in sorted(zip(map(score, docs), trials), key=lambda x: -x[0])]


# A query must name a condition: never only a place in the body or a generic word.
NOT_A_CONDITION = {
    "the", "a", "an", "of", "in", "on", "left", "right", "upper", "lower", "bilateral", "leg", "legs", "arm", "arms",
    "lesion", "lesions", "mass", "masses", "pain", "disease", "syndrome", "infection", "disorder", "history",
}
CLAUSE = re.compile(r"\s+(?:of|in|on|with|involving|due to|secondary to|extending|affecting)\s+", re.I)


def query_candidates(diagnoses: list[str]) -> list[str]:
    """Most specific first: every diagnosis as written, then the part before a clause, then shorter forms."""
    full = [d.strip() for d in diagnoses if d.strip()]
    heads = [CLAUSE.split(d, maxsplit=1)[0] for d in full]
    shorter = []
    for head in heads:
        words = head.split()
        for i in range(1, len(words)):
            rest = words[i:]
            if rest[0].lower() not in NOT_A_CONDITION and not all(w.lower() in NOT_A_CONDITION for w in rest):
                shorter.append(" ".join(rest))
    candidates = []
    for q in full + heads + shorter:
        if q.lower() not in {c.lower() for c in candidates} and not all(w.lower() in NOT_A_CONDITION for w in q.split()):
            candidates.append(q)
    return candidates


def retrieve(profile: PatientProfile, status: str | None = "RECRUITING", page_size: int = 50) -> tuple[str, list[Trial]]:
    """Return the query used and the filtered, reranked candidates."""
    query, trials = "", []
    for query in query_candidates(profile.diagnoses):
        trials = search_trials(query, status, page_size)
        if trials:
            break
    filtered = hard_filter(profile, trials)
    ranked = rerank(profile, filtered)
    trace.log("retrieval", "code", query=query, fetched=len(trials), after_filter=len(filtered), top=[t.nct_id for t in ranked[:10]])
    return query, ranked
