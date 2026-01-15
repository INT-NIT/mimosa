from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import json

from pylibCZIrw import czi as czirw


# -------------------
# CONFIG (edit these)
# -------------------
INPUT_DIR = Path("/envau/work/invibe/USERS/IBOS/data/Marmoset/lames/0-Originals/1-Fenouil-original")  # <- folder to scan
OUTPUT_JSON = Path("/DATA/mimosa/mimosa/subject_name_hits.json")                          # <- output report

# Put here any subject names you want to detect (case-insensitive)
KEYWORDS = ["fenouil", "marmot", "sully"]


def walk_strings(obj: Any, path: str = ""):
    """Yield (path, string_value) for every string found in nested dict/list metadata."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}/{k}" if path else str(k)
            yield from walk_strings(v, p)
    elif isinstance(obj, list):
        for i, it in enumerate(obj):
            p = f"{path}[{i}]"
            yield from walk_strings(it, p)
    elif isinstance(obj, str):
        s = obj.strip()
        if s:
            yield path, s


def get_czi_metadata(czi_path: Path) -> dict:
    """Read CZI metadata as a Python dict using pylibCZIrw."""
    with czirw.open_czi(str(czi_path)) as doc:
        return doc.metadata


def find_keyword_hits(meta: dict, keywords: List[str]) -> List[Dict[str, str]]:
    """Return list of hits: [{keyword, path, value}, ...]"""
    kws = [k.lower() for k in keywords]
    hits: List[Dict[str, str]] = []
    for p, s in walk_strings(meta):
        low = s.lower()
        for k in kws:
            if k in low:
                hits.append({"keyword": k, "path": p, "value": s})
    return hits


def main() -> None:
    czis = sorted(INPUT_DIR.rglob("*.czi"))
    if not czis:
        print(f"[INFO] No .czi found under: {INPUT_DIR}")
        return

    report: List[Dict[str, Any]] = []

    for czi in czis:
        try:
            meta = get_czi_metadata(czi)
            hits = find_keyword_hits(meta, KEYWORDS)
            report.append(
                {
                    "file": str(czi),
                    "hits_count": len(hits),
                    "hits": hits,   # list of (keyword, path, value)
                }
            )
        except Exception as e:
            report.append({"file": str(czi), "error": str(e)})

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"[OK] Saved: {OUTPUT_JSON}")
    # Small console summary
    n_with_hits = sum(1 for r in report if r.get("hits_count", 0) > 0)
    print(f"[INFO] Files scanned: {len(czis)} | files with hits: {n_with_hits}")


if __name__ == "__main__":
    main()
