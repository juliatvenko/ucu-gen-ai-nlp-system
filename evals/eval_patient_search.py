"""Cohort search, scored on TREC in reverse: fix a trial, rank all 75 TREC patients, see where the eligible ones land.

The TREC labels say which patients fit which trial (2 eligible, 1 excluded, 0 not relevant). Unjudged
patient-trial pairs count as not relevant, as is usual for TREC pools. Trials are split into dev and test by a
hash of the NCT ID, so settings are chosen on dev only. Rules only: no model calls.
"""
import hashlib
import random
from collections import defaultdict

from trialmatch.patient_search import DEFAULT, SearchSettings, rank_patients
from trialmatch.retrieval import get_trials

from . import trec
from .common import ndcg, wilson

PER_SPLIT = 300
K = 10

# Tried on dev only. The chosen one is DEFAULT in trialmatch/patient_search.py.
VARIANTS = {
    "conditions only": SearchSettings(title=0, keywords=0, inclusion=0, concepts=False, stem=False),
    "conditions + title": SearchSettings(keywords=0, inclusion=0, concepts=False, stem=False),
    "+ keywords": SearchSettings(inclusion=0, concepts=False, stem=False),
    "+ keywords, stemming": SearchSettings(inclusion=0, concepts=False),
    "+ keywords, stemming, concepts": SearchSettings(inclusion=0),
    "+ inclusion criteria (0.3)": SearchSettings(inclusion=0.3),
    "+ inclusion criteria (1.0)": SearchSettings(inclusion=1.0),
    "+ inclusion criteria (2.0)": SearchSettings(inclusion=2.0),
    "+ inclusion criteria (1.0), conditions 2": SearchSettings(inclusion=1.0, conditions=2.0),
    "no age/sex filter": None,  # filled in below: DEFAULT without the filter
}


def split_of(nct_id: str) -> str:
    return "dev" if int(hashlib.sha256(nct_id.encode()).hexdigest(), 16) % 2 == 0 else "test"


def labels_by_trial() -> dict[str, dict[int, int]]:
    by: dict[str, dict[int, int]] = defaultdict(dict)
    for topic, judged in trec.load_qrels().items():
        for nct, label in judged.items():
            by[nct][topic] = label
    return by


def sample_trials(split: str, limit: int | None) -> list[str]:
    """Trials with at least one eligible patient, so every trial has something to find."""
    ids = sorted(n for n, d in labels_by_trial().items() if 2 in d.values() and split_of(n) == split)
    random.Random(11).shuffle(ids)
    return ids[: limit or PER_SPLIT]


def score(trials, labels, topics, settings: SearchSettings, use_filter: bool = True) -> dict:
    ndcgs, recalls, rr = [], [], []
    hits = filtered_eligible = eligible_total = 0
    for t in trials:
        gold = labels[t.nct_id]
        ranked = rank_patients(t, topics, settings=settings)
        if not use_filter:
            ranked = sorted(ranked, key=lambda c: -c.score)
        order = [gold.get(c.patient_id, 0) for c in ranked]
        eligible = sum(g == 2 for g in order)
        ndcgs.append(ndcg(order, K))
        recalls.append(sum(g == 2 for g in order[:K]) / eligible)
        hits += any(g == 2 for g in order[:K])
        rr.append(1 / (order.index(2) + 1))
        eligible_total += eligible
        filtered_eligible += sum(1 for c in ranked if c.ruled_out and gold.get(c.patient_id) == 2)
    mean = lambda xs: round(sum(xs) / len(xs), 3) if xs else 0.0
    return {
        "ndcg_at_10": mean(ndcgs),
        "eligible_recall_at_10": mean(recalls),
        "trials_with_eligible_in_top_10": round(hits / len(trials), 3),
        "trials_with_eligible_in_top_10_95ci": wilson(hits, len(trials)),
        "mrr_first_eligible": mean(rr),
        "eligible_patients_ruled_out_by_filter": filtered_eligible,
        "eligible_patients": eligible_total,
    }


def random_baseline(trials, labels, topics, seeds: int = 20) -> dict:
    rng = random.Random(9)
    ndcgs, recalls, hits = [], [], []
    ids = list(topics)
    for t in trials:
        gold = labels[t.nct_id]
        for _ in range(seeds):
            rng.shuffle(ids)
            order = [gold.get(i, 0) for i in ids]
            ndcgs.append(ndcg(order, K))
            recalls.append(sum(g == 2 for g in order[:K]) / sum(g == 2 for g in order))
            hits.append(any(g == 2 for g in order[:K]))
    mean = lambda xs: round(sum(xs) / len(xs), 3)
    return {"ndcg_at_10": mean(ndcgs), "eligible_recall_at_10": mean(recalls), "trials_with_eligible_in_top_10": mean(hits)}


def run(mode: str, split: str, limit: int | None, client) -> dict:
    # Rules only, so offline and LLM mode give the same result; the mode argument is kept for run_all.
    labels = labels_by_trial()
    topics = {str(k): v for k, v in trec.load_topics().items()}
    labels = {n: {str(k): v for k, v in d.items()} for n, d in labels.items()}
    wanted = sample_trials(split, limit)
    # A merged record comes back under a newer NCT ID that has no TREC label, so it isn't scored.
    trials = [t for t in get_trials(wanted) if t.nct_id in labels]

    metrics = {
        "system": score(trials, labels, topics, DEFAULT),
        "conditions_only": score(trials, labels, topics, VARIANTS["conditions only"]),
        "random": random_baseline(trials, labels, topics),
        "trials": len(trials),
        "patients_ranked_per_trial": len(topics),
    }
    if split == "dev":
        metrics["variants_dev_only"] = {
            name: {k: v for k, v in (score(trials, labels, topics, DEFAULT, use_filter=False) if s is None
                                     else score(trials, labels, topics, s)).items() if not k.endswith("95ci")}
            for name, s in VARIANTS.items()
        }

    errors = []
    for t in trials:
        ranked = rank_patients(t, topics)
        gold = labels[t.nct_id]
        first = next(i for i, c in enumerate(ranked) if gold.get(c.patient_id) == 2)
        if first >= K:
            errors.append({"trial": t.nct_id, "conditions": t.conditions[:3], "first_eligible_rank": first + 1,
                           "ruled_out": next(c.ruled_out for c in ranked if gold.get(c.patient_id) == 2)})
    return {"metrics": metrics, "errors": errors[:50]}
