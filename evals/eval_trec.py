"""End to end on human judgements: does the verdict separate eligible from excluded trials?"""
import random
from concurrent.futures import ThreadPoolExecutor

from trialmatch.aggregate import RANK
from trialmatch.pipeline import evaluate
from trialmatch.profile import extract_profile
from trialmatch.retrieval import get_trials

from . import trec
from .common import ndcg, prf, wilson


def _error(topic: int, text: str, v, gold: str) -> dict:
    """A wrong block lists the criteria that blocked. A missed exclusion lists what was decided."""
    by_id = {c.id: c for c in v.criteria}
    if gold == "eligible":
        checks = [c for c in v.checks if c.criterion_id in v.blockers]
    else:
        checks = [c for c in v.checks if c.status != "insufficient"]
    return {
        "topic": topic, "trial": v.trial.nct_id, "title": v.trial.title, "gold": gold, "verdict": v.verdict,
        "patient": text,
        "criteria": [{"kind": by_id[c.criterion_id].kind, "text": by_id[c.criterion_id].text, "status": c.status,
                      "evidence": c.evidence, "reasoning": c.reasoning, "source": c.source} for c in checks],
    }


def run(mode: str, split: str, limit: int | None, client, per_label: int | None = None) -> dict:
    topics, qrels = trec.load_topics(), trec.load_qrels()
    topic_ids = trec.topics_for(split, limit)
    # Model calls cost quota, so use a smaller pool per topic in LLM mode.
    per_label = per_label or (2 if client else 10)
    tp = fp = fn = tn = 0
    system_ndcg, random_ndcg = [], []
    rng = random.Random(5)
    errors = []
    verdict_counts: dict[str, dict[str, int]] = {}

    for tid in topic_ids:
        text = topics[tid]
        pool = trec.sample_pool(qrels[tid], per_label=per_label)
        # A merged record comes back under a newer NCT id that has no TREC label, so it isn't scored.
        trials = [t for t in get_trials(list(pool)) if t.eligibility_text and t.nct_id in pool]
        profile = extract_profile(text, client)

        # A model failure stops the run instead of counting as a low score. Finished calls stay cached.
        with ThreadPoolExecutor(max_workers=4 if client else 1) as ex:
            verdicts = list(ex.map(lambda t: evaluate(t, text, profile, client), trials))

        for v in verdicts:
            gold = pool[v.trial.nct_id]
            name = {2: "eligible", 1: "excluded", 0: "not_relevant"}[gold]
            verdict_counts.setdefault(name, {}).setdefault(v.verdict, 0)
            verdict_counts[name][v.verdict] += 1
            if gold == 0:
                continue
            open_ = v.verdict != "not_eligible"
            if (gold == 2) != open_:
                errors.append(_error(tid, text, v, name))
            tp += gold == 2 and open_
            fp += gold == 1 and open_
            fn += gold == 2 and not open_
            tn += gold == 1 and not open_

        ranked = sorted(verdicts, key=lambda v: (RANK[v.verdict], -v.score))
        gains = [pool[v.trial.nct_id] for v in ranked]
        system_ndcg.append(ndcg(gains))
        shuffled = gains[:]
        rng.shuffle(shuffled)
        random_ndcg.append(ndcg(shuffled))

    mean = lambda xs: round(sum(xs) / len(xs), 3) if xs else 0.0
    excluded = fp + tn
    return {
        "metrics": {
            "eligible_vs_excluded": prf(tp, fp, fn),
            "excluded_trials_caught": round(tn / excluded, 3) if excluded else None,
            "excluded_trials_caught_95ci": wilson(tn, excluded),
            "precision_if_always_open": round((tp + fn) / (tp + fn + excluded), 3) if tp + fn + excluded else None,
            "ndcg_at_10_system": mean(system_ndcg),
            "ndcg_at_10_random": mean(random_ndcg),
            "verdicts_by_gold_label": verdict_counts,
            "topics": len(topic_ids),
            "per_label_sample": per_label,
        },
        "errors": errors[:50],
    }
