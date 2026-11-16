"""Component 5. Plain code, so the logic is verified exhaustively. Real-world effect is measured in eval_trec."""
from itertools import product

from trialmatch.aggregate import aggregate, effect
from trialmatch.schemas import Criterion, CriterionCheck, Trial

STATUSES = ["met", "not_met", "insufficient"]


def expected(kinds, statuses) -> str:
    blocked = any((k == "inclusion" and s == "not_met") or (k == "exclusion" and s == "met") for k, s in zip(kinds, statuses))
    if blocked:
        return "not_eligible"
    unknown = statuses.count("insufficient")
    if unknown / len(statuses) > 0.6:
        return "insufficient_data"
    return "needs_more_data" if unknown else "likely_eligible"


def run(mode: str, split: str, limit: int | None, client) -> dict:
    total = correct = 0
    errors = []
    # Every combination of up to 4 criteria: 2 kinds and 3 statuses each.
    for n in range(1, 5):
        for kinds in product(["inclusion", "exclusion"], repeat=n):
            for statuses in product(STATUSES, repeat=n):
                criteria = [Criterion(id=str(i), kind=k, text="x") for i, k in enumerate(kinds)]
                checks = [CriterionCheck(criterion_id=str(i), status=s) for i, s in enumerate(statuses)]
                got = aggregate(Trial(nct_id="X"), criteria, checks).verdict
                want = expected(kinds, list(statuses))
                total += 1
                correct += got == want
                if got != want:
                    errors.append({"kinds": kinds, "statuses": statuses, "got": got, "want": want})
    screening = Criterion(id="s", kind="inclusion", text="consent", screening_only=True)
    screening_ok = aggregate(Trial(nct_id="X"), [screening], [CriterionCheck(criterion_id="s", status="insufficient")]).missing == []
    return {
        "metrics": {
            "truth_table_correct": correct,
            "truth_table_total": total,
            "screening_only_not_counted_missing": screening_ok,
            "effect_exclusion_met_blocks": effect("exclusion", "met") == "blocks",
        },
        "errors": errors,
    }
