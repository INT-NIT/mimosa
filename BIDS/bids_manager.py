import os
import pathlib as Path
import re
import glob
from BIDS import bids_metadata as bmeta


class BIDSSession:
    """
    Assigns BIDS numbers (ses, acq ) to each CZI file ,
    it remembers what it has already seen (ses, acq) and automatically inceremnts nulbers for each file .
    """

    def __init__(self, bids_root_path: str):
        self.bids_root_path = bids_root_path
        self._ses_map = {}   
        self._acq_map = {}   

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
        Stock for each subject all the sessions with each session a correspondant index
        """
        if sub not in self._ses_map:
            self._ses_map[sub] = {}
        if acq_time not in self._ses_map[sub]:
            next_idx = len(self._ses_map[sub]) + 1
            self._ses_map[sub][acq_time] = f"{next_idx:02d}"
        return self._ses_map[sub][acq_time]

    def _acq_index_for_signature(self, acq_sig: str) -> str:
        """returns acq number for a given microscope signature"""
        if acq_sig not in self._acq_map:
            existing = self._get_last_index("acq")
            acq_idx = f"{max(existing) + 1:02d}" if existing else "01"
            self._acq_map[acq_sig] = acq_idx
        return self._acq_map[acq_sig]


    def get_bids_info(self, summary_meta, czi_id, section_idx):
        sub      = summary_meta.get("sub")
        acq_time = summary_meta.get("acq_time")
        acq_sig  = summary_meta.get("acq_sig", "Unknown")

        ses_idx = self._session_index_for_time(sub, acq_time)
        acq_idx = self._acq_index_for_signature(acq_sig)

        return {
            "sub":            sub,
            "ses":            ses_idx,
            "acq_time":       acq_time,
            "acq":            acq_idx,
            "acq_sig":        acq_sig,
            "section":        section_idx,   # ← "176", "184"...
            "bids_root_path": self.bids_root_path,
        }

def initialize_dataset(bids_root_path: str, yaml_path: str = "metadata.yml", output_format: str = "both") -> str:
    bids_root_path = os.path.abspath(bids_root_path)
    os.makedirs(bids_root_path, exist_ok=True)

    if not yaml_path or not os.path.exists(yaml_path):
        raise FileNotFoundError(f"YAML not found: {yaml_path}")

    cfg = bmeta.load_metadata_config(yaml_path)
    bmeta.create_dataset_description(bids_root_path, cfg)
    bmeta.create_participants_files(bids_root_path, cfg)
    
    if output_format in ("nii", "both"):
        bmeta.create_derivatives_descriptions(bids_root_path, cfg)

    print(f"Dataset initialized in {bids_root_path}")
    return bids_root_path


def create_sourcedata_links(czi_file_path: str, subject: str, bids_root_path: str) -> None:
    """creating files CZI with same name of the original ones"""
    sourcedata_dir = os.path.join(bids_root_path, "sourcedata", f"sub-{subject}")
    os.makedirs(sourcedata_dir, exist_ok=True)

    placeholder_path = os.path.join(sourcedata_dir, os.path.basename(czi_file_path))

    if os.path.exists(placeholder_path):
        return

    with open(placeholder_path, "w"):
        pass

    print(f"Placeholder: {os.path.basename(placeholder_path)}")

def build_bids_basename(bids_info, stain, suffix="FLUO"):
    stain_clean = re.sub(r"[^a-zA-Z0-9]", "", stain)
    return (
        f"sub-{bids_info['sub']}"
        f"_ses-{bids_info['ses']}"
        f"_sample-section{bids_info['section']}"  # ← "section176"
        f"_acq-{bids_info['acq']}"
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
def group_subject_niftis_by_channel(self, subject_dir: Path):
    groups = {}
    for nii_path in subject_dir.rglob("*.nii.gz"):
        channel = self.get_channel_from_path(nii_path)
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


def get_derivative_folder(bids_root_path: str, pipeline_name: str, bids_info: dict) -> str:
    folder_path = os.path.join(
        bids_root_path,
        "derivatives",
        pipeline_name,
        f"sub-{bids_info['sub']}",
        f"ses-{bids_info['ses']}",
        "micr",
    )
    os.makedirs(folder_path, exist_ok=True)
    return folder_path