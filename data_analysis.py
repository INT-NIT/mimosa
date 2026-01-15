from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Dict, List, Tuple
import re

import pandas as pd
import matplotlib.pyplot as plt

from pylibCZIrw import czi as czirw


# -----------------------
# Config
# -----------------------
INPUT_ROOT = Path("/DATA/mimosa/original-dataset")   # folder containing the 7 subject folders
OUTPUT_DIR = Path("/DATA/mimosa/mimosa/metadata_audit_out") # where to save csv + plots


# -----------------------
# Helpers
# -----------------------
def as_text(v: Any) -> Optional[str]:
    """Normalize metadata values to a usable string."""
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


def normalize_path(p: Optional[str]) -> Optional[str]:
    """
    Make paths comparable across files by removing numeric indexes:
      Track[0] -> Track[*]
      Channel[12] -> Channel[*]
    """
    if p is None:
        return None
    # replace [123] by [*]
    p = re.sub(r"\[\d+\]", "[*]", p)
    return p


def get_czi_metadata(czi_path: Path) -> dict:
    """Read and return CZI metadata as a Python dictionary using pylibCZIrw."""
    with czirw.open_czi(str(czi_path)) as doc:
        return doc.metadata


# -----------------------
# Filename heuristics
# -----------------------
def subject_from_filename(stem: str) -> Optional[str]:
    tokens = [t for t in stem.replace("-", "_").split("_") if t]
    for t in tokens:
        if any(ch.isalpha() for ch in t) and any(ch.isdigit() for ch in t) and 6 <= len(t) <= 40:
            return t
    return None


def sample_from_filename(stem: str) -> Optional[str]:
    tokens = [t for t in stem.replace("-", "_").split("_") if t]
    subj = subject_from_filename(stem)
    start = 0
    if subj and subj in tokens:
        start = tokens.index(subj) + 1
    for t in tokens[start:]:
        if t.isalpha() and 1 <= len(t) <= 12:
            return "Cx" if t.lower() == "cortex" else t
    return None


# -----------------------
# Field finders (by suffix)
# -----------------------
FIELD_SUFFIXES = {
    "AcquisitionDateAndTime": ("/acquisitiondateandtime",),
    "StartTime": ("/starttime",),
    "SessionName": ("/@sessionname", "/sessionname"),
    "CreationDate": ("/creationdate",),
    "ImageName": ("/imagename", "/@imagename"),
}


def find_first_by_suffix(meta: dict, suffixes: Tuple[str, ...]) -> Tuple[Optional[str], Optional[str]]:
    """Return (value, path) for the first match found."""
    for p, v in walk_all(meta):
        pl = p.lower()
        if any(pl.endswith(sfx) for sfx in suffixes):
            txt = as_text(v)
            if txt:
                return txt, p
    return None, None


