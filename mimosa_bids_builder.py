from __future__ import annotations

from pylibCZIrw import czi as czirw
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Optional, Tuple, List, Dict, Any
import re


# -----------------------------
# Helpers: normalize metadata
# -----------------------------

def as_text(v: Any) -> Optional[str]:
    """Normalize metadata values to a usable string (handles str/list/dict)."""
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


# -----------------------------
# Read metadata
# -----------------------------

def get_czi_metadata(czi_path: Path) -> dict:
    """Read and return CZI metadata as a Python dictionary using pylibCZIrw."""
    with czirw.open_czi(str(czi_path)) as doc:
        return doc.metadata


# -----------------------------
# Subject + sample
# -----------------------------

def get_subject_from_filename(stem: str) -> Optional[str]:
    """Heuristic: first token that contains letters+digits and is not too short."""
    tokens = [t for t in stem.replace("-", "_").split("_") if t]
    for t in tokens:
        has_a = any(ch.isalpha() for ch in t)
        has_d = any(ch.isdigit() for ch in t)
        if has_a and has_d and 6 <= len(t) <= 40:
            return t
    return None


def get_sample_from_filename(stem: str) -> Optional[str]:
    """Heuristic: first short alphabetic token after subject token."""
    tokens = [t for t in stem.replace("-", "_").split("_") if t]
    subj = get_subject_from_filename(stem)
    start_idx = 0
    if subj and subj in tokens:
        start_idx = tokens.index(subj) + 1
    for t in tokens[start_idx:]:
        if t.isalpha() and 1 <= len(t) <= 12:
            if t.lower() == "cortex":
                return "Cx"
            return t
    return None


def get_subject_from_path(czi_path: Path) -> Optional[str]:
    """Fallback: try to extract an id-like token from folder names."""
    parts = list(czi_path.parts)
    for part in reversed(parts[:-1]):  # ignore filename
        toks = re.split(r"[_\-\s]+", part)
        for t in toks:
            if any(ch.isalpha() for ch in t) and any(ch.isdigit() for ch in t) and 6 <= len(t) <= 40:
                return t
    return None


# -----------------------------
# Date/session extraction
# -----------------------------

def _valid_ymd(y: int, m: int, d: int) -> bool:
    try:
        date(y, m, d)
        return True
    except ValueError:
        return False


