"""Read the Chia corpus (BRAT format) and build the entity gazetteer from the train split only."""
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHIA = ROOT / "data" / "raw" / "chia"
OUT = ROOT / "data" / "derived" / "gazetteer.json"
CORE = {"Condition", "Drug", "Procedure", "Measurement", "Value", "Temporal", "Negation", "Person"}


def trial_split(seed: int = 13) -> dict[str, list[str]]:
    """Split by trial, not by line, so one trial's wording can't leak across splits."""
    trials = sorted({p.name.split("_")[0] for p in CHIA.glob("*.ann")})
    random.Random(seed).shuffle(trials)
    return {"train": trials[:800], "dev": trials[800:900], "test": trials[900:]}


def read_raw(path: Path) -> str:
    """Keep newlines as they are: Chia offsets count \\r, and universal newlines would shift them."""
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def read_file(stem: Path) -> tuple[str, list[tuple[str, int, int]]]:
    """Return the text and core entities. A discontinuous span is stored as its outer span."""
    text = read_raw(stem.with_suffix(".txt"))
    entities = []
    for line in read_raw(stem.with_suffix(".ann")).splitlines():
        if not line.startswith("T"):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        tokens = parts[1].replace(";", " ").split()
        if tokens[0] in CORE:
            offsets = [int(x) for x in tokens[1:]]
            entities.append((tokens[0], min(offsets), max(offsets)))
    return text, entities


def iter_files(trials: list[str]):
    for trial in trials:
        for kind in ("inc", "exc"):
            stem = CHIA / f"{trial}_{kind}"
            if stem.with_suffix(".ann").exists():
                yield kind, *read_file(stem)


def build_gazetteer(min_count: int = 2, min_precision: float = 0.5) -> dict:
    """Keep a phrase only if, when it appears, it is usually annotated. This drops common words."""
    annotated: dict[str, Counter] = defaultdict(Counter)
    texts = []
    for _, text, entities in iter_files(trial_split()["train"]):
        texts.append(text.lower())
        for etype, start, end in entities:
            if etype in {"Value", "Temporal", "Negation"}:
                continue  # handled by regexes
            phrase = re.sub(r"\s+", " ", text[start:end].lower()).strip()
            if 2 <= len(phrase) <= 60:
                annotated[phrase][etype] += 1
    corpus = "\n".join(texts)
    gazetteer = {}
    for phrase, types in annotated.items():
        count = sum(types.values())
        if count < min_count:
            continue
        occurrences = len(re.findall(r"(?<![\w-])" + re.escape(phrase) + r"(?![\w-])", corpus))
        if occurrences and count / occurrences >= min_precision:
            etype, n = types.most_common(1)[0]
            gazetteer[phrase] = {"type": etype, "count": n}
    return gazetteer


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    gazetteer = build_gazetteer()
    OUT.write_text(json.dumps(gazetteer, indent=0, sort_keys=True))
    print(len(gazetteer), "phrases", Counter(v["type"] for v in gazetteer.values()).most_common())
