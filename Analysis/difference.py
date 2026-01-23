from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Dict, List, Tuple
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import re

from pylibCZIrw import czi as czirw


# -----------------------
# Config
# -----------------------
INPUT_ROOT = Path("/DATA/mimosa/original-dataset")
OUTPUT_DIR = Path("/DATA/mimosa/metadata_meaningful_out")
WORKERS = 8

# Keep only differences that are stable inside the subject
MIN_IN_SUBJECT = 3      # value must appear in >= 3 files of the subject
MAX_OUTSIDE = 1         # value can appear in <= 1 file outside this subject

# Limit number of differences written per subject
TOP_K_PER_SUBJECT = 30

# Normalize list indices: Distance[0] -> Distance[*]
IDX_RE = re.compile(r"\[\d+\]")

# Filter useless/noisy values
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
DATE_RE = re.compile(r"(20\d{2})[-/]?(\d{2})[-/]?(\d{2})")
PATH_BAD = ("\\", "/DATA/", "/home/", "C:\\")

# -----------------------
# Helpers
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


def canon_path(p: str) -> str:
    return IDX_RE.sub("[*]", p)


def subject_folder_of_file(czi_path: Path) -> str:
    # the subject folder is the direct child of INPUT_ROOT
    for parent in czi_path.parents:
        if parent.parent == INPUT_ROOT:
            return parent.name
    return "UNKNOWN_SUBJECT"


def get_meta(czi_path: Path) -> dict:
    with czirw.open_czi(str(czi_path)) as doc:
        return doc.metadata


def normalize_value(field: str, value: str) -> Optional[str]:
    """
    Make values comparable and 'meaningful':
    - normalize dates to YYYYMMDD if present
    - keep short strings, avoid file paths, UUID, huge blobs
    """
    v = value.strip()
    if len(v) < 2 or len(v) > 180:
        return None
    if UUID_RE.search(v):
        return None
    if any(b in v for b in PATH_BAD):
        return None

    # normalize date patterns
    m = DATE_RE.search(v)
    if m:
        y, mo, d = m.group(1), m.group(2), m.group(3)
        return f"{y}{mo}{d}"

    # collapse spaces
    v = re.sub(r"\s+", " ", v).strip()

    return v


# -----------------------
# What we actually care about (whitelist)
# -----------------------
# We match by *field name suffix* (not full exact path)
# and then we will keep the canonicalized path so you can see where it came from.
TARGET_SUFFIXES: Dict[str, Tuple[str, ...]] = {
    "AcquisitionDateAndTime": ("/acquisitiondateandtime",),
    "StartTime": ("/starttime",),
    "SessionName": ("/sessionname", "/@sessionname"),
    "CreationDate": ("/creationdate",),
    "MicroscopeDevice": ("/hardwaresetting/configuration/device[*]",),  # we’ll still check content
    "Distance": ("/distance",),  # for pixel sizes (X/Y) and sometimes Z
    "ExposureTime": ("/exposuretime",),
    "Objective": ("/objective", "/objectivename", "/@objectivename"),
    "ChannelName": ("/channel",),  # we’ll filter by having @Name/Name
}


def collect_target_facts(meta: dict) -> List[Tuple[str, str, str]]:
    """
    Return list of facts (category, canonical_path, normalized_value)
    Only for meaningful target fields.
    """
    facts: List[Tuple[str, str, str]] = []

    for p, v in walk_all(meta):
        pl = p.lower()
        cp = canon_path(p)

        # ---- 1) Session/date fields
        for cat in ["AcquisitionDateAndTime", "StartTime", "SessionName", "CreationDate"]:
            if any(pl.endswith(sfx) for sfx in TARGET_SUFFIXES[cat]):
                txt = as_text(v)
                if not txt:
                    continue
                nv = normalize_value(cat, txt)
                if nv:
                    facts.append((cat, cp, nv))

        # ---- 2) Microscope name: look for device dict with Id=Microscope
        # We detect at dict level (so check v is dict)
        if isinstance(v, dict):
            dev_id = as_text(v.get("@Id") or v.get("Id"))
            if dev_id == "Microscope":
                nm = as_text(v.get("@Name") or v.get("Name"))
                if nm:
                    nv = normalize_value("Microscope", nm)
                    if nv:
                        facts.append(("Microscope", cp, nv))

        # ---- 3) ExposureTime (often numeric but meaningful)
        if pl.endswith("/exposuretime"):
            txt = as_text(v)
            if txt:
                # keep only if not crazy long
                nv = normalize_value("ExposureTime", txt)
                if nv:
                    facts.append(("ExposureTime", cp, nv))

        # ---- 4) Objective (if exists)
        if pl.endswith("/objective") or pl.endswith("/objectivename") or pl.endswith("/@objectivename"):
            txt = as_text(v)
            if txt:
                nv = normalize_value("Objective", txt)
                if nv:
                    facts.append(("Objective", cp, nv))

        # ---- 5) Channel names: dict with Name/@Name and path contains channel
        if isinstance(v, dict) and "channel" in pl:
            nm = as_text(v.get("@Name") or v.get("Name"))
            if nm:
                nv = normalize_value("ChannelName", nm)
                if nv:
                    facts.append(("ChannelName", cp + ("/@Name" if "@Name" in v else "/Name"), nv))

        # ---- 6) Distance nodes: dict with Id X/Y/Z and Value + Unit
        if isinstance(v, dict) and pl.endswith("/distance"):
            dist_id = as_text(v.get("@Id") or v.get("Id"))
            val = as_text(v.get("Value") or v.get("@Value") or v.get("#text") or v.get("text"))
            unit = as_text(v.get("Unit") or v.get("@Unit") or v.get("DefaultUnitFormat"))
            if dist_id and val:
                # store as "X:3.24e-07 m" style normalized
                raw = f"{dist_id}:{val}{(' ' + unit) if unit else ''}"
                nv = normalize_value("Distance", raw)
                if nv:
                    facts.append(("Distance", cp, nv))

    return facts


