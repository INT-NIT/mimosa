import os
import re
import ancpbids
from ancpbids import BIDSLayout, DatasetOptions
import bids_metadata as bmeta

acq_signature_mapping = {}

run_file_mapping = {}

session_time_mapping = {}


def initialize_dataset(bids_root_path, yaml_path="metadata.yml"):
   
    bids_root_path = os.path.abspath(bids_root_path)
    bids_dataset_path = os.path.join(bids_root_path, "bids_dataset")
    os.makedirs(bids_dataset_path, exist_ok=True)

    if yaml_path and os.path.exists(yaml_path):
        cfg = bmeta.load_metadata_config(yaml_path)
        bmeta.create_dataset_description(bids_dataset_path, cfg)
        bmeta.create_participants_files(bids_dataset_path, cfg)
        bmeta.create_derivatives_descriptions(bids_dataset_path, cfg)
    else:
        print(f"Attention: YAML introuvable: {yaml_path}")

    options = DatasetOptions(infer_artifact_datatype=True, lazy_loading=True)
    dataset = ancpbids.load_dataset(bids_dataset_path, options=options)
    layout = BIDSLayout(bids_dataset_path)

    print(f"Dataset charge depuis {bids_dataset_path}")
    return layout, dataset, bids_dataset_path


def create_sourcedata_links(czi_file_path, subject, bids_root_path):
    """Crée un fichier placeholder vide dans sourcedata/"""
    sourcedata_dir = os.path.join(bids_root_path, "sourcedata", f"sub-{subject}")
    os.makedirs(sourcedata_dir, exist_ok=True)

    placeholder_path = os.path.join(sourcedata_dir, os.path.basename(czi_file_path))
    
    # Ne rien faire si le fichier existe déjà
    if os.path.exists(placeholder_path):
        return
    
    # Créer le placeholder vide
    with open(placeholder_path, "w"):
        pass
    
    print(f"    Placeholder: {os.path.basename(placeholder_path)}")

def _session_index_for_time(sub: str, acq_time: str) -> str:
 
    if sub not in session_time_mapping:
        session_time_mapping[sub] = {}

    if acq_time not in session_time_mapping[sub]:
        next_idx = len(session_time_mapping[sub]) + 1
        session_time_mapping[sub][acq_time] = f"{next_idx:02d}"

    return session_time_mapping[sub][acq_time]


def get_bids_info(layout, summary_meta, bids_root_path, czi_id=None):
 
    sub = summary_meta.get("sub")
    acq_time = summary_meta.get("ses")  # date réelle
    sample = summary_meta.get("sample")
    acq_sig = summary_meta.get("acq_sig", "Unknown")

    ses_idx = _session_index_for_time(sub, acq_time)

    existing_entities = layout.get_entities()

    # ACQ index (signature microscope/scaling)
    if acq_sig not in acq_signature_mapping:
        acqs = existing_entities.get("acq", [])
        if not acqs:
            acq_idx = "1"
        else:
            numeric_acqs = [int(a) for a in acqs if str(a).isdigit()]
            acq_idx = str(max(numeric_acqs) + 1) if numeric_acqs else "1"
        acq_signature_mapping[acq_sig] = acq_idx
    else:
        acq_idx = acq_signature_mapping[acq_sig]

    # RUN index (1 fois par fichier CZI)
    if czi_id is None:
        czi_id = "UNKNOWN_CZI"

    context_key = (sub, ses_idx, sample, acq_idx, czi_id)

    if context_key not in run_file_mapping:
        runs = existing_entities.get("run", [])
        if not runs:
            run_idx = "01"
        else:
            numeric_runs = [int(r) for r in runs if str(r).isdigit()]
            run_idx = f"{max(numeric_runs) + 1:02d}" if numeric_runs else "01"
        run_file_mapping[context_key] = run_idx
    else:
        run_idx = run_file_mapping[context_key]

    return {
        "sub": sub,
        "ses": ses_idx,        # ses-01, ses-02...
        "acq_time": acq_time,  # date réelle
        "sample": sample,
        "acq": acq_idx,
        "acq_sig": acq_sig,
        "run": run_idx,
        "bids_root_path": bids_root_path,
    }


def build_bids_basename(bids_info, stain, chunk, suffix="FLUO"):
    """sub-..._ses-.._..._run-.._chunk-.._FLUO"""
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


def get_raw_micr_folder(bids_root_path, bids_info):
    folder_path = os.path.join(
        bids_root_path,
        f"sub-{bids_info['sub']}",
        f"ses-{bids_info['ses']}",
        "micr",
    )
    os.makedirs(folder_path, exist_ok=True)
    return folder_path


def get_derivative_folder(bids_root_path, pipeline_name, bids_info):
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