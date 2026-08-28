import os
import pathlib as Path
import re
import glob
import shutil 
from BIDS import bids_metadata as bmeta
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
    session_order = {}

    for entry in cfg.get("samples", {}).get("entries", []):
        subject = entry.get("subject")
        if not subject:
            continue

        date_to_min_slice = {}

        for sample in entry.get("samples", []):
            if not isinstance(sample, dict):
                continue
            for file_entry in (sample.get("files") or []):
                if not isinstance(file_entry, dict):
                    continue
                filename = file_entry.get("filename")
                slices = file_entry.get("slices", [])
                if not filename or not slices:
                    continue

                date_part = filename.split("__")[0]
                parts = date_part.split("_")

                if len(parts) != 3:
                    continue

                year, month, day = parts
                date_key = f"{year}-{month}-{day}"

                date_to_min_slice.setdefault(date_key, None)    
        sorted_dates = sorted(date_to_min_slice.keys())
        session_order[subject] = {
            date_key: f"{idx + 1:02d}"
            for idx, date_key in enumerate(sorted_dates)
        }

    SESSION_ORDER_BY_ROOT[bids_root_path] = session_order

    bmeta.create_dataset_description(bids_root_path, cfg)
    bmeta.create_participants_files(bids_root_path, cfg)
    
    if output_format in ("nii", "both"):
        bmeta.create_derivatives_descriptions(
            bids_root_path,
            cfg        
            )
    print(f"Dataset initialized in {bids_root_path}")
    return bids_root_path


def create_sourcedata_links(czi_file_path: str, subject: str, bids_root_path: str,copy_real: bool = False) -> None:
    """creating files CZI with same name of the original ones , real copy for the first czi file """
    sourcedata_dir = os.path.join(bids_root_path, "sourcedata", f"sub-{subject}")
    os.makedirs(sourcedata_dir, exist_ok=True)

    dest_path = os.path.join(sourcedata_dir, os.path.basename(czi_file_path))

    if os.path.exists(dest_path):
        return

    if copy_real:
        shutil.copy2(czi_file_path, dest_path)          
        print(f"First CZI Copied: {os.path.basename(dest_path)}")
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