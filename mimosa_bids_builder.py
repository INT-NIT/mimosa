from __future__ import annotations

from pylibCZIrw import czi as czirw
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Optional, Tuple, List, Dict, Any
import re


def get_czi_metadata(czi_path: Path) -> dict:
    """Read and return CZI metadata as a Python dictionary using pylibCZIrw."""
    with czirw.open_czi(str(czi_path)) as doc:
        return doc.metadata


def get_subject_from_filename(stem: str) -> Optional[str]:
    """Extract a subject-like identifier from the filename stem (heuristic)."""
    tokens = [t for t in stem.replace("-", "_").split("_") if t]
    for t in tokens:
        has_a = any(ch.isalpha() for ch in t)
        has_d = any(ch.isdigit() for ch in t)
        if has_a and has_d and 6 <= len(t) <= 40:
            return t
    return None


def get_sample_from_filename(stem: str) -> Optional[str]:
    """Extract a sample label from the filename stem (heuristic)."""
    tokens = [t for t in stem.replace("-", "_").split("_") if t]

    subj = get_subject_from_filename(stem)
    start_idx = 0
    if subj and subj in tokens:
        start_idx = tokens.index(subj) + 1

    for t in tokens[start_idx:]:
        if t.isalpha() and 1 <= len(t) <= 8:
            if t.lower() == "cortex":
                return "Cx"
            return t
    return None


def _valid_ymd(y: int, m: int, d: int) -> bool:
    """Validate that (year, month, day) is a real calendar date."""
    try:
        date(y, m, d)
        return True
    except ValueError:
        return False


def _walk(obj: Any):
    """Recursively walk a nested (dict/list) structure and yield dict nodes."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for it in obj:
            yield from _walk(it)


def get_imagename_from_metadata(meta: dict) -> Optional[str]:
    """Best-effort extraction of ImageName from pylibCZIrw metadata dict."""
    try:
        v = meta["ImageDocument"]["Metadata"]["Information"]["Image"]["ImageName"]
        if isinstance(v, str) and v.strip():
            return v.strip()
    except Exception:
        pass

    for d in _walk(meta):
        v = d.get("ImageName") or d.get("@ImageName")
        if isinstance(v, str) and v.strip():
            return v.strip()

    return None


def get_best_datetime_for_session(meta: dict) -> Optional[str]:
    """Return a string that contains a date for building the BIDS session.

    Priority:
      1) Information/Image/AcquisitionDateAndTime
      2) Information/Document/CreationDate
      3) ImageName (may contain a date)
    """
    try:
        v = meta["ImageDocument"]["Metadata"]["Information"]["Image"]["AcquisitionDateAndTime"]
        if isinstance(v, str) and v.strip():
            return v.strip()
    except Exception:
        pass

    try:
        v = meta["ImageDocument"]["Metadata"]["Information"]["Document"]["CreationDate"]
        if isinstance(v, str) and v.strip():
            return v.strip()
    except Exception:
        pass

    imagename = get_imagename_from_metadata(meta)
    if isinstance(imagename, str) and imagename.strip():
        return imagename.strip()

    return None


def ses_from_any_datetime(s: str) -> Optional[str]:
    """Extract a date from a string and return a BIDS session label 'ses-YYYYMMDD'.

    Supported patterns inside the string:
      - YYYY-MM-DD (e.g., 2024-07-27T10:37:13Z)
      - YYYYMMDD (e.g., 20230417_765.czi)
      - DD-MM-YYYY or DD/MM/YYYY (e.g., 17-04-2023)
    """
    # YYYY-MM-DD
    m = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _valid_ymd(y, mo, d):
            return f"ses-{y:04d}{mo:02d}{d:02d}"

    # YYYYMMDD
    m = re.search(r"\b(20\d{2})(\d{2})(\d{2})\b", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _valid_ymd(y, mo, d):
            return f"ses-{y:04d}{mo:02d}{d:02d}"

    # DD-MM-YYYY or DD/MM/YYYY
    m = re.search(r"\b(\d{2})[-/](\d{2})[-/](20\d{2})\b", s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _valid_ymd(y, mo, d):
            return f"ses-{y:04d}{mo:02d}{d:02d}"

    return None


def get_microscope_name(meta: dict) -> Optional[str]:
    """Find microscope device name from metadata dict (Device Id='Microscope')."""
    for d in _walk(meta):
        dev_id = d.get("@Id") or d.get("Id")
        if dev_id == "Microscope":
            name = d.get("@Name") or d.get("Name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    return None


def get_pixel_xy_um(meta: dict) -> Tuple[Optional[float], Optional[float]]:
    """Extract pixel size X/Y in micrometers from metadata dict.

    Values are often stored as meters when unit is missing; we convert m -> µm.
    """
    px: Dict[str, Optional[float]] = {"X": None, "Y": None}

    for d in _walk(meta):
        dist_id = d.get("@Id") or d.get("Id")
        if dist_id not in ("X", "Y"):
            continue

        val = d.get("Value") or d.get("@Value")
        unit = d.get("Unit") or d.get("@Unit")

        if isinstance(val, dict):
            val = val.get("#text") or val.get("text") or val.get("Value")

        if val is None:
            continue

        try:
            fval = float(str(val).strip())
        except Exception:
            continue

        if unit in (None, "", "m", "meter", "metre"):
            v_um = fval * 1e6
        elif unit in ("µm", "um"):
            v_um = fval
        elif unit == "nm":
            v_um = fval / 1000.0
        else:
            v_um = fval

        # Less sensitive rounding to avoid creating too many acq-* folders
        px[dist_id] = round(v_um, 3)

    return px["X"], px["Y"]


def make_acq_signature(meta: dict) -> Optional[Tuple]:
    """Build an acquisition signature for grouping into acq-1, acq-2, ...

    Less sensitive signature:
        (microscope_name, pixel_x_um, pixel_y_um)
    """
    microscope = get_microscope_name(meta)
    if microscope is None:
        return None

    px, py = get_pixel_xy_um(meta)
    return (microscope, px, py)


def parse_one_file(czi_path: Path) -> Optional[dict]:
    """Parse one CZI and extract fields required to build the sourcedata tree."""
    meta = get_czi_metadata(czi_path)

    subject = get_subject_from_filename(czi_path.stem)
    if subject is None:
        return None

    sample = get_sample_from_filename(czi_path.stem)
    if sample is None:
        return None

    dt_str = get_best_datetime_for_session(meta)
    if dt_str is None:
        return None

    ses = ses_from_any_datetime(dt_str)
    if ses is None:
        return None

    sig = make_acq_signature(meta)
    if sig is None:
        return None

    return {
        "src": czi_path,
        "subject": subject,
        "sample": sample,
        "ses": ses,
        "acq_sig": sig,
    }


def move_file(src: Path, dst: Path) -> None:
    """Create a symlink at dst pointing to src (BIDS-named alias)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    dst.symlink_to(src.resolve())


