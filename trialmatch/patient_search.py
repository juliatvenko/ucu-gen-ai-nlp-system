"""Cohort search: rank a collection of patient texts for one trial, before any patient is checked.

Rules only, so it can scan a whole collection without model calls. It shortlists; the checker decides.
Settings were chosen on the dev half of the reverse TREC eval (evals/eval_patient_search.py).
"""
import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

from . import lexicon
from .profile import extract_age, extract_sex
from .schemas import Trial

STOP = {
    "of", "the", "and", "or", "with", "in", "on", "a", "an", "to", "for", "at", "by", "as", "is", "was", "be", "are",
    "patients", "patient", "study", "trial", "subjects", "participants", "treatment", "phase", "versus", "vs",
    "who", "has", "have", "had", "not", "no", "from", "this", "that", "will", "after", "before", "than",
}


@dataclass(frozen=True)
class SearchSettings:
    conditions: float = 3.0
    title: float = 1.0
    keywords: float = 1.0
    inclusion: float = 1.0
    concepts: bool = True   # map aliases such as "t2dm" to one concept on both sides
    stem: bool = True       # drop a plural "s"
    k1: float = 1.2
    b: float = 0.75


DEFAULT = SearchSettings()


@dataclass
class Candidate:
    patient_id: str
    score: float
    ruled_out: str = ""     # why age or sex rules this patient out; empty if not


def _stem(token: str) -> str:
    return token[:-1] if len(token) > 4 and token.endswith("s") and not token.endswith("ss") else token


@lru_cache(maxsize=4096)
def _cached_tokens(text: str, settings: "SearchSettings") -> tuple[str, ...]:
    return tuple(tokens(text, settings))


@lru_cache(maxsize=4096)
def _age_sex(text: str) -> tuple[float | None, str | None]:
    return extract_age(text), extract_sex(text)


def tokens(text: str, settings: SearchSettings = DEFAULT) -> list[str]:
    out = [t for t in re.findall(r"[a-z0-9][a-z0-9'-]*", text.lower()) if t not in STOP and len(t) > 1]
    if settings.stem:
        out = [_stem(t) for t in out]
    if settings.concepts:
        out += [f"concept:{c}" for c in lexicon.find_concepts(text)]
    return out


def _inclusion_text(trial: Trial) -> str:
    text = trial.eligibility_text
    cut = re.search(r"exclusion criteria", text, re.I)
    return text[: cut.start()] if cut else text


def trial_query(trial: Trial, settings: SearchSettings = DEFAULT) -> Counter:
    query: Counter = Counter()
    parts = [
        (" ; ".join(trial.conditions), settings.conditions),
        (trial.title, settings.title),
        (" ; ".join(trial.keywords), settings.keywords),
        (_inclusion_text(trial), settings.inclusion),
    ]
    for text, weight in parts:
        if weight:
            for tok in set(tokens(text, settings)):
                query[tok] += weight
    return query


def ruled_out(trial: Trial, age: float | None, sex: str | None) -> str:
    """Same rule as the trial filter: an unknown value never rules a patient out."""
    if age is not None:
        if trial.min_age is not None and age < trial.min_age:
            return f"younger than {trial.min_age:g}"
        if trial.max_age is not None and age > trial.max_age:
            return f"older than {trial.max_age:g}"
    if sex and trial.sex in ("MALE", "FEMALE") and trial.sex.lower() != sex:
        return f"trial is for {trial.sex.lower()} patients"
    return ""


def warm_up(records: dict[str, dict]) -> None:
    for r in records.values():
        _cached_tokens(r["text"], DEFAULT)


def rank_patients(
    trial: Trial,
    patients: dict[str, str],
    known: dict[str, tuple[float | None, str | None]] | None = None,
    settings: SearchSettings = DEFAULT,
) -> list[Candidate]:
    """BM25 of every patient text against the trial. Patients ruled out by age or sex go last, flagged.

    known gives (age, sex) from structured fields when a collection has them; otherwise rules read the text.
    """
    known = known or {}
    ids = list(patients)
    # Cached: a collection is ranked again for every trial, and its texts don't change.
    docs = [_cached_tokens(patients[i], settings) for i in ids]
    query = trial_query(trial, settings)
    n = len(docs)
    avg_len = sum(map(len, docs)) / n if n else 1
    df = Counter(tok for d in docs for tok in set(d))

    out = []
    for pid, doc in zip(ids, docs):
        counts = Counter(doc)
        score = 0.0
        for tok, weight in query.items():
            if tok in counts:
                idf = math.log(1 + (n - df[tok] + 0.5) / (df[tok] + 0.5))
                tf = counts[tok] * (settings.k1 + 1) / (counts[tok] + settings.k1 * (1 - settings.b + settings.b * len(doc) / avg_len))
                score += weight * idf * tf
        age, sex = known.get(pid) or _age_sex(patients[pid])
        out.append(Candidate(pid, round(score, 3), ruled_out(trial, age, sex)))
    # Stable sort: ties keep the collection's order.
    return sorted(out, key=lambda c: (bool(c.ruled_out), -c.score))


def best_sentence(trial: Trial, text: str, settings: SearchSettings = DEFAULT) -> str:
    """The sentence that shares most with the trial's conditions and title, to show why a patient was found."""
    wanted = set(tokens(" ; ".join(trial.conditions) + " " + trial.title, settings))
    sentences = [s.strip() for s in re.split(r"(?<=[.;])\s+", text) if s.strip()]
    if not sentences:
        return ""
    best = max(sentences, key=lambda s: len(wanted & set(tokens(s, settings))))
    return best if wanted & set(tokens(best, settings)) else ""
