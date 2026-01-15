from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Dict, List, Tuple
from collections import Counter, defaultdict
import re

import pandas as pd
import matplotlib.pyplot as plt

from pylibCZIrw import czi as czirw


# -----------------------
# Config (change this)
# -----------------------
INPUT_ROOT = Path("/DATA/mimosa/original-dataset")   # folder that contains the 7 subject folders
OUTPUT_DIR = Path("/DATA/mimosa/metadata_audit_out") # where to save csv + plots


# -----------------------
# Generic helpers
# -----------------------
def as_text(v: Any) -> Optional[str]:
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
# Target fields to audit
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


def extract_microscope(meta: dict) -> Tuple[Optional[str], Optional[str]]:
    """
    Find microscope name like: a dict with Id='Microscope' and Name='...'
    Return (value, path_to_dict)
    """
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
    Extract channel names by searching dicts that look like channels and have @Name/Name.
    Return (unique_names, paths_used_for_names)
    """
    names: List[str] = []
    paths: List[str] = []
    for p, v in walk_all(meta):
        if isinstance(v, dict):
            nm = as_text(v.get("@Name") or v.get("Name"))
            if nm and 1 <= len(nm) <= 32:
                # heuristic: keep only likely channel nodes
                if ("channel" in p.lower()) and (nm not in names):
                    names.append(nm)
                    paths.append(p + ("/@Name" if "@Name" in v else "/Name"))
    return names, paths


# -----------------------
# Main audit per file
# -----------------------
def audit_one_file(czi_path: Path) -> Dict[str, Any]:
    meta = get_czi_metadata(czi_path)

    subj = subject_from_filename(czi_path.stem)
    samp = sample_from_filename(czi_path.stem)

    out: Dict[str, Any] = {
        "file": str(czi_path),
        "filename": czi_path.name,
        "subject_from_filename": subj,
        "sample_from_filename": samp,
    }

    # Date/session-related fields
    for field, suffixes in FIELD_SUFFIXES.items():
        val, path = find_first_by_suffix(meta, suffixes)
        out[f"{field}_present"] = val is not None
        out[f"{field}_path"] = path
        out[f"{field}_value"] = val

    # Microscope
    mic, mic_path = extract_microscope(meta)
    out["Microscope_present"] = mic is not None
    out["Microscope_path"] = mic_path
    out["Microscope_value"] = mic

    # Pixel size
    px, py, px_path, py_path = extract_pixel_xy_um(meta)
    out["PixelSizeX_present"] = px is not None
    out["PixelSizeY_present"] = py is not None
    out["PixelSizeX_um"] = px
    out["PixelSizeY_um"] = py
    out["PixelSizeX_path"] = px_path
    out["PixelSizeY_path"] = py_path

    # Channels
    chans, chan_paths = extract_channel_names(meta)
    out["Channels_present"] = len(chans) > 0
    out["Channels_count"] = len(chans)
    out["Channels_names"] = ",".join(chans) if chans else None
    out["Channels_paths"] = ";".join(chan_paths) if chan_paths else None

    return out


# -----------------------
# Reporting + plots
# -----------------------
def save_plots(df: pd.DataFrame, outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)

    # 1) Presence bar chart for key fields
    presence_cols = [c for c in df.columns if c.endswith("_present")]
    pres = df[presence_cols].sum().sort_values(ascending=False)

    plt.figure()
    pres.plot(kind="bar")
    plt.title("How many files contain each field (presence)")
    plt.ylabel("Number of files")
    plt.tight_layout()
    plt.savefig(outdir / "presence_counts.png", dpi=150)
    plt.close()

    # 2) Channels count distribution
    if "Channels_count" in df.columns:
        plt.figure()
        df["Channels_count"].fillna(0).astype(int).value_counts().sort_index().plot(kind="bar")
        plt.title("Distribution of number of channels per file")
        plt.xlabel("Channels_count")
        plt.ylabel("Number of files")
        plt.tight_layout()
        plt.savefig(outdir / "channels_count_distribution.png", dpi=150)
        plt.close()

    # 3) Session-like values distribution (AcquisitionDateAndTime / StartTime / SessionName)
    for key in ["AcquisitionDateAndTime_value", "StartTime_value", "SessionName_value", "CreationDate_value"]:
        if key in df.columns:
            vc = df[key].dropna().astype(str).value_counts().head(20)
            if len(vc) > 0:
                plt.figure()
                vc.plot(kind="bar")
                plt.title(f"Top values: {key} (top 20)")
                plt.ylabel("Number of files")
                plt.tight_layout()
                plt.savefig(outdir / f"top_values_{key}.png", dpi=150)
                plt.close()


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    czis = sorted(INPUT_ROOT.rglob("*.czi"))
    if not czis:
        print(f"[INFO] No .czi found under: {INPUT_ROOT}")
        return

    rows: List[Dict[str, Any]] = []
    for czi in czis:
        try:
            rows.append(audit_one_file(czi))
        except Exception as e:
            rows.append({"file": str(czi), "filename": czi.name, "error": str(e)})

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_DIR / "summary_files.csv", index=False)

    # Frequency of paths (where fields are located)
    path_cols = [c for c in df.columns if c.endswith("_path") or c.endswith("_paths")]
    path_counter = Counter()
    for col in path_cols:
        for v in df[col].dropna().astype(str):
            # Channels_paths is ; separated
            for part in v.split(";"):
                part = part.strip()
                if part:
                    path_counter[(col, part)] += 1
    paths_df = pd.DataFrame(
        [{"column": k[0], "path": k[1], "count": c} for k, c in path_counter.items()]
    ).sort_values(["column", "count"], ascending=[True, False])
    paths_df.to_csv(OUTPUT_DIR / "paths_frequency.csv", index=False)

    # Frequency of values (sessions, microscope, etc.)
    value_cols = [c for c in df.columns if c.endswith("_value") or c in ["PixelSizeX_um", "PixelSizeY_um", "Channels_names"]]
    val_counter = Counter()
    for col in value_cols:
        for v in df[col].dropna().astype(str):
            val_counter[(col, v)] += 1
    vals_df = pd.DataFrame(
        [{"column": k[0], "value": k[1], "count": c} for k, c in val_counter.items()]
    ).sort_values(["column", "count"], ascending=[True, False])
    vals_df.to_csv(OUTPUT_DIR / "values_frequency.csv", index=False)

    save_plots(df, OUTPUT_DIR)

    print("[OK] Audit done.")
    print(f"  - {OUTPUT_DIR / 'summary_files.csv'}")
    print(f"  - {OUTPUT_DIR / 'paths_frequency.csv'}")
    print(f"  - {OUTPUT_DIR / 'values_frequency.csv'}")
    print(f"  - plots: {OUTPUT_DIR}/*.png")


if __name__ == "__main__":
    main()