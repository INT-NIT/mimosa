import os
import re
import glob
from BIDS import bids_metadata as bmeta


class BIDSSession:
    """
    Assigns BIDS numbers (ses, acq, run) to each CZI file ,
    it remembers what it has already seen (ses, acq, run) and automatically inceremnts nulbers for each file .
    """

    def __init__(self, bids_root_path: str):
        self.bids_root_path = bids_root_path
        self._ses_map = {}   
        self._acq_map = {}   
        self._run_map = {} 

    def _get_last_index(self, entity: str, sub_path: str = None) -> int:
        """scan folders to find existing entity numbers so we can calculate the next index for run and session"""
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

    def _run_index_for_context(self, sub: str, ses_idx: str, sample: str, acq_idx: str, czi_id: str) -> str:
        """
        returns run number for a given czi file.
        run changes when czi file changes — same run for all channels of the same file.
        """
        context_key = (sub, ses_idx, sample, acq_idx, czi_id)  # stain removed
        if context_key not in self._run_map:
            sub_path = os.path.join(self.bids_root_path, f"sub-{sub}")
            existing = self._get_last_index("run", sub_path=sub_path)
            run_idx = f"{max(existing) + 1:02d}" if existing else "01"
            self._run_map[context_key] = run_idx
        return self._run_map[context_key]

    def get_bids_info(self, summary_meta: dict, czi_id: str) -> dict:
        sub      = summary_meta.get("sub")
        acq_time = summary_meta.get("acq_time")  # real date from CZI metadata
        sample   = summary_meta.get("sample")
        acq_sig  = summary_meta.get("acq_sig", "Unknown")

        ses_idx = self._session_index_for_time(sub, acq_time)
        acq_idx = self._acq_index_for_signature(acq_sig)
        run_idx = self._run_index_for_context(sub, ses_idx, sample, acq_idx, czi_id)

        return {
            "sub":            sub,
            "ses":            ses_idx,    # session index
            "acq_time":       acq_time,   # real date for sessions.tsv
            "sample":         sample,
            "acq":            acq_idx,
            "acq_sig":        acq_sig,
            "run":            run_idx,
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


def build_bids_basename(bids_info: dict, stain: str, chunk: str, suffix: str = "FLUO") -> str:
    """sub-_ses-_run-_chunk-_FLUO"""
    stain_clean = re.sub(r"[^a-zA-Z0-9]", "", stain)
    return (
        f"sub-{bids_info['sub']}"
        f"_ses-{bids_info['ses']}"
        f"_sample-{bids_info['sample']}"
        f"_acq-{bids_info['acq']}"
        f"_stain-{stain_clean}"
        f"_run-{bids_info['run']}"
        f"_chunk-{chunk}"
        f"_{suffix}"
    )


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