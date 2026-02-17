import os
import re
import ancpbids
import ancpbids.utils
from ancpbids import BIDSLayout, DatasetOptions

# mapping acquisition signature -> acq index (stable pendant l’exécution)
acq_signature_mapping = {}

# mapping (sub,ses,sample,acq,czi_id) -> run index
run_file_mapping = {}


def initialize_dataset(bids_root_path):
    bids_root_path = os.path.abspath(bids_root_path)
    bids_dataset_path = os.path.join(bids_root_path, "bids_dataset")

    if not os.path.exists(bids_dataset_path):
        os.makedirs(bids_dataset_path)

    desc_file = os.path.join(bids_dataset_path, "dataset_description.json")
    if not os.path.exists(desc_file):
        desc = {
            "Name": "bids_dataset",
            "BIDSVersion": "1.8.0",
            "DatasetType": "raw",
        }
        ancpbids.utils.write_contents(desc_file, desc)

    options = DatasetOptions(infer_artifact_datatype=True, lazy_loading=True)
    dataset = ancpbids.load_dataset(bids_dataset_path, options=options)
    layout = BIDSLayout(bids_dataset_path)

    print(f"Dataset charge depuis {bids_dataset_path}")
    return layout, dataset, bids_dataset_path


def create_sourcedata_links(czi_file_path, subject, bids_root_path):
    """Crée des liens durs vers les CZI originaux dans sourcedata/"""
    sourcedata_dir = os.path.join(bids_root_path, "sourcedata", f"sub-{subject}")
    os.makedirs(sourcedata_dir, exist_ok=True)

    link_path = os.path.join(sourcedata_dir, os.path.basename(czi_file_path))
    if not os.path.exists(link_path):
        os.link(os.path.abspath(czi_file_path), link_path)
        print(f"Lien sourcedata cree: {os.path.basename(link_path)}")


def initialize_derivatives(bids_root_path, pipeline_name="downsampled"):
    """Initialise le dossier derivatives avec dataset_description.json"""
    derivatives_path = os.path.join(bids_root_path, "derivatives", pipeline_name)

    if not os.path.exists(derivatives_path):
        os.makedirs(derivatives_path)
        print(f"Dossier derivatives cree: {derivatives_path}")

    desc_file = os.path.join(derivatives_path, "dataset_description.json")
    if not os.path.exists(desc_file):
        desc = {
            "Name": f"{pipeline_name.capitalize()} microscopy images",
            "BIDSVersion": "1.8.0",
            "DatasetType": "derivative",
            "GeneratedBy": [
                {
                    "Name": "mimosa_hpc_convert",
                    "Version": "1.0",
                    "Description": f"{pipeline_name} of CZI microscopy images",
                }
            ],
            "SourceDatasets": [{"URL": "../..", "Version": "1.0"}],
        }
        ancpbids.utils.write_contents(desc_file, desc)
        print(f"dataset_description.json cree pour {pipeline_name}")

    return derivatives_path


def get_bids_info(layout, summary_meta, bids_root_path, czi_id=None):
    """
    Calcule infos BIDS.
    IMPORTANT: run est calculé UNE FOIS par fichier CZI (czi_id),
    et reste identique pour toutes les scenes/channels/outputs issus de ce CZI.
    """
    sub = summary_meta.get("sub")
    ses = summary_meta.get("ses")
    sample = summary_meta.get("sample")
    acq_sig = summary_meta.get("acq_sig", "Unknown")

    existing_entities = layout.get_entities()

    # 1) ACQ index basé sur la signature microscope/scaling
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

    # 2) RUN index basé sur le fichier CZI (même CZI => même run)
    # czi_id: idéalement le filename sans extension
    if czi_id is None:
        czi_id = "UNKNOWN_CZI"

    context_key = (sub, ses, sample, acq_idx, czi_id)

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
        "ses": ses,
        "sample": sample,
        "acq": acq_idx,
        "acq_sig": acq_sig,
        "run": run_idx,
        "bids_root_path": bids_root_path,
    }


def build_bids_basename(bids_info, stain, chunk, suffix="FLUO"):
    """
    Nom de base BIDS: ..._run-XX_chunk-YY_SUFFIX
    suffix demandé = FLUO
    """
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


def write_bids_sidecar(target_path, metadata):
    json_path = os.path.splitext(target_path)[0] + ".json"
    ancpbids.utils.write_contents(json_path, metadata)
    print(f"Sidecar JSON cree: {os.path.basename(json_path)}")


def prepare_bids_metadata(summary, channel_name, channel_idx, scene_idx):
    metadata = summary.copy()
    metadata["channel_name"] = channel_name
    metadata["channel_index"] = channel_idx
    metadata["scene_index"] = scene_idx
    return metadata


def prepare_derivative_metadata(summary, channel_name, channel_idx, downsampling_factor):
    metadata = summary.copy()
    metadata["channel_name"] = channel_name
    metadata["channel_index"] = channel_idx
    metadata["Resolution"] = f"Downsampled by factor {downsampling_factor}"
    metadata["DownsamplingFactor"] = downsampling_factor
    metadata["OriginalResolution"] = summary.get("acq_sig", "Unknown")
    metadata["ProcessingPipeline"] = "downsampled"
    return metadata