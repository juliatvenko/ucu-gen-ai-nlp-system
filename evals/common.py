import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "evals" / "results"
DATA = ROOT / "data"


def prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3), "support": tp + fn}


def per_class(pairs: list[tuple[str, str]], labels: list[str]) -> dict:
    """pairs are (gold, predicted). Returns per-class scores and macro-F1."""
    out = {}
    for label in labels:
        tp = sum(g == label and p == label for g, p in pairs)
        fp = sum(g != label and p == label for g, p in pairs)
        fn = sum(g == label and p != label for g, p in pairs)
        out[label] = prf(tp, fp, fn)
    out["macro_f1"] = round(sum(out[l]["f1"] for l in labels) / len(labels), 3)
    return out


def wilson(successes: int, n: int, z: float = 1.96) -> list[float]:
    """95% interval. The gold sets are small, so a point estimate alone would mislead."""
    if n == 0:
        return [0.0, 0.0]
    p = successes / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(centre - half, 3), round(centre + half, 3)]


def dcg(gains: list[float], k: int) -> float:
    return sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(gains[:k]))


def ndcg(gains: list[float], k: int = 10) -> float:
    ideal = dcg(sorted(gains, reverse=True), k)
    return dcg(gains, k) / ideal if ideal else 0.0


def load_vignettes(split: str | None = None) -> list[dict]:
    data = json.loads((DATA / "vignettes.json").read_text())
    return [v for v in data if split in (None, "all", v["split"])]


def save(component: str, mode: str, split: str, payload: dict) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{component}_{mode}_{split}.json"
    path.write_text(json.dumps(payload, indent=1, default=str))
    return path
