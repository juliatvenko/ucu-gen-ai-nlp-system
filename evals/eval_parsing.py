"""Component 3. Segmentation, entity F1 against Chia (strict and relaxed), screening-only detection."""
import json
import re
from collections import defaultdict

from scripts.chia import CHIA, iter_files, read_raw, trial_split
from trialmatch.parsing import CORE_TYPES, extract_entities_llm, extract_entities_rule, is_screening_only, load_gazetteer, parse_criteria

from .common import DATA, prf

STYLES = {"star": "* {}", "dash": "- {}", "plain": "{}"}
SCREENING_TYPES = {"Informed_consent", "Subjective_judgement"}
LLM_BATCH = 15


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def eval_segmentation() -> tuple[dict, list]:
    errors, tp, fp, fn = [], 0, 0, 0
    for case in json.loads((DATA / "parsing_gold.json").read_text()):
        pred = [(c.kind, _norm(c.text)) for c in parse_criteria(case["text"])]
        gold = [(k, _norm(t)) for k, t in case["expected"]]
        tp += len(set(pred) & set(gold))
        fp += len(set(pred) - set(gold))
        fn += len(set(gold) - set(pred))
        if set(pred) != set(gold):
            errors.append({"case": case["id"], "extra": sorted(set(pred) - set(gold)), "missed": sorted(set(gold) - set(pred))})
    return prf(tp, fp, fn), errors


def eval_chia_roundtrip(trials: list[str]) -> dict:
    """Rebuild CT.gov-style text from Chia's split files in several bullet styles and check recovery."""
    out = {}
    pieces = defaultdict(dict)
    for trial in trials:
        for kind in ("inc", "exc"):
            path = CHIA / f"{trial}_{kind}.txt"
            if path.exists():
                pieces[trial][kind] = [l.strip() for l in read_raw(path).splitlines() if l.strip()]
    for style, fmt in STYLES.items():
        tp = fp = fn = 0
        for parts in pieces.values():
            text = "Inclusion Criteria:\n" + "\n".join(fmt.format(l) for l in parts.get("inc", []))
            text += "\nExclusion Criteria:\n" + "\n".join(fmt.format(l) for l in parts.get("exc", []))
            gold = {("inclusion", _norm(l)) for l in parts.get("inc", [])} | {("exclusion", _norm(l)) for l in parts.get("exc", [])}
            pred = {(c.kind, _norm(c.text)) for c in parse_criteria(text)}
            # Bullet stripping and unescaping can alter a line, so compare on word characters only.
            squash = lambda items: {(k, re.sub(r"\W+", "", t)) for k, t in items}
            gold, pred = squash(gold), squash(pred)
            tp += len(gold & pred)
            fp += len(pred - gold)
            fn += len(gold - pred)
        out[style] = prf(tp, fp, fn)
    return out


def _split_lines(text: str) -> list[tuple[int, str]]:
    offset, lines = 0, []
    for line in text.split("\n"):
        if line.strip():
            lines.append((offset, line))
        offset += len(line) + 1
    return lines


def eval_entities(trials: list[str], client, limit_lines: int | None) -> dict:
    gazetteer = load_gazetteer()
    strict = {t: [0, 0, 0] for t in CORE_TYPES}
    relaxed = {t: [0, 0, 0] for t in CORE_TYPES}
    lines_scored = 0

    def score(gold: list, pred: list) -> None:
        for etype in CORE_TYPES:
            g = {(s, e) for t, s, e in gold if t == etype}
            p = {(s, e) for t, s, e in pred if t == etype}
            strict[etype][0] += len(g & p)
            strict[etype][1] += len(p - g)
            strict[etype][2] += len(g - p)
            overlap = lambda a, b: a[0] < b[1] and b[0] < a[1]
            relaxed[etype][0] += sum(any(overlap(x, y) for y in p) for x in g)
            relaxed[etype][1] += sum(not any(overlap(x, y) for y in g) for x in p)
            relaxed[etype][2] += sum(not any(overlap(x, y) for y in p) for x in g)

    for _, text, entities in iter_files(trials):
        lines = _split_lines(text)
        if limit_lines is not None:
            lines = lines[: max(0, limit_lines - lines_scored)]
            if not lines:
                break
        lines_scored += len(lines)
        predictions: list[tuple[str, int, int]] = []
        if client is None:
            for offset, line in lines:
                predictions += [(e.type, offset + e.start, offset + e.end) for e in extract_entities_rule(line, gazetteer)]
        else:
            for i in range(0, len(lines), LLM_BATCH):
                batch = lines[i : i + LLM_BATCH]
                for (offset, _), ents in zip(batch, extract_entities_llm([l for _, l in batch], client)):
                    predictions += [(e.type, offset + e.start, offset + e.end) for e in ents]
        covered = [(o, o + len(l)) for o, l in lines]
        gold = [x for x in entities if any(a <= x[1] < b for a, b in covered)]
        score(gold, predictions)

    def summarise(tally: dict) -> dict:
        out = {t: prf(*v) for t, v in tally.items()}
        out["micro"] = prf(*[sum(v[i] for v in tally.values()) for i in range(3)])
        return out

    return {"strict": summarise(strict), "relaxed": summarise(relaxed), "lines_scored": lines_scored}


def eval_screening(trials: list[str]) -> dict:
    """A line is screening-only if Chia marks an informed-consent or subjective-judgement span in it."""
    tp = fp = fn = 0
    for trial in trials:
        for kind in ("inc", "exc"):
            stem = CHIA / f"{trial}_{kind}"
            if not stem.with_suffix(".ann").exists():
                continue
            text = read_raw(stem.with_suffix(".txt"))
            spans = []
            for line in read_raw(stem.with_suffix(".ann")).splitlines():
                parts = line.split("\t")
                if line.startswith("T") and len(parts) >= 2 and parts[1].split()[0] in SCREENING_TYPES:
                    spans.append(int(parts[1].replace(";", " ").split()[1]))
            for offset, l in _split_lines(text):
                gold = any(offset <= s < offset + len(l) for s in spans)
                pred = is_screening_only(l)
                tp += gold and pred
                fp += pred and not gold
                fn += gold and not pred
    return prf(tp, fp, fn)


def run(mode: str, split: str, limit: int | None, client) -> dict:
    split_key = split if split in ("dev", "test") else "test"
    trials = trial_split()[split_key]
    segmentation, errors = eval_segmentation()
    entities = eval_entities(trials, client, limit_lines=(limit * 10 if limit else (150 if client else None)))
    return {
        "metrics": {
            "segmentation_gold_cases": segmentation,
            "segmentation_chia_roundtrip": eval_chia_roundtrip(trials),
            "entities": entities,
            "screening_only_vs_chia": eval_screening(trials),
            "n_trials": len(trials),
        },
        "errors": errors,
    }
