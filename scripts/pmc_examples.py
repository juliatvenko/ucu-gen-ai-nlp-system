"""Pick published case reports from PMC-Patients as demo examples. They have no labels and stay out of evals.

Run after scripts.download_data. Writes data/pmc_examples.json.
"""
import json
from pathlib import Path

from trialmatch.case_reports import read_records

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "data" / "raw" / "pmc" / "first5mb.json"
OUT = ROOT / "data" / "pmc_examples.json"

# Chosen for a clear main condition with recruiting trials, adult ages, and a mix of areas and sexes.
CHOSEN = ["1236965-1", "1488855-1", "2045104-1", "1884161-2", "1634846-1"]


def main() -> None:
    by_uid = {r["patient_uid"]: r for r in read_records(SOURCE)}
    examples = []
    for uid in CHOSEN:
        r = by_uid[uid]
        examples.append({
            "id": f"pmc-{r['PMID']}",
            "text": r["patient"],  # unmodified, as the license requires saying if it were changed
            "source": "published",
            "title": r["title"],
            "pmid": r["PMID"],
            "patient_uid": r["patient_uid"],  # one article can describe several patients
            "year": r["pub_date"],
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{r['PMID']}/",
            "credit": "the PMC-Patients dataset, CC BY-NC-SA 4.0",
        })
    OUT.write_text(json.dumps(examples, indent=1, ensure_ascii=False) + "\n")
    print("wrote", len(examples), "examples to", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
