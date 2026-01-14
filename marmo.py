from pylibCZIrw import czi as czirw
from pathlib import Path
import json
import re

CZI_PATH = Path("/DATA/mimosa/original-dataset/6-Marmot-MJO16052401/MJO16052401_Cx_200_202.czi")
OUT_JSON = Path("./marmot_metadata_full.json")  # export complet (optionnel)


def walk(obj, path=""):
    if isinstance(obj, dict):
        yield path, obj
        for k, v in obj.items():
            p2 = f"{path}/{k}" if path else str(k)
            yield from walk(v, p2)
    elif isinstance(obj, list):
        for i, it in enumerate(obj):
            p2 = f"{path}[{i}]"
            yield from walk(it, p2)
    else:
        yield path, obj


def to_jsonable(x):
    # pylibCZIrw metadata is usually JSON-able, but just in case:
    if isinstance(x, (str, int, float, bool)) or x is None:
        return x
    if isinstance(x, dict):
        return {str(k): to_jsonable(v) for k, v in x.items()}
    if isinstance(x, list):
        return [to_jsonable(v) for v in x]
    return str(x)


def main():
    with czirw.open_czi(str(CZI_PATH)) as doc:
        meta = doc.metadata

    print("=== QUICK CHECKS ===")
    # Try your usual path first
    try:
        imagename = meta["ImageDocument"]["Metadata"]["Information"]["Image"]["ImageName"]
    except Exception:
        imagename = None
    print("ImageName:", imagename)

    print("\n=== SEARCH KEYS THAT LOOK LIKE DATE/TIME/SESSION ===")
    key_hints = ("date", "time", "session", "acquisition", "created", "timestamp", "start")
    hits = []
    for p, v in walk(meta):
        if not p:
            continue
        pl = p.lower()
        if any(h in pl for h in key_hints):
            # print small values only
            if isinstance(v, (str, int, float, bool)) or v is None:
                hits.append((p, v))
            elif isinstance(v, dict) and len(v) <= 6:
                hits.append((p, v))
    for p, v in hits[:80]:
        print(f"- {p}: {v}")

    print("\n=== SEARCH VALUES THAT CONTAIN A DATE STRING ===")
    # look for common patterns: 20230417, 2023-04-17, 17-04-2023
    date_pat = re.compile(r"(20\d{2}[-/]\d{2}[-/]\d{2})|(\b\d{2}[-/]\d{2}[-/](20\d{2})\b)|(\b20\d{2}\d{2}\d{2}\b)")
    val_hits = []
    for p, v in walk(meta):
        if isinstance(v, str) and date_pat.search(v):
            val_hits.append((p, v))
    for p, v in val_hits[:80]:
        print(f"- {p}: {v}")

    print("\n=== EXPORT FULL METADATA (OPTIONAL) ===")
    OUT_JSON.write_text(json.dumps(to_jsonable(meta), indent=2, ensure_ascii=False), encoding="utf-8")
    print("Saved:", OUT_JSON.resolve())


if __name__ == "__main__":
    main()