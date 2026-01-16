from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Tuple, Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from datetime import date
import re
import csv

from pylibCZIrw import czi as czirw


INPUT_ROOT = Path("/DATA/mimosa/original-dataset")  # dossier qui contient les 7 dossiers sujets
OUT_CSV = Path("/DATA/mimosa/metadata_audit_out") / "subject_sessions_microscope.csv"
WORKERS = 8


def as_text(v: Any) -> Optional[str]:
    """Return a clean string from common metadata value shapes (str/bytes/list/dict)."""
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s if s else None
    if isinstance(v, bytes):
        try:
            s = v.decode("utf-8", errors="ignore").strip()
            return s if s else None
        except Exception:
            return None
    if isinstance(v, list) and v:
        return as_text(v[0])
    if isinstance(v, dict):
        return as_text(v.get("#text") or v.get("text") or v.get("Value") or v.get("@Value"))
    return None


def walk_all(obj: Any, path: str = ""):
    """Yield (path, value) for every node in nested dict/list metadata."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}/{k}" if path else str(k)
            yield (p, v)
            yield from walk_all(v, p)
    elif isinstance(obj, list):
        for i, it in enumerate(obj):
            p = f"{path}[{i}]"
            yield (p, it)
            yield from walk_all(it, p)


def get_czi_metadata(czi_path: Path) -> dict:
    with czirw.open_czi(str(czi_path)) as doc:
        return doc.metadata


def valid_date(y: int, m: int, d: int) -> bool:
    try:
        date(y, m, d)
        return True
    except ValueError:
        return False


def ses_from_string(s: str) -> Optional[str]:
    """Extract YYYY-MM-DD or YYYYMMDD or DD-MM-YYYY(DD/MM/YYYY) and return ses-YYYYMMDD."""
    # YYYY-MM-DD
    m = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if valid_date(y, mo, d):
            return f"ses-{y:04d}{mo:02d}{d:02d}"

    # YYYYMMDD
    m = re.search(r"\b(20\d{2})(\d{2})(\d{2})\b", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if valid_date(y, mo, d):
            return f"ses-{y:04d}{mo:02d}{d:02d}"

    # DD-MM-YYYY or DD/MM/YYYY
    m = re.search(r"\b(\d{2})[-/](\d{2})[-/](20\d{2})\b", s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if valid_date(y, mo, d):
            return f"ses-{y:04d}{mo:02d}{d:02d}"

    return None


def subject_from_filename(stem: str) -> Optional[str]:
    tokens = [t for t in stem.replace("-", "_").split("_") if t]
    for t in tokens:
        if any(ch.isalpha() for ch in t) and any(ch.isdigit() for ch in t) and 6 <= len(t) <= 40:
            return t
    return None


def subject_from_path(czi_path: Path) -> Optional[str]:
    for part in reversed(czi_path.parts[:-1]):  # ignore filename
        toks = re.split(r"[_\-\s]+", part)
        for t in toks:
            if any(ch.isalpha() for ch in t) and any(ch.isdigit() for ch in t) and 6 <= len(t) <= 40:
                return t
    return None


def best_session(meta: dict) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Return (ses_label, field_name, meta_path)

    Priority:
      1) AcquisitionDateAndTime
      2) StartTime
      3) SessionName / @SessionName
      4) CreationDate
    """
    rules = [
        ("AcquisitionDateAndTime", ("/acquisitiondateandtime",)),
        ("StartTime", ("/starttime",)),
        ("SessionName", ("/@sessionname", "/sessionname")),
        ("CreationDate", ("/creationdate",)),
    ]

    for field_name, suffixes in rules:
        for p, v in walk_all(meta):
            pl = p.lower()
            if any(pl.endswith(sfx) for sfx in suffixes):
                txt = as_text(v)
                if not txt:
                    continue
                ses = ses_from_string(txt)
                if ses:
                    return ses, field_name, p

    return None, None, None


