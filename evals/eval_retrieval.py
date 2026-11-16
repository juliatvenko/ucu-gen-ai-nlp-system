"""Component 2. Recall for the search step, nDCG for the reranker, violations for the hard filter."""
import random

from trialmatch.profile import extract_profile
from trialmatch.retrieval import get_trials, hard_filter, rerank, retrieve, search_trials, search_within

from . import trec
from .common import load_vignettes, ndcg


def run(mode: str, split: str, limit: int | None, client) -> dict:
    errors = []
    topics, qrels = trec.load_topics(), trec.load_qrels()
    topic_ids = trec.topics_for(split, limit)

    recalls, no_query = [], 0
    pool_recalls, pool_precisions = [], []
    rerank_ndcg, api_ndcg, random_ndcg = [], [], []
    rng = random.Random(3)
    for tid in topic_ids:
        relevant = {n for n, l in qrels[tid].items() if l >= 1}
        profile = extract_profile(topics[tid], client)
        if not profile.diagnoses:
            no_query += 1
            recalls.append(0.0)
            pool_recalls.append(0.0)
            errors.append({"topic": tid, "problem": "no diagnosis extracted", "text": topics[tid][:120]})
        else:
            # All statuses: the judged trials are from a 2021 snapshot and most no longer recruit.
            found = {t.nct_id for t in search_trials(profile.diagnoses[0], status=None, page_size=100)}
            recall = len(found & relevant) / len(relevant) if relevant else 0.0
            recalls.append(recall)
            # Over the judged set only, so a 2026 registry and a depth cutoff can't hide a good query.
            matched = search_within(profile.diagnoses[0], sorted(qrels[tid]))
            reachable = len(matched & relevant) / len(relevant) if relevant else 0.0
            pool_recalls.append(reachable)
            if matched:
                pool_precisions.append(len(matched & relevant) / len(matched))
            if reachable < 0.1:
                errors.append({"topic": tid, "problem": "query reaches under 10% of relevant trials", "query": profile.diagnoses[0]})

        pool = trec.sample_pool(qrels[tid])
        # A merged record comes back under a newer NCT id that has no TREC label, so it isn't scored.
        trials = [t for t in get_trials(list(pool)) if t.nct_id in pool]
        gains = [pool[t.nct_id] for t in trials]
        api_ndcg.append(ndcg(gains))
        shuffled = gains[:]
        rng.shuffle(shuffled)
        random_ndcg.append(ndcg(shuffled))
        rerank_ndcg.append(ndcg([pool[t.nct_id] for t in rerank(profile, trials)]))

    # Live search on vignettes: is the topic right, and did the filter hold?
    vignettes = load_vignettes(split)[: limit or None]
    on_topic = shown = violations = total_results = 0
    for v in vignettes:
        profile = extract_profile(v["text"], client)
        _, ranked = retrieve(profile)
        for t in ranked[:10]:
            shown += 1
            blob = " ".join(t.conditions + [t.title]).lower()
            on_topic += any(term in blob for term in v["condition_terms"])
        total_results += len(ranked)
        violations += len(ranked) - len(hard_filter(profile, ranked))

    mean = lambda xs: round(sum(xs) / len(xs), 3) if xs else 0.0
    return {
        "metrics": {
            "trec_query_recall_over_judged_pool": mean(pool_recalls),
            "trec_query_precision_over_judged_pool": mean(pool_precisions),
            "trec_recall_at_100_of_live_registry": mean(recalls),
            "trec_topics_without_query": no_query,
            "trec_topics": len(topic_ids),
            "pool_ndcg_at_10_rerank": mean(rerank_ndcg),
            "pool_ndcg_at_10_random": mean(random_ndcg),
            "vignette_on_topic_precision_at_10": round(on_topic / shown, 3) if shown else 0.0,
            "vignette_results_shown": shown,
            "hard_filter_violations": violations,
        },
        "errors": errors,
    }
