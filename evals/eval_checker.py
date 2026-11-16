"""Component 4, the core. Per-class P/R, evidence quality, and the errors that could harm someone."""
from trialmatch.aggregate import aggregate
from trialmatch.checker import check_criteria, quote_is_verbatim
from trialmatch.followup import topic_and_question
from trialmatch.profile import extract_profile
from trialmatch.schemas import Criterion, CriterionCheck, Trial

from .common import load_vignettes, per_class, wilson

LABELS = ["met", "not_met", "insufficient"]


def criteria_for(v: dict) -> list[Criterion]:
    return [Criterion(id=f"{v['id']}-{i}", kind=c["kind"], text=c["text"]) for i, c in enumerate(v["criteria"])]


def run(mode: str, split: str, limit: int | None, client) -> dict:
    vignettes = load_vignettes(split)[: limit or None]
    pairs, errors = [], []
    quotes = verbatim = evidence_right = evidence_scored = 0
    flips = invented = definitive_gold = gold_insufficient = 0
    resolved = followups = specific = insufficient_total = 0
    verdict_pairs, false_open = [], 0
    gold_blocked = 0
    guard_abstentions = 0

    for v in vignettes:
        profile = extract_profile(v["text"], client)
        criteria = criteria_for(v)
        checks = check_criteria(criteria, v["text"], profile, client)
        for gold, check, criterion in zip(v["criteria"], checks, criteria):
            g, p = gold["status"], check.status
            pairs.append((g, p))
            guard_abstentions += check.source == "guard"
            if g != p:
                errors.append({"id": criterion.id, "criterion": gold["text"], "gold": g, "pred": p, "evidence": check.evidence, "source": check.source})
            if p != "insufficient":
                quotes += 1
                verbatim += quote_is_verbatim(check.evidence, v["text"])
            if g != "insufficient":
                definitive_gold += 1
                flips += p != "insufficient" and p != g
                if g == p:
                    evidence_scored += 1
                    a, b = gold["evidence"].lower(), check.evidence.lower()
                    evidence_right += a in b or b in a
            else:
                gold_insufficient += 1
                invented += p != "insufficient"
                insufficient_total += 1
                specific += not topic_and_question(gold["text"])[0].startswith("text:")

        # Does adding the follow-up answer settle the criterion correctly?
        for gold, criterion in zip(v["criteria"], criteria):
            if "followup" in gold:
                followups += 1
                text = v["text"] + "\n" + gold["followup"]["answer"]
                after = check_criteria([criterion], text, extract_profile(text, client), client)[0]
                resolved += after.status == gold["followup"]["status_after"]

        # Does a criterion error reach the verdict?
        trial = Trial(nct_id=v["id"])
        gold_checks = [CriterionCheck(criterion_id=c.id, status=g["status"]) for c, g in zip(criteria, v["criteria"])]
        gold_verdict = aggregate(trial, criteria, gold_checks).verdict
        pred_verdict = aggregate(trial, criteria, checks).verdict
        verdict_pairs.append((gold_verdict, pred_verdict))
        if gold_verdict == "not_eligible":
            gold_blocked += 1
            false_open += pred_verdict != "not_eligible"

    classes = per_class(pairs, LABELS)
    agree = sum(g == p for g, p in verdict_pairs)
    correct = sum(g == p for g, p in pairs)
    return {
        "metrics": {
            "per_class": classes,
            "macro_f1": classes["macro_f1"],
            "accuracy": round(correct / len(pairs), 3) if pairs else 0.0,
            "accuracy_95ci": wilson(correct, len(pairs)),
            "n_pairs": len(pairs),
            "guard_abstentions": guard_abstentions,
            "evidence_verbatim_rate": round(verbatim / quotes, 3) if quotes else None,
            "evidence_matches_gold_when_correct": round(evidence_right / evidence_scored, 3) if evidence_scored else None,
            "flip_rate_on_definitive": round(flips / definitive_gold, 3) if definitive_gold else 0.0,
            "invented_decision_rate_on_insufficient": round(invented / gold_insufficient, 3) if gold_insufficient else 0.0,
            "followup_resolution_rate": round(resolved / followups, 3) if followups else None,
            "followups": followups,
            "specific_question_rate": round(specific / insufficient_total, 3) if insufficient_total else None,
            "verdict_agreement_with_gold_statuses": round(agree / len(verdict_pairs), 3) if verdict_pairs else 0.0,
            "missed_blocks_rate": round(false_open / gold_blocked, 3) if gold_blocked else None,
            "gold_blocked_patients": gold_blocked,
        },
        "errors": errors,
    }
