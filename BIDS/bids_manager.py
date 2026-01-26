import os
import ancpbids
from pathlib import Path
import ancpbids.utils
from ancpbids import BIDSLayout, DatasetOptions

def initialize_dataset(bids_root_path):
    bids_root_path = os.path.abspath(bids_root_path)
    if not os.path.exists(bids_root_path):
        os.makedirs(bids_root_path)
    
    # Créer dataset_description.json si inexistant
    desc_file = os.path.join(bids_root_path, "dataset_description.json")
    if not os.path.exists(desc_file):
        desc = {
            "Name": os.path.basename(bids_root_path),
            "BIDSVersion": "1.8.0",
            "DatasetType": "raw"
        }
        ancpbids.utils.write_contents(desc_file, desc)
    
    options = DatasetOptions(infer_artifact_datatype=True, lazy_loading=True)
    dataset = ancpbids.load_dataset(bids_root_path, options=options)
    layout = BIDSLayout(bids_root_path)
    
    print(f"Dataset charge depuis {bids_root_path}")
    return layout, dataset, bids_root_path  # Retourner aussi le path

def get_bids_path(layout, summary_meta, bids_root_path):
    """
    Calcule uniquement la racine BIDS (Sujet, Session, Sample, Acq, Stain, Run).
    
    CORRECTION: Ajouter bids_root_path comme paramètre au lieu d'utiliser layout.root
    """
    sub = summary_meta.get('sub') 
    ses = summary_meta.get('ses') 
    sample = summary_meta.get('sample') 
    acq = summary_meta.get('acq_sig', 'Unknown').split('_')[0].replace(' ', '')
    stain = summary_meta.get('illumination', 'FLUO').replace(' ', '')
    
    existing_entities = layout.get_entities()
    runs = existing_entities.get('run', [])
    if not runs:
        run_idx = "01"
    else:
        numeric_runs = [int(r) for r in runs if str(r).isdigit()]
        run_idx = f"{max(numeric_runs) + 1:02d}" if numeric_runs else "01"
    
    # FIX: Utiliser bids_root_path au lieu de layout.root
    folder_path = os.path.join(bids_root_path, f"sub-{sub}", f"ses-{ses}", "micr")
    if not os.path.exists(folder_path):
        os.makedirs(folder_path, exist_ok=True)
    
    root_name = f"sub-{sub}_ses-{ses}_sample-{sample}_acq-{acq}_stain-{stain}_run-{run_idx}"
    return folder_path, root_name

def write_bids_sidecar(target_path, metadata):
    """
    Crée le fichier .json correspondant au fichier image.
    """
    json_path = os.path.splitext(target_path)[0] + ".json"
    ancpbids.utils.write_contents(json_path, metadata)
    print(f"Sidecar JSON cree : {os.path.basename(json_path)}")