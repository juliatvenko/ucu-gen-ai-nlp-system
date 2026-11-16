"""Published case reports from PMC-Patients, as a collection for cohort search.

The local copy (data/raw/pmc/first5mb.json) is ignored by git; scripts/download_data.py fetches it.
Texts are used unchanged and shown with their credit, as CC BY-NC-SA 4.0 requires.
"""
import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "data" / "raw" / "pmc" / "first5mb.json"
CREDIT = "the PMC-Patients dataset, CC BY-NC-SA 4.0"
PER_YEAR = {"year": 1, "month": 12, "week": 52, "day": 365}


def read_records(path: Path) -> list[dict]:
    """The file is cut at 5 MB, so read whole records one by one and drop the partial last one."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    decoder = json.JSONDecoder()
    records, i = [], text.index("{")
    while True:
        try:
            record, end = decoder.raw_decode(text, i)
        except ValueError:
            return records
        records.append(record)
        i = text.find("{", end)
        if i < 0:
            return records


def _age(field) -> float | None:
    # The dataset gives age as [[value, unit]].
    try:
        value, unit = field[0]
        return float(value) / PER_YEAR[unit]
    except (IndexError, KeyError, TypeError, ValueError):
        return None


@lru_cache(maxsize=1)
def load() -> dict[str, dict]:
    """patient_uid -> record with text, age in years, sex, and citation. Empty if the file isn't downloaded."""
    if not SOURCE.exists():
        return {}
    out = {}
    for r in read_records(SOURCE):
        out[r["patient_uid"]] = {
            "id": f"pmc-{r['patient_uid']}",
            "text": r["patient"],
            "age": _age(r.get("age")),
            "sex": {"F": "female", "M": "male"}.get(r.get("gender")),
            "title": r["title"],
            "pmid": r["PMID"],
            "patient_uid": r["patient_uid"],
            "year": r["pub_date"],
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{r['PMID']}/",
            "credit": CREDIT,
            "source": "published",
        }
    return out
