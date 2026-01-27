import os
import ancpbids
from pathlib import Path
import ancpbids.utils
from ancpbids import BIDSLayout, DatasetOptions

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
            "DatasetType": "raw"
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

def get_bids_info(layout, summary_meta, bids_root_path):
    """Calcule toutes les infos BIDS une seule fois"""
    sub = summary_meta.get('sub') 
    ses = summary_meta.get('ses') 
    sample = summary_meta.get('sample') 
    
    # acq = numéro incrémental
    existing_entities = layout.get_entities()
    acqs = existing_entities.get('acq', [])
    if not acqs:
        acq_idx = "1"
    else:
        numeric_acqs = [int(a) for a in acqs if str(a).isdigit()]
        acq_idx = str(max(numeric_acqs) + 1) if numeric_acqs else "1"
    
    # run incrémental
    runs = existing_entities.get('run', [])
    if not runs:
        run_idx = "01"
    else:
        numeric_runs = [int(r) for r in runs if str(r).isdigit()]
        run_idx = f"{max(numeric_runs) + 1:02d}" if numeric_runs else "01"
    
    return {
        'sub': sub,
        'ses': ses,
        'sample': sample,
        'acq': acq_idx,
        'run': run_idx,
        'bids_root_path': bids_root_path
    }

def get_channel_path(bids_info, channel_id):
    """Génère le chemin et nom pour un canal spécifique"""
    folder_path = os.path.join(
        bids_info['bids_root_path'], 
        f"sub-{bids_info['sub']}", 
        f"ses-{bids_info['ses']}", 
        "micr"
    )
    if not os.path.exists(folder_path):
        os.makedirs(folder_path, exist_ok=True)
    
    stain = f"C{channel_id}"
    root_name = f"sub-{bids_info['sub']}_ses-{bids_info['ses']}_sample-{bids_info['sample']}_acq-{bids_info['acq']}_stain-{stain}_run-{bids_info['run']}"
    
    return folder_path, root_name

def write_bids_sidecar(target_path, metadata):
    """Crée le fichier .json correspondant"""
    json_path = os.path.splitext(target_path)[0] + ".json"
    ancpbids.utils.write_contents(json_path, metadata)
    print(f"Sidecar JSON cree: {os.path.basename(json_path)}")