def microscope_name(meta: dict) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract microscope name from:
      ImageDocument/Metadata/HardwareSetting/Configuration/Device[*]
    where Device has Id='Microscope' and Name='...'
    Return (name, meta_path_to_device)
    """
    # try the "expected" place first
    try:
        devices = meta["ImageDocument"]["Metadata"]["HardwareSetting"]["Configuration"]["Device"]
    except Exception:
        devices = None

    if isinstance(devices, dict):
        devices = [devices]

    if isinstance(devices, list):
        for i, dev in enumerate(devices):
            if not isinstance(dev, dict):
                continue
            dev_id = as_text(dev.get("@Id") or dev.get("Id"))
            if dev_id == "Microscope":
                nm = as_text(dev.get("@Name") or dev.get("Name"))
                if nm:
                    return nm, f"ImageDocument/Metadata/HardwareSetting/Configuration/Device[{i}]"

    # fallback: generic scan anywhere
    for p, v in walk_all(meta):
        if isinstance(v, dict):
            dev_id = as_text(v.get("@Id") or v.get("Id"))
            if dev_id == "Microscope":
                nm = as_text(v.get("@Name") or v.get("Name"))
                if nm:
                    return nm, p

    return None, None


def parse_one_file(czi_path: Path) -> Optional[dict]:
    try:
        meta = get_czi_metadata(czi_path)
    except Exception as e:
        return {"file": str(czi_path), "error": f"read_meta_failed: {e}"}

    subject = subject_from_filename(czi_path.stem) or subject_from_path(czi_path) or "unknown"
    ses, ses_field, ses_path = best_session(meta)
    mic, mic_path = microscope_name(meta)

    return {
        "file": str(czi_path),
        "filename": czi_path.name,
        "subject": subject,
        "ses": ses,
        "ses_field": ses_field,
        "ses_path": ses_path,
        "microscope": mic,
        "microscope_path": mic_path,
        "error": None,
    }


def main() -> None:
    czis = sorted(INPUT_ROOT.rglob("*.czi"))
    if not czis:
        print(f"[INFO] No .czi found under {INPUT_ROOT}")
        return

    rows: List[dict] = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(parse_one_file, p) for p in czis]
        for fut in as_completed(futs):
            r = fut.result()
            if r:
                rows.append(r)

    # ---- Build correspondence table: subject -> (ses -> microscopes)
    subj_map: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    # also keep examples of which field was used
    subj_ses_field: Dict[Tuple[str, str], Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for r in rows:
        if r.get("error"):
            continue
        subject = r["subject"]
        ses = r["ses"] or "MISSING_SESSION"
        mic = r["microscope"] or "UNKNOWN_MICROSCOPE"
        subj_map[subject][ses][mic] += 1
        key = (subject, ses)
        if r.get("ses_field"):
            subj_ses_field[key][r["ses_field"]] += 1

    # ---- Write CSV (one line per subject+session+microscope)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "subject",
            "session",
            "microscope",
            "n_files",
            "session_field_used_most",
            "session_field_counts",
        ])

        for subject in sorted(subj_map.keys()):
            for ses in sorted(subj_map[subject].keys()):
                field_counts = subj_ses_field.get((subject, ses), {})
                if field_counts:
                    field_used_most = sorted(field_counts.items(), key=lambda x: (-x[1], x[0]))[0][0]
                    field_counts_str = ";".join([f"{k}:{v}" for k, v in sorted(field_counts.items())])
                else:
                    field_used_most = ""
                    field_counts_str = ""

                for mic in sorted(subj_map[subject][ses].keys()):
                    n = subj_map[subject][ses][mic]
                    w.writerow([subject, ses, mic, n, field_used_most, field_counts_str])

    # ---- Print a readable summary (subject -> sessions list)
    print("\n=== SUBJECT -> SESSIONS (with microscopes) ===")
    for subject in sorted(subj_map.keys()):
        sessions = sorted(subj_map[subject].keys())
        print(f"\n{subject}:")
        for ses in sessions:
            mics = sorted(subj_map[subject][ses].items(), key=lambda x: (-x[1], x[0]))
            mic_str = ", ".join([f"{mic} (n={n})" for mic, n in mics])
            print(f"  - {ses}: {mic_str}")

    print(f"\n[OK] CSV written: {OUT_CSV}")


if __name__ == "__main__":
    main()