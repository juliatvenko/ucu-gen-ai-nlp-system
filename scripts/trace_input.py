"""Print one input's path through every component. For the report walkthrough and the video."""
import argparse
import json
from pathlib import Path

from trialmatch.checker import check_criteria
from trialmatch.aggregate import aggregate
from trialmatch.followup import generate_questions
from trialmatch.llm import get_client
from trialmatch.parsing import parse_criteria
from trialmatch.profile import extract_profile
from trialmatch.retrieval import get_trials, retrieve
from trialmatch.safety import assess

ROOT = Path(__file__).resolve().parent.parent


def step(number: int, name: str, kind: str) -> None:
    print(f"\n=== {number}. {name} [{kind}]")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vignette", default="d01")
    ap.add_argument("--text")
    ap.add_argument("--nct")
    args = ap.parse_args()
    vignettes = json.loads((ROOT / "data" / "vignettes.json").read_text())
    text = args.text or next(v["text"] for v in vignettes if v["id"] == args.vignette)
    client = get_client()
    model_kind = f"model call: {client.label}" if client else "plain code, offline mode"
    print("INPUT:", text)

    step(1, "Profile extraction", model_kind)
    profile = extract_profile(text, client)
    print(profile.model_dump_json(indent=1, exclude_defaults=True))

    step(2, "Safety gate", "plain code")
    safety = assess(text, profile)
    print(safety.action, safety.message)
    if safety.action != "proceed":
        return

    step(3, "Retrieval", "external tool: ClinicalTrials.gov, then plain code")
    if args.nct:
        ranked = get_trials([args.nct])
        print("fixed trial", args.nct)
    else:
        query, ranked = retrieve(profile)
        print("query:", query, "| candidates after filters:", len(ranked))
        for t in ranked[:5]:
            print(" ", t.nct_id, t.title[:90])
    if not ranked:
        print("No trials found: the system stops here and says so.")
        return
    trial = ranked[0]

    step(4, f"Criteria parsing of {trial.nct_id}", "plain code")
    criteria = parse_criteria(trial.eligibility_text, trial.nct_id)
    print(len(criteria), "criteria;", sum(c.screening_only for c in criteria), "are screening-only")
    for c in criteria[:8]:
        print(f"  [{c.kind[:3]}] {c.text[:100]}")

    step(5, "Criterion checks", f"numeric rules in code, the rest: {model_kind}")
    checks = check_criteria(criteria, text, profile, client)
    by_id = {c.id: c for c in criteria}
    for check in checks[:12]:
        print(f"  {check.status:<12} {by_id[check.criterion_id].text[:70]!r}  quote={check.evidence[:60]!r} via {check.source}")

    step(6, "Aggregation", "plain code")
    verdict = aggregate(trial, criteria, checks)
    print(verdict.verdict, "| score", verdict.score, "| blockers", len(verdict.blockers), "| missing", len(verdict.missing))

    step(7, "Follow-up questions", "plain code")
    for q in generate_questions([verdict], patient_text=text):
        print(" -", q)


if __name__ == "__main__":
    main()
