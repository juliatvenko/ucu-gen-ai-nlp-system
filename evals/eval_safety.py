"""Component 6a. Whether the system stops when it should. Run-when-it-should-stop is the costly error."""
import json

from trialmatch.profile import extract_profile
from trialmatch.safety import assess

from .common import DATA, per_class

LABELS = ["proceed", "ask_diagnosis", "refuse", "urgent"]


def run(mode: str, split: str, limit: int | None, client) -> dict:
    cases = json.loads((DATA / "safety_cases.json").read_text())[: limit or None]
    pairs, errors = [], []
    for case in cases:
        pred = assess(case["text"], extract_profile(case["text"], client)).action
        pairs.append((case["action"], pred))
        if pred != case["action"]:
            errors.append({"text": case["text"], "gold": case["action"], "pred": pred})
    stop = [p for g, p in pairs if g != "proceed"]
    return {
        "metrics": {
            "per_class": per_class(pairs, LABELS),
            "unsafe_proceed_rate": round(sum(p == "proceed" for p in stop) / len(stop), 3) if stop else 0.0,
            "urgent_recall": per_class(pairs, LABELS)["urgent"]["recall"],
            "n_cases": len(pairs),
        },
        "errors": errors,
    }
