"""TREC Clinical Trials 2021: real patient topics with human eligibility judgements."""
import random
import re
from collections import defaultdict

from .common import DATA

RAW = DATA / "raw" / "trec"


def load_topics() -> dict[int, str]:
    xml = (RAW / "topics2021.xml").read_text()
    return {int(n): re.sub(r"\s+", " ", t).strip() for n, t in re.findall(r'<topic number="(\d+)">(.*?)</topic>', xml, re.S)}


def load_qrels() -> dict[int, dict[str, int]]:
    """2 eligible, 1 excluded, 0 not relevant."""
    qrels: dict[int, dict[str, int]] = defaultdict(dict)
    for line in (RAW / "qrels2021.txt").read_text().splitlines():
        topic, _, nct, label = line.split()
        qrels[int(topic)][nct] = int(label)
    return qrels


def topics_for(split: str, limit: int | None) -> list[int]:
    # Fixed split by topic number. dev: 1-37, test: 38-75.
    ids = sorted(load_topics())
    ids = {"dev": ids[:37], "test": ids[37:]}.get(split, ids)
    return ids[: limit or None]


def sample_pool(judged: dict[str, int], per_label: int = 10, seed: int = 7) -> dict[str, int]:
    """Balanced sample. The true label mix is not preserved, so report P/R with this in mind."""
    rng = random.Random(seed)
    pool = {}
    for label in (2, 1, 0):
        ids = sorted(n for n, l in judged.items() if l == label)
        rng.shuffle(ids)
        pool.update({n: label for n in ids[:per_label]})
    return pool
