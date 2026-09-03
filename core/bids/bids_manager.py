import os
import pathlib as Path
import re
import glob
import shutil 
from core.bids import bids_metadata as bmeta
SESSION_ORDER_BY_ROOT = {}

class BIDSSession:
    """
    Assigns BIDS numbers (ses, acq ) to each CZI file ,
    it remembers what it has already seen (ses, acq) and automatically inceremnts nulbers for each file .
    """

    def __init__(self, bids_root_path: str):
        self.bids_root_path = bids_root_path
        self._ses_map = {}   
        self._session_order = SESSION_ORDER_BY_ROOT.get(self.bids_root_path, {})
        
    def _get_last_index(self, entity: str, sub_path: str = None) -> int:
        """scan folders to find existing entity numbers so we can calculate the next index for session"""
        search_root = sub_path if sub_path else self.bids_root_path
        pattern = os.path.join(search_root, "**", f"*_{entity}-*")
        files = glob.glob(pattern, recursive=True)
        numbers = []
        for f in files:
            match = re.search(rf"_{entity}-(\d+)", os.path.basename(f))
            if match:
                numbers.append(int(match.group(1)))
        return numbers

    def _session_index_for_time(self, sub: str, acq_time: str) -> str:
        """
        Assign one session per acquisition date.
        If YAML slice order exists, use it to number sessions.
        """
        if sub not in self._ses_map:
            self._ses_map[sub] = {}

        session_key = str(acq_time).split("T")[0]

        if sub in self._session_order and session_key in self._session_order[sub]:
            self._ses_map[sub][session_key] = self._session_order[sub][session_key]
            return self._session_order[sub][session_key]

        if session_key not in self._ses_map[sub]:
            next_idx = len(self._ses_map[sub]) + 1
            self._ses_map[sub][session_key] = f"{next_idx:02d}"

        return self._ses_map[sub][session_key]



    def get_bids_info(self, summary_meta, czi_id, section_idx=None, sample_id=None):
        sub      = summary_meta.get("sub")
        acq_time = summary_meta.get("acq_time")
        acq_sig  = summary_meta.get("acq_sig", "Unknown")

        ses_idx = self._session_index_for_time(sub, acq_time)

        return {
            "sub":            sub,
            "ses":            ses_idx,
            "acq_time":       acq_time,
            "acq_sig":        acq_sig,
            "sample":         sample_id,
            "chunk":          section_idx,
            "bids_root_path": self.bids_root_path,
        }

def build_session_order_from_acq_time(cfg: dict, bids_root_path: str) -> dict:
    """Number sessions by real acquisition date.

    Opens each CZI listed in cfg, reads its acquisition time, groups files by
    day per subject, sorts the days ascending and assigns ses-01, ses-02, ...
    (earliest day = ses-01). All CZIs scanned on the same day share the session.
    The result is stored in SESSION_ORDER_BY_ROOT and used by BIDSSession.
    """
    from core.bids.czi_reader import MimosaReader  # local import avoids a cycle

    bids_root_path = os.path.abspath(bids_root_path)
    dates_by_sub = {}
    for entry in cfg.get("samples", {}).get("entries", []):
        subject_path = entry.get("path")
        for sample in entry.get("samples", []):
            if not isinstance(sample, dict):
                continue
            for file_entry in (sample.get("files") or []):
                if not isinstance(file_entry, dict):
                    continue
                filename = file_entry.get("filename")
                if not filename or not subject_path:
                    continue
                full_path = os.path.join(subject_path, filename)
                if not os.path.exists(full_path):
                    continue
                try:
                    with MimosaReader(full_path) as reader:
                        summary = reader.get_summary()
                except Exception as exc:
                    print(f"WARNING: cannot read acq_time from {filename}: {exc}")
                    continue
                sub = summary.get("sub")
                acq_time = summary.get("acq_time")
                if not sub or not acq_time:
                    continue
                date_key = str(acq_time).split("T")[0]
                dates_by_sub.setdefault(sub, set()).add(date_key)

    session_order = {
        sub: {date_key: f"{idx + 1:02d}"
              for idx, date_key in enumerate(sorted(dates))}
        for sub, dates in dates_by_sub.items()
    }
    SESSION_ORDER_BY_ROOT[bids_root_path] = session_order
    return session_order


