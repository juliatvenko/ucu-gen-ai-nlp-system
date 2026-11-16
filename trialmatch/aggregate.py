"""Component 5: turn per-criterion statuses into a trial verdict. Plain code, no model."""
from .schemas import OTHER_PERSON, Criterion, CriterionCheck, Trial, TrialVerdict

MAX_UNKNOWN_SHARE = 0.6
RANK = {"likely_eligible": 0, "needs_more_data": 1, "insufficient_data": 2, "not_eligible": 3}


def effect(kind: str, status: str) -> str:
    """Whether a status helps, blocks, or leaves open eligibility."""
    if status == "insufficient":
        return "unknown"
    blocks = (kind == "inclusion" and status == "not_met") or (kind == "exclusion" and status == "met")
    return "blocks" if blocks else "passes"


def _units(criteria: list[Criterion], by_id: dict[str, CriterionCheck]) -> list[tuple[list[str], str]]:
    """One unit per criterion, or per option group. Each unit is (criterion ids, effect)."""
    order: list[str] = []  # criterion ids and group ids, in the trial's order
    single: dict[str, str] = {}
    groups: dict[str, list[tuple[Criterion, str]]] = {}
    for c in criteria:
        if c.screening_only or c.cohort == OTHER_PERSON:
            continue
        check = by_id.get(c.id)
        result = effect(c.kind, check.status if check else "insufficient")
        if c.conditional and result == "blocks":
            result = "unknown"  # it may not apply to this patient, so a person should check
        if not c.group:
            order.append(c.id)
            single[c.id] = result
            continue
        if c.group not in groups:
            order.append(c.group)
            groups[c.group] = []
        groups[c.group].append((c, result))

    out = []
    for key in order:
        if key in single:
            out.append(([key], single[key]))
            continue
        members = groups[key]
        needed = members[0][0].group_needed
        passes = [c.id for c, r in members if r == "passes"]
        blocks = [c.id for c, r in members if r == "blocks"]
        if len(passes) >= needed:
            out.append((passes, "passes"))
        elif len(blocks) > len(members) - needed:
            out.append((blocks, "blocks"))  # too few options are left open to reach the number needed
        else:
            out.append(([c.id for c, r in members if r == "unknown"], "unknown"))
    return out


def _verdict(trial: Trial, criteria: list[Criterion], checks: list[CriterionCheck], part: list[Criterion], cohort: str) -> TrialVerdict:
    units = _units(part, {c.criterion_id: c for c in checks})
    blockers = [i for ids, r in units if r == "blocks" for i in ids]
    missing = [i for ids, r in units if r == "unknown" for i in ids]
    passes = sum(r == "passes" for _, r in units)
    unknown = sum(r == "unknown" for _, r in units)
    checkable = len(units)

    if blockers:
        verdict = "not_eligible"
    elif checkable == 0 or unknown / checkable > MAX_UNKNOWN_SHARE:
        verdict = "insufficient_data"
    elif missing:
        verdict = "needs_more_data"
    else:
        verdict = "likely_eligible"
    score = passes / checkable if checkable else 0.0
    return TrialVerdict(trial=trial, verdict=verdict, score=round(score, 3), criteria=criteria, checks=checks,
                        blockers=blockers, missing=missing, cohort=cohort)


def aggregate(trial: Trial, criteria: list[Criterion], checks: list[CriterionCheck]) -> TrialVerdict:
    """A trial with several participant groups is judged for each, and the patient gets the best fit."""
    cohorts = sorted({c.cohort for c in criteria} - {"", OTHER_PERSON})
    if not cohorts:
        return _verdict(trial, criteria, checks, criteria, "")
    verdicts = [_verdict(trial, criteria, checks, [c for c in criteria if c.cohort in ("", name)], name) for name in cohorts]
    return min(verdicts, key=lambda v: (RANK[v.verdict], -v.score))


def rank(verdicts: list[TrialVerdict]) -> list[TrialVerdict]:
    """Verdict first, then share of criteria confirmed. sorted() keeps retrieval order on ties."""
    return sorted(verdicts, key=lambda v: (RANK[v.verdict], -v.score))