# -----------------------
# Per file worker
# -----------------------
def analyze_one_file(czi_path: Path) -> Tuple[str, str, List[Tuple[str, str, str]]]:
    meta = get_meta(czi_path)
    subj = subject_folder_of_file(czi_path)
    facts = collect_target_facts(meta)
    return subj, czi_path.name, facts


# -----------------------
# Main
# -----------------------
def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    czis = sorted(INPUT_ROOT.rglob("*.czi"))
    if not czis:
        print(f"[INFO] No .czi found under {INPUT_ROOT}")
        return

    # subject -> Counter(fact) where fact = (category, value)
    subj_fact_counts: Dict[str, Counter] = defaultdict(Counter)
    # subject -> examples for fact
    subj_fact_examples: Dict[str, Dict[Tuple[str, str], List[str]]] = defaultdict(lambda: defaultdict(list))
    # subject -> presence of category (how many files have at least 1 fact for that category)
    subj_cat_file_presence: Dict[str, Counter] = defaultdict(Counter)
    # subject -> number of files
    subj_nfiles: Counter = Counter()

    errors: List[Tuple[str, str]] = []

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(analyze_one_file, czi): czi for czi in czis}
        for fut in as_completed(futs):
            czi = futs[fut]
            try:
                subj, fname, facts = fut.result()
            except Exception as e:
                errors.append((str(czi), str(e)))
                continue

            subj_nfiles[subj] += 1

            # track which categories appear in this file at least once
            cats_in_file = set()

            for cat, _path, value in facts:
                key = (cat, value)
                subj_fact_counts[subj][key] += 1
                cats_in_file.add(cat)
                ex_list = subj_fact_examples[subj][key]
                if len(ex_list) < 3:
                    ex_list.append(fname)

            for cat in cats_in_file:
                subj_cat_file_presence[subj][cat] += 1

    # Build global counts for each (cat,value)
    global_counts: Counter = Counter()
    for subj, ctr in subj_fact_counts.items():
        global_counts.update(ctr)

    # For each subject: keep "meaningful unique-ish" facts:
    # frequent inside subject, rare outside subject
    rows_diff: List[Dict[str, Any]] = []
    rows_summary: List[Dict[str, Any]] = []

    for subj in sorted(subj_fact_counts.keys()):
        nfiles = subj_nfiles[subj]
        ctr = subj_fact_counts[subj]

        # summary: presence ratios for categories
        for cat in sorted(TARGET_SUFFIXES.keys() | {"Microscope"}):
            present_files = subj_cat_file_presence[subj].get(cat, 0)
            rows_summary.append({
                "subject_folder": subj,
                "category": cat,
                "files_with_category": present_files,
                "total_files_subject": nfiles,
                "coverage_ratio": round(present_files / nfiles, 3) if nfiles else 0.0
            })

        # differences
        diffs: List[Tuple[int, int, str, str]] = []
        # store (in_count, outside_count, cat, value)
        for (cat, value), in_count in ctr.items():
            outside = global_counts[(cat, value)] - in_count
            if in_count >= MIN_IN_SUBJECT and outside <= MAX_OUTSIDE:
                diffs.append((in_count, outside, cat, value))

        diffs.sort(key=lambda x: (x[0], -x[1]), reverse=True)
        diffs = diffs[:TOP_K_PER_SUBJECT]

        for in_count, outside, cat, value in diffs:
            examples = ";".join(subj_fact_examples[subj][(cat, value)])
            rows_diff.append({
                "subject_folder": subj,
                "category": cat,
                "value": value,
                "count_in_subject_files": in_count,
                "count_outside_subject": outside,
                "example_files": examples
            })

    # write csv
    out_diffs = OUTPUT_DIR / "meaningful_differences.csv"
    out_summary = OUTPUT_DIR / "coverage_by_subject.csv"
    out_errors = OUTPUT_DIR / "errors.csv"

    with out_diffs.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "subject_folder", "category", "value",
            "count_in_subject_files", "count_outside_subject",
            "example_files"
        ])
        w.writeheader()
        w.writerows(rows_diff)

    with out_summary.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "subject_folder", "category",
            "files_with_category", "total_files_subject", "coverage_ratio"
        ])
        w.writeheader()
        w.writerows(rows_summary)

    with out_errors.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["file", "error"])
        w.writeheader()
        w.writerows([{"file": a, "error": b} for a, b in errors])

    print("[OK] Meaningful subject differences done.")
    print(f"  - {out_diffs}")
    print(f"  - {out_summary}")
    print(f"  - {out_errors}")
    if errors:
        print(f"  - errors: {len(errors)}")


if __name__ == "__main__":
    main()