def extract_session_best(meta: dict) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Return (value, path, source_key) using strict priority:
      1) AcquisitionDateAndTime
      2) StartTime
      3) SessionName
      4) CreationDate
      5) ImageName
    """
    order = ["AcquisitionDateAndTime", "StartTime", "SessionName", "CreationDate", "ImageName"]
    for key in order:
        val, path = find_first_by_suffix(meta, FIELD_SUFFIXES[key])
        if val is not None:
            return val, path, key
    return None, None, None


def extract_sessionname_anywhere(meta: dict) -> Tuple[Optional[str], Optional[str]]:
    """
    Return (SessionName_value, path) even if it is not selected as best session.
    Useful to know if SessionName exists at all.
    """
    val, path = find_first_by_suffix(meta, FIELD_SUFFIXES["SessionName"])
    return val, path


def extract_microscope(meta: dict) -> Tuple[Optional[str], Optional[str]]:
    """Find microscope: a dict with Id='Microscope' and Name='...'."""
    for p, v in walk_all(meta):
        if isinstance(v, dict):
            dev_id = as_text(v.get("@Id") or v.get("Id"))
            if dev_id == "Microscope":
                nm = as_text(v.get("@Name") or v.get("Name"))
                if nm:
                    return nm, p
    return None, None


def extract_pixel_xy_um(meta: dict) -> Tuple[Optional[float], Optional[float], Optional[str], Optional[str]]:
    """
    Look for Distance nodes with Id X/Y.
    Return (px_um, py_um, path_x, path_y)
    """
    px = py = None
    path_x = path_y = None

    for p, v in walk_all(meta):
        if not isinstance(v, dict):
            continue
        dist_id = as_text(v.get("@Id") or v.get("Id"))
        if dist_id not in ("X", "Y"):
            continue

        val_txt = as_text(v.get("Value") or v.get("@Value") or v.get("#text") or v.get("text"))
        unit_txt = as_text(v.get("Unit") or v.get("@Unit"))
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

        v_um = round(v_um, 6)
        if dist_id == "X":
            px, path_x = v_um, p
        else:
            py, path_y = v_um, p

    return px, py, path_x, path_y


def extract_channel_names(meta: dict) -> Tuple[List[str], List[str]]:
    """
    Extract channel names + the paths used.
    Paths are normalized later (Track[0] -> Track[*]).
    """
    names: List[str] = []
    paths: List[str] = []
    for p, v in walk_all(meta):
        if isinstance(v, dict) and ("channel" in p.lower()):
            nm = as_text(v.get("@Name") or v.get("Name"))
            if nm and 1 <= len(nm) <= 32 and nm not in names:
                names.append(nm)
                paths.append(p + ("/@Name" if "@Name" in v else "/Name"))
    return names, paths


# -----------------------
# Audit per file
# -----------------------
def audit_one_file(czi_path: Path) -> Dict[str, Any]:
    meta = get_czi_metadata(czi_path)

    subj = subject_from_filename(czi_path.stem)
    samp = sample_from_filename(czi_path.stem)

    sess_val, sess_path, sess_src = extract_session_best(meta)
    sessname_val, sessname_path = extract_sessionname_anywhere(meta)

    mic, mic_path = extract_microscope(meta)
    px, py, px_path, py_path = extract_pixel_xy_um(meta)
    chans, chan_paths = extract_channel_names(meta)

    # normalize paths to ignore Track[0]/Track[1]/...
    sess_path_n = normalize_path(sess_path)
    mic_path_n = normalize_path(mic_path)
    px_path_n = normalize_path(px_path)
    py_path_n = normalize_path(py_path)

    chan_paths_n = [normalize_path(x) for x in chan_paths if x]
    chan_paths_n = [x for x in chan_paths_n if x]  # drop None
    chans_paths_joined = ";".join(sorted(set(chan_paths_n))) if chan_paths_n else None

    return {
        "file": str(czi_path),
        "filename": czi_path.name,

        "subject_from_filename": subj,
        "sample_from_filename": samp,

        "Session_present": sess_val is not None,
        "Session_value": sess_val,
        "Session_path": sess_path,
        "Session_path_norm": sess_path_n,
        "Session_source": sess_src,

        "SessionName_present": sessname_val is not None,
        "SessionName_value": sessname_val,
        "SessionName_path": sessname_path,
        "SessionName_path_norm": normalize_path(sessname_path),

        "Microscope_present": mic is not None,
        "Microscope_value": mic,
        "Microscope_path_norm": mic_path_n,

        "PixelSize_present": (px is not None) and (py is not None),
        "PixelSizeX_um": px,
        "PixelSizeY_um": py,
        "PixelSizeX_path_norm": px_path_n,
        "PixelSizeY_path_norm": py_path_n,

        "Channels_present": len(chans) > 0,
        "Channels_count": len(chans),
        "Channels_names": ",".join(chans) if chans else None,
        "Channels_paths_norm": chans_paths_joined,
    }


# -----------------------
# Plots (2 only)
# -----------------------
def save_two_plots(df: pd.DataFrame, outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    total = len(df)

    # ---- Plot 1: coverage of needed fields
    needed = {
        "Subject (from filename)": df["subject_from_filename"].notna().sum(),
        "Sample (from filename)": df["sample_from_filename"].notna().sum(),
        "Session (best of meta)": df["Session_present"].sum(),
        "SessionName exists": df["SessionName_present"].sum(),
        "Microscope": df["Microscope_present"].sum(),
        "PixelSize (X+Y)": df["PixelSize_present"].sum(),
        "Channels": df["Channels_present"].sum(),
    }

    plt.figure()
    pd.Series(needed).sort_values(ascending=False).plot(kind="bar")
    plt.title(f"Coverage of needed fields (N={total} files)")
    plt.ylabel("Number of files where field is present")
    plt.tight_layout()
    plt.savefig(outdir / "coverage_needed_fields.png", dpi=150)
    plt.close()

    # ---- Plot 2: differences = session SOURCE variability (not Track index paths)
    # This tells you: are sessions usually extracted from AcquisitionDateAndTime? StartTime? SessionName?
    vc = df["Session_source"].fillna("NONE").value_counts()

    plt.figure()
    vc.plot(kind="bar")
    plt.title("Session inconsistency: which metadata field provides the session?")
    plt.ylabel("Number of files")
    plt.tight_layout()
    plt.savefig(outdir / "session_source_distribution.png", dpi=150)
    plt.close()


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    czis = sorted(INPUT_ROOT.rglob("*.czi"))
    if not czis:
        print(f"[INFO] No .czi found under: {INPUT_ROOT}")
        return

    rows: List[Dict[str, Any]] = []
    skipped = 0

    for czi in czis:
        try:
            rows.append(audit_one_file(czi))
        except Exception as e:
            skipped += 1
            rows.append({"file": str(czi), "filename": czi.name, "error": str(e)})

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_DIR / "summary_files.csv", index=False)

    df_ok = df[df.get("error").isna()] if "error" in df.columns else df
    if len(df_ok) == 0:
        print(f"[INFO] No usable files for plots. Skipped: {skipped}")
        return

    save_two_plots(df_ok, OUTPUT_DIR)

    # Quick debug: how many different normalized channel paths?
    ch_unique = set()
    for v in df_ok["Channels_paths_norm"].dropna().astype(str):
        for part in v.split(";"):
            part = part.strip()
            if part:
                ch_unique.add(part)

    print("[OK] Audit done.")
    print(f"  - CSV: {OUTPUT_DIR / 'summary_files.csv'}")
    print(f"  - Plot1: {OUTPUT_DIR / 'coverage_needed_fields.png'}")
    print(f"  - Plot2: {OUTPUT_DIR / 'session_source_distribution.png'}")
    print(f"  - Unique normalized channel paths: {len(ch_unique)}")
    if skipped:
        print(f"  - Skipped (errors): {skipped}")


if __name__ == "__main__":
    main()