def ses_from_string(s: str) -> Optional[str]:
    """Extract date from a string and return ses-YYYYMMDD."""
    m = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _valid_ymd(y, mo, d):
            return f"ses-{y:04d}{mo:02d}{d:02d}"

    m = re.search(r"\b(20\d{2})(\d{2})(\d{2})\b", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _valid_ymd(y, mo, d):
            return f"ses-{y:04d}{mo:02d}{d:02d}"

    m = re.search(r"\b(\d{2})[-/](\d{2})[-/](20\d{2})\b", s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _valid_ymd(y, mo, d):
            return f"ses-{y:04d}{mo:02d}{d:02d}"

    return None


def best_session(meta: dict) -> Tuple[Optional[str], Optional[str]]:
    """
    Return (ses_label, source_path) using ONLY approved metadata fields.

    Priority:
      1) ImageDocument/Metadata/Information/Image/AcquisitionDateAndTime
      2) ImageDocument/Metadata/Information/Image/Dimensions/T/StartTime (or any *StartTime)
      3) any @SessionName / SessionName (often contains YYYYMMDD)
      4) ImageDocument/Metadata/Information/Document/CreationDate

    If nothing is found, return (None, None).
    """

    # 1) AcquisitionDateAndTime (canonical)
    try:
        v = as_text(meta["ImageDocument"]["Metadata"]["Information"]["Image"]["AcquisitionDateAndTime"])
        if v:
            ses = ses_from_string(v)
            if ses:
                return ses, "ImageDocument/Metadata/Information/Image/AcquisitionDateAndTime"
    except Exception:
        pass

    # 2) StartTime: prefer canonical path first
    preferred_path = "ImageDocument/Metadata/Information/Image/Dimensions/T/StartTime"
    for p, v in walk_all(meta):
        if p.endswith(preferred_path):
            txt = as_text(v)
            if txt:
                ses = ses_from_string(txt)
                if ses:
                    return ses, p

    # Otherwise any StartTime
    for p, v in walk_all(meta):
        if p.lower().endswith("/starttime"):
            txt = as_text(v)
            if txt:
                ses = ses_from_string(txt)
                if ses:
                    return ses, p

    # 3) SessionName anywhere
    for p, v in walk_all(meta):
        pl = p.lower()
        if pl.endswith("/@sessionname") or pl.endswith("/sessionname"):
            txt = as_text(v)
            if txt:
                ses = ses_from_string(txt)
                if ses:
                    return ses, p

    # 4) CreationDate
    try:
        v = as_text(meta["ImageDocument"]["Metadata"]["Information"]["Document"]["CreationDate"])
        if v:
            ses = ses_from_string(v)
            if ses:
                return ses, "ImageDocument/Metadata/Information/Document/CreationDate"
    except Exception:
        pass

    return None, None


# -----------------------------
# Acquisition extraction (acq)
# -----------------------------

def microscope_name(meta: dict) -> Optional[str]:
    """Try hard to find microscope name."""
    for _, d in walk_all(meta):
        if isinstance(d, dict):
            dev_id = as_text(d.get("@Id") or d.get("Id"))
            if dev_id == "Microscope":
                nm = as_text(d.get("@Name") or d.get("Name"))
                if nm:
                    return nm
    return None


def pixel_xy_um(meta: dict) -> Tuple[Optional[float], Optional[float]]:
    """Extract pixel size X/Y (µm). Robust search for Distance Id X/Y."""
    px: Dict[str, Optional[float]] = {"X": None, "Y": None}

    for _, d in walk_all(meta):
        if not isinstance(d, dict):
            continue
        dist_id = as_text(d.get("@Id") or d.get("Id"))
        if dist_id not in ("X", "Y"):
            continue

        val_txt = as_text(d.get("Value") or d.get("@Value"))
        if val_txt is None:
            val_txt = as_text(d.get("Value"))

        unit_txt = as_text(d.get("Unit") or d.get("@Unit"))

        if val_txt is None:
            continue

        try:
            fval = float(val_txt)
        except Exception:
            continue

        if unit_txt in (None, "", "m", "meter", "metre"):
            v_um = fval * 1e6
        elif unit_txt in ("µm", "um"):
            v_um = fval
        elif unit_txt == "nm":
            v_um = fval / 1000.0
        else:
            v_um = fval

        px[dist_id] = round(v_um, 3)

    return px["X"], px["Y"]


def acq_signature(meta: dict) -> Tuple[str, Optional[float], Optional[float]]:
    """Stable signature used to assign acq-1/acq-2..."""
    mic = microscope_name(meta) or "unknown"
    px, py = pixel_xy_um(meta)
    return (mic, px, py)


# -----------------------------
# Main parsing per file
# -----------------------------

def parse_one_file(czi_path: Path) -> Optional[dict]:
    """Parse one CZI; return record dict or None if session cannot be found."""
    meta = get_czi_metadata(czi_path)

    subject = get_subject_from_filename(czi_path.stem) or get_subject_from_path(czi_path) or "unknown"
    sample = get_sample_from_filename(czi_path.stem) or "unknown"

    ses, ses_src = best_session(meta)
    if ses is None:
        return None

    sig = acq_signature(meta)

    return {
        "src": czi_path,
        "subject_raw": subject,
        "sample": sample,
        "ses": ses,
        "ses_src": ses_src,
        "acq_sig": sig,
    }


# -----------------------------
# File placement (symlink)
# -----------------------------

def move_file(src: Path, dst: Path) -> None:
    """Create a symlink at dst pointing to src (BIDS-named alias)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    dst.symlink_to(src.resolve())


# -----------------------------
# Organize all files
# -----------------------------

def organize_sourcedata(input_root: Path, sourcedata_dir: Path, workers: int = 8) -> None:
    czis = sorted(Path(input_root).rglob("*.czi"))
    if not czis:
        print(f"[INFO] No .czi files found under {input_root}")
        return

    records: List[dict] = []
    skipped = 0

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(parse_one_file, czi): czi for czi in czis}
        for fut in as_completed(futs):
            czi = futs[fut]
            rec = fut.result()
            if rec is None:
                skipped += 1
                continue
            records.append(rec)

    if not records:
        print(f"[INFO] No usable files. Skipped: {skipped}")
        return

    print(f"[INFO] Parsed: {len(records)} files (skipped: {skipped})")

    subjects = sorted({r["subject_raw"] for r in records})
    subject_to_sub = {sid: f"sub-{i:02d}" for i, sid in enumerate(subjects, start=1)}

    group_sigs: Dict[Tuple[str, str, str], List[Tuple]] = {}
    for r in records:
        sub = subject_to_sub[r["subject_raw"]]
        key = (sub, r["ses"], r["sample"])
        group_sigs.setdefault(key, [])
        if r["acq_sig"] not in group_sigs[key]:
            group_sigs[key].append(r["acq_sig"])

    for key in group_sigs:
        group_sigs[key] = sorted(group_sigs[key], key=lambda x: str(x))

    run_counter: Dict[Tuple[str, str, str, int], int] = {}

    def sort_key(r: dict):
        sub = subject_to_sub[r["subject_raw"]]
        key3 = (sub, r["ses"], r["sample"])
        acq_num = group_sigs[key3].index(r["acq_sig"]) + 1
        return (sub, r["ses"], r["sample"], acq_num, r["src"].name)

    print("[INFO] Session sources summary (first 30 usable files):")
    for rr in sorted(records, key=lambda x: x["src"].name)[:30]:
        print(f"  - {rr['src'].name}: {rr['ses']} ({rr['ses_src']})")

    for r in sorted(records, key=sort_key):
        sub = subject_to_sub[r["subject_raw"]]
        ses = r["ses"]
        sample = r["sample"]

        key3 = (sub, ses, sample)
        acq_num = group_sigs[key3].index(r["acq_sig"]) + 1

        rc_key = (sub, ses, sample, acq_num)
        run_counter[rc_key] = run_counter.get(rc_key, 0) + 1
        run = f"run-{run_counter[rc_key]:02d}"

        dest_dir = Path(sourcedata_dir) / sub / ses / f"sample-{sample}" / f"acq-{acq_num}"
        dest_name = f"{sub}_{ses}_sample-{sample}_acq-{acq_num}_{run}.czi"
        dest_path = dest_dir / dest_name

        move_file(r["src"], dest_path)

    print("[OK] sourcedata organization done.")


def main() -> None:
    input_root = Path("/DATA/mimosa/original-dataset")
    sourcedata_dir = Path("/DATA/mimosa/MIMOSA_BIDS_dataset/sourcedata")
    organize_sourcedata(input_root, sourcedata_dir, workers=8)


if __name__ == "__main__":
    main()