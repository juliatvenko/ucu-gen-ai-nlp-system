"""Component 1. Field-level precision and recall: a missed fact and an invented fact are different errors."""
from trialmatch import lexicon
from trialmatch.profile import extract_profile

from .common import load_vignettes, prf


def same(a: str, b: str) -> bool:
    a, b = a.lower(), b.lower()
    if a in b or b in a:
        return True
    return bool(set(lexicon.find_concepts(a)) & set(lexicon.find_concepts(b)))


def score_list(gold: list[str], pred: list[str]) -> tuple[int, int, int, list[str], list[str]]:
    unmatched = list(pred)
    missed = []
    tp = 0
    for g in gold:
        hit = next((p for p in unmatched if same(g, p)), None)
        if hit is None:
            missed.append(g)
        else:
            unmatched.remove(hit)
            tp += 1
    return tp, len(unmatched), len(missed), missed, unmatched


def run(mode: str, split: str, limit: int | None, client) -> dict:
    vignettes = load_vignettes(split)[: limit or None]
    totals = {f: [0, 0, 0] for f in ("diagnoses", "medications", "absent")}
    age = sex = main = 0
    lab_tp = lab_fp = lab_fn = 0
    errors = []
    for v in vignettes:
        gold = v["gold_profile"]
        pred = extract_profile(v["text"], client)
        age += pred.age == gold["age"]
        sex += pred.sex == gold["sex"]
        main += bool(pred.diagnoses) and same(gold["diagnoses"][0], pred.diagnoses[0])
        for field, tally in totals.items():
            # Past events may legitimately land in history, so they aren't scored as invented diagnoses.
            tp, fp, fn, missed, extra = score_list(gold[field], getattr(pred, field))
            tally[0] += tp
            tally[1] += fp
            tally[2] += fn
            if missed or extra:
                errors.append({"id": v["id"], "field": field, "missed": missed, "invented": extra})
        pred_labs = {l.name.lower(): l.value for l in pred.labs}
        for name, value in gold["labs"].items():
            if name in pred_labs and abs(pred_labs[name] - value) < 1e-6:
                lab_tp += 1
            else:
                lab_fn += 1
                errors.append({"id": v["id"], "field": "labs", "missed": name, "got": pred_labs.get(name)})
        lab_fp += sum(1 for name, value in pred_labs.items() if gold["labs"].get(name) != value)
    n = len(vignettes)
    metrics = {f: prf(*t) for f, t in totals.items()}
    metrics["labs_name_and_value"] = prf(lab_tp, lab_fp, lab_fn)
    metrics["age_accuracy"] = round(age / n, 3)
    metrics["sex_accuracy"] = round(sex / n, 3)
    metrics["main_diagnosis_first_accuracy"] = round(main / n, 3)
    metrics["n_patients"] = n
    return {"metrics": metrics, "errors": errors}