def organize_sourcedata(input_root: Path, sourcedata_dir: Path, workers: int = 8) -> None:
    """Organize CZIs recursively under input_root into a sourcedata BIDS-like tree."""
    czis = sorted(Path(input_root).rglob("*.czi"))
    if not czis:
        print(f"[INFO] No .czi files found under {input_root}")
        return

    records: List[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(parse_one_file, czi): czi for czi in czis}
        for fut in as_completed(futs):
            czi = futs[fut]
            rec = fut.result()
            if rec is None:
                print(f"[WARN] Missing required fields (subject/sample/ses/acq): {czi}")
                continue
            records.append(rec)

    if not records:
        print("[INFO] No usable files.")
        return

    subjects = sorted({r["subject"] for r in records})
    subject_to_sub = {sid: f"sub-{i:02d}" for i, sid in enumerate(subjects, start=1)}

    group_sigs: Dict[Tuple[str, str, str], List[Tuple]] = {}
    for r in records:
        sub = subject_to_sub[r["subject"]]
        key = (sub, r["ses"], r["sample"])
        group_sigs.setdefault(key, [])
        if r["acq_sig"] not in group_sigs[key]:
            group_sigs[key].append(r["acq_sig"])

    for key in group_sigs:
        group_sigs[key] = sorted(group_sigs[key], key=lambda x: str(x))

    run_counter: Dict[Tuple[str, str, str, int], int] = {}

    def sort_key(r: dict):
        sub = subject_to_sub[r["subject"]]
        key3 = (sub, r["ses"], r["sample"])
        acq_num = group_sigs[key3].index(r["acq_sig"]) + 1
        return (sub, r["ses"], r["sample"], acq_num, r["src"].name)

    for r in sorted(records, key=sort_key):
        sub = subject_to_sub[r["subject"]]
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