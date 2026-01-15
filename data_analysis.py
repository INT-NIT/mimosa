from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Dict, List, Tuple
from collections import Counter

import pandas as pd
import matplotlib.pyplot as plt

from pylibCZIrw import czi as czirw


# -----------------------
# Config
# -----------------------
INPUT_ROOT = Path("/DATA/mimosa/original-dataset")   # folder containing the 7 subject folders
OUTPUT_DIR = Path("/DATA/mimosa/metadata_audit_out") # where to save csv + plots


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


def extract_session_best(meta: dict) -> Tuple[Optional[str], Optional[str]]:
    """
    Return (value, source_field_path) using a strict priority:
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
            return val, path
    return None, None


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
    """Extract channel names + the paths used."""
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

    sess_val, sess_path = extract_session_best(meta)

    mic, mic_path = extract_microscope(meta)
    px, py, px_path, py_path = extract_pixel_xy_um(meta)
    chans, chan_paths = extract_channel_names(meta)

    return {
        "file": str(czi_path),
        "filename": czi_path.name,

        "subject_from_filename": subj,
        "sample_from_filename": samp,

        "Session_present": sess_val is not None,
        "Session_value": sess_val,
        "Session_path": sess_path,

        "Microscope_present": mic is not None,
        "Microscope_value": mic,
        "Microscope_path": mic_path,

        "PixelSize_present": (px is not None) and (py is not None),
        "PixelSizeX_um": px,
        "PixelSizeY_um": py,
        "PixelSizeX_path": px_path,
        "PixelSizeY_path": py_path,

        "Channels_present": len(chans) > 0,
        "Channels_count": len(chans),
        "Channels_names": ",".join(chans) if chans else None,
        "Channels_paths": ";".join(chan_paths) if chan_paths else None,
    }


# -----------------------
# Plots
# -----------------------
def save_two_plots(df: pd.DataFrame, outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)

    # ---- Plot 1: similarity / coverage of needed fields
    needed = {
        "Subject (from filename)": df["subject_from_filename"].notna().sum(),
        "Sample (from filename)": df["sample_from_filename"].notna().sum(),
        "Session (best of meta)": df["Session_present"].sum(),
        "Microscope": df["Microscope_present"].sum(),
        "PixelSize (X+Y)": df["PixelSize_present"].sum(),
        "Channels": df["Channels_present"].sum(),
    }
    total = len(df)

    plt.figure()
    pd.Series({k: v for k, v in needed.items()}).sort_values(ascending=False).plot(kind="bar")
    plt.title(f"Similarity / coverage of needed fields (N={total} files)")
    plt.ylabel("Number of files where field is present")
    plt.tight_layout()
    plt.savefig(outdir / "similarity_needed_fields.png", dpi=150)
    plt.close()

    # ---- Plot 2: differences = how many different PATHS were used to find each field
    # (more unique paths => less consistent across datasets)
    path_variability: Dict[str, int] = {}

    def n_unique(series: pd.Series) -> int:
        vals = series.dropna().astype(str).unique().tolist()
        return len(vals)

    path_variability["Session_path"] = n_unique(df["Session_path"])
    path_variability["Microscope_path"] = n_unique(df["Microscope_path"])
    path_variability["PixelSizeX_path"] = n_unique(df["PixelSizeX_path"])
    path_variability["PixelSizeY_path"] = n_unique(df["PixelSizeY_path"])

    # Channels_paths can contain multiple paths separated by ';'
    ch_paths = []
    for v in df["Channels_paths"].dropna().astype(str):
        ch_paths.extend([x.strip() for x in v.split(";") if x.strip()])
    path_variability["Channels_paths"] = len(set(ch_paths))

    plt.figure()
    pd.Series(path_variability).sort_values(ascending=False).plot(kind="bar")
    plt.title("Differences / inconsistency: number of unique metadata paths used")
    plt.ylabel("Unique paths count (higher = more inconsistent)")
    plt.tight_layout()
    plt.savefig(outdir / "differences_paths.png", dpi=150)
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

    # Keep only rows without errors for plotting
    df_ok = df[df.get("error").isna()] if "error" in df.columns else df
    if len(df_ok) == 0:
        print(f"[INFO] No usable files for plots. Skipped: {skipped}")
        return

    save_two_plots(df_ok, OUTPUT_DIR)

    print("[OK] Audit done.")
    print(f"  - CSV: {OUTPUT_DIR / 'summary_files.csv'}")
    print(f"  - Plot1: {OUTPUT_DIR / 'similarity_needed_fields.png'}")
    print(f"  - Plot2: {OUTPUT_DIR / 'differences_paths.png'}")
    if skipped:
        print(f"  - Skipped (errors): {skipped}")


if __name__ == "__main__":
    main()