def initialize_dataset(
    bids_root_path: str,
    yaml_path: str = "metadata.yml",
    output_format: str = "both",
) -> str:
    bids_root_path = os.path.abspath(bids_root_path)
    os.makedirs(bids_root_path, exist_ok=True)

    if not yaml_path or not os.path.exists(yaml_path):
        raise FileNotFoundError(f"YAML not found: {yaml_path}")

    cfg = bmeta.load_metadata_config(yaml_path)

    # The session order (which acquisition date becomes ses-01, ses-02, ...) is
    # built from the real acquisition time read in each CZI, not from the file
    # name. The converters call build_session_order_from_acq_time() once the
    # file list is known (auto-scan resolved). Start empty here.
    SESSION_ORDER_BY_ROOT.setdefault(bids_root_path, {})

    # Only the dataset root gets a dataset_description.json. Derivative folders
    # do not (no derivatives block required in the YAML).
    bmeta.create_dataset_description(bids_root_path, cfg)
    bmeta.create_participants_files(bids_root_path, cfg)

    print("=" * 60)
    print(f"BIDS dataset initialized: {bids_root_path}")
    return bids_root_path


def _copy_with_progress(src: str, dst: str, chunk_size: int = 8 * 1024 * 1024) -> None:
    """Copy a file showing a live percentage (CZI files are large)."""
    total = os.path.getsize(src)
    total_mb = total / (1024 * 1024)
    copied = 0
    name = os.path.basename(dst)
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        while True:
            buf = fin.read(chunk_size)
            if not buf:
                break
            fout.write(buf)
            copied += len(buf)
            pct = (copied / total * 100) if total else 100.0
            print(f"\r  Copying {name}: {pct:5.1f}%  "
                  f"({copied / (1024 * 1024):.0f}/{total_mb:.0f} MB)",
                  end="", flush=True)
    print()  # end the progress line with a newline
    shutil.copystat(src, dst)  # keep timestamps/permissions, like copy2


def create_sourcedata_links(czi_file_path: str, subject: str, bids_root_path: str,copy_real: bool = False) -> None:
    """creating files CZI with same name of the original ones , real copy for the first czi file """
    sourcedata_dir = os.path.join(bids_root_path, "sourcedata", f"sub-{subject}")
    os.makedirs(sourcedata_dir, exist_ok=True)

    dest_path = os.path.join(sourcedata_dir, os.path.basename(czi_file_path))

    if os.path.exists(dest_path):
        return

    if copy_real:
        print(f"Copying first CZI for sub-{subject} ...")
        #_copy_with_progress(czi_file_path, dest_path)
        print(f"First CZI copied: {os.path.basename(dest_path)}")
    else:
        with open(dest_path, "w"):                      
            pass
        print(f"Placeholder: {os.path.basename(dest_path)}")

def build_bids_basename(bids_info, stain, suffix="FLUO"):
    stain_clean = re.sub(r"[^a-zA-Z0-9]", "", stain)

    sample = bids_info.get("sample")
    chunk = bids_info.get("chunk")

    if sample is None:
        raise ValueError("Missing sample in bids_info")
    if chunk is None:
        raise ValueError("Missing chunk in bids_info")

    return (
        f"sub-{bids_info['sub']}"
        f"_ses-{bids_info['ses']}"
        f"_sample-{sample}"
        f"_chunk-{int(chunk)}"
        f"_stain-{stain_clean}"
        f"_{suffix}"
    )
def iter_subject_dirs( root: Path):
    for subject_dir in sorted(root.glob("sub-*")):
        if subject_dir.is_dir():
            yield subject_dir

def iter_subject_niftis( subject_dir: Path):
    for nii_path in subject_dir.rglob("*.nii.gz"):
        yield nii_path
def group_subject_niftis_by_channel( subject_dir: Path):
    groups = {}
    for nii_path in subject_dir.rglob("*.nii.gz"):
        channel = get_channel_from_path(nii_path)
        groups.setdefault(channel, []).append(nii_path)
    return groups

def get_channel_from_path( nii_path: Path) -> str:
    parts = nii_path.name.split("_")

    for part in parts:
        if part.startswith("stain-"):
            return part.replace("stain-", "")

    raise ValueError(f"CHANNEL NOT FOUND  {nii_path.name}")

def get_raw_micr_folder(bids_root_path: str, bids_info: dict) -> str:
    folder_path = os.path.join(
        bids_root_path,
        f"sub-{bids_info['sub']}",
        f"ses-{bids_info['ses']}",
        "micr",
    )
    os.makedirs(folder_path, exist_ok=True)
    return folder_path


def get_derivative_folder(bids_root_path: str, bids_info: dict, res_label) -> str:
    folder_path = os.path.join(
        bids_root_path,
        "derivatives","2D","downsampled",
        f"sub-{bids_info['sub']}",
        f"ses-{bids_info['ses']}",
        "micr",
        f"res-{res_label}",
    )
    os.makedirs(folder_path, exist_ok=True)
    return folder_path