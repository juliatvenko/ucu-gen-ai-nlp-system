"""Download the open datasets into data/raw. Safe to re-run."""
import zipfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
FILES = {
    "chia/chia_without_scope.zip": "https://ndownloader.figshare.com/files/21728853",  # Chia, CC BY 4.0
    "trec/topics2021.xml": "https://www.trec-cds.org/topics2021.xml",
    "trec/qrels2021.txt": "https://trec.nist.gov/data/trials/qrels2021.txt",
}
# Only the first 5 MB of an 837 MB file: enough for demo examples. CC BY-NC-SA 4.0.
PARTIAL = {
    "pmc/first5mb.json": ("https://huggingface.co/datasets/zhengyun21/PMC-Patients/resolve/main/PMC-Patients-V2.json", 5 * 1024 * 1024),
}


def main() -> None:
    for name, url in FILES.items():
        path = RAW / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            print("downloading", name)
            r = httpx.get(url, follow_redirects=True, timeout=180)
            r.raise_for_status()
            path.write_bytes(r.content)
    for name, (url, size) in PARTIAL.items():
        path = RAW / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            print("downloading the first", size // (1024 * 1024), "MB of", name)
            r = httpx.get(url, headers={"Range": f"bytes=0-{size - 1}"}, follow_redirects=True, timeout=180)
            r.raise_for_status()
            path.write_bytes(r.content)
    archive = RAW / "chia" / "chia_without_scope.zip"
    with zipfile.ZipFile(archive) as z:
        for member in z.namelist():
            if member.startswith("/") or ".." in member:
                raise ValueError(f"unsafe path in archive: {member}")
        z.extractall(archive.parent)
    print("done:", len(list((RAW / "chia").glob("*.ann"))), "Chia annotation files")


if __name__ == "__main__":
    main()
