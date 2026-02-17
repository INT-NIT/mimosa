import os
import ancpbids
from pathlib import Path
import ancpbids.utils
from ancpbids import BIDSLayout, DatasetOptions
import re


acq_signature_mapping = {}
run_context_mapping = {} 
def initialize_dataset(bids_root_path):
    bids_root_path = os.path.abspath(bids_root_path)
    
    if not os.path.exists(bids_root_path):
        os.makedirs(bids_root_path)
    
    desc_file = os.path.join(bids_root_path, "dataset_description.json")
    if not os.path.exists(desc_file):
        desc = {
            "Name": "bids_dataset",
            "BIDSVersion": "1.8.0",
            "DatasetType": "raw"
        }
        ancpbids.utils.write_contents(desc_file, desc)
    
    options = DatasetOptions(infer_artifact_datatype=True, lazy_loading=True)
    dataset = ancpbids.load_dataset(bids_root_path, options=options)
    layout = BIDSLayout(bids_root_path)
    
    print(f"Dataset charge depuis {bids_root_path}")
    return layout, dataset, bids_root_path

def create_sourcedata_links(czi_file_path, subject, bids_root_path):
    """Crée des liens durs vers les CZI originaux dans sourcedata/"""
    sourcedata_dir = os.path.join(bids_root_path, "sourcedata", f"sub-{subject}")
    os.makedirs(sourcedata_dir, exist_ok=True)
    
    link_path = os.path.join(sourcedata_dir, os.path.basename(czi_file_path))
    if not os.path.exists(link_path):
        os.link(os.path.abspath(czi_file_path), link_path)
        print(f"Lien sourcedata cree: {os.path.basename(link_path)}")
# bids_manager.py



def get_bids_info(layout, summary_meta, bids_root_path, channel_name=None):
    """
    Calcule les infos BIDS (sub, ses, sample, acq).
    Si channel_name fourni, calcule aussi run via get_run_for_file().
    """
    sub = summary_meta.get('sub') 
    ses = summary_meta.get('ses') 
    sample = summary_meta.get('sample')
    acq_sig = summary_meta.get('acq_sig', 'Unknown')
    
    existing_entities = layout.get_entities()
    
    # ACQ basé sur la signature d'acquisition
    if acq_sig not in acq_signature_mapping:
        acqs = existing_entities.get('acq', [])
        if not acqs:
            acq_idx = "1"
        else:
            numeric_acqs = [int(a) for a in acqs if str(a).isdigit()]
            acq_idx = str(max(numeric_acqs) + 1) if numeric_acqs else "1"
        acq_signature_mapping[acq_sig] = acq_idx
    else:
        acq_idx = acq_signature_mapping[acq_sig]
    
    result = {
        'sub': sub,
        'ses': ses,
        'sample': sample,
        'acq': acq_idx,
        'acq_sig': acq_sig,
        'bids_root_path': bids_root_path
    }
    
    # Run calculé seulement si canal fourni
    if channel_name:
        result['run'] = get_run_for_file(sub, ses, sample, acq_idx, channel_name)
    
    return result
def get_run_for_file(sub, ses, sample, acq_idx, channel_name):
    """
    Calcule et mémorise le run pour un fichier CZI + canal donné.
    A appeler UNE SEULE FOIS par fichier CZI, avant la boucle des scènes.
    Le même run sera utilisé pour tous les chunks et les deux formats (tiff + nii).
    """
    stain = re.sub(r'[^a-zA-Z0-9]', '', channel_name)
    context_key = (sub, ses, sample, acq_idx, stain)
    
    if context_key not in run_context_mapping:
        # Première fois pour ce contexte → run-01
        run_context_mapping[context_key] = 1
    else:
        # Fichier suivant avec la même config → incrémenter
        run_context_mapping[context_key] += 1
    
    return f"{run_context_mapping[context_key]:02d}"


    """Génère le nom de fichier BIDS (nomenclature uniquement)"""
    stain = re.sub(r'[^a-zA-Z0-9]', '', channel_name)
    return f"sub-{bids_info['sub']}_ses-{bids_info['ses']}_sample-{bids_info['sample']}_acq-{bids_info['acq']}_stain-{stain}_run-{bids_info['run']}"

def get_channel_path(bids_info, channel_name):
    """Crée les dossiers et retourne chemin + nom"""
    folder_path = os.path.join(
        bids_info['bids_root_path'], 
        f"sub-{bids_info['sub']}", 
        f"ses-{bids_info['ses']}", 
        "micr"
    )
    os.makedirs(folder_path, exist_ok=True)
    
    root_name = get_bids_filename(bids_info, channel_name)  # Réutilise
    return folder_path, root_name

def write_bids_sidecar(target_path, metadata):
    """Crée le fichier .json correspondant"""
    json_path = os.path.splitext(target_path)[0] + ".json"
    ancpbids.utils.write_contents(json_path, metadata)
    print(f"Sidecar JSON cree: {os.path.basename(json_path)}")




def initialize_derivatives(bids_root_path, pipeline_name="downsampled"):
    """Initialise le dossier derivatives avec dataset_description.json"""
    derivatives_path = os.path.join(bids_root_path, "derivatives", pipeline_name)
    
    if not os.path.exists(derivatives_path):
        os.makedirs(derivatives_path)
        print(f"Dossier derivatives cree: {derivatives_path}")
    
    # Créer dataset_description.json pour le pipeline
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
                    "Description": f"{pipeline_name} of CZI microscopy images"
                }
            ],
            "SourceDatasets": [
                {
                    "URL": "../..",
                    "Version": "1.0"
                }
            ]
        }
        ancpbids.utils.write_contents(desc_file, desc)
        print(f"dataset_description.json cree pour {pipeline_name}")
    
    return derivatives_path


def get_derivative_path(bids_info, channel_name, resolution, pipeline_name="downsampled"):
    """Génère le chemin pour un fichier dérivé (downsampled)"""
    derivatives_root = os.path.join(bids_info['bids_root_path'], "derivatives", pipeline_name)
    
    folder_path = os.path.join(
        derivatives_root,
        f"sub-{bids_info['sub']}",
        f"ses-{bids_info['ses']}",
        "micr"  
    )
    
    if not os.path.exists(folder_path):
        os.makedirs(folder_path, exist_ok=True)
    
    import re
    stain = re.sub(r'[^a-zA-Z0-9]', '', channel_name)
    
    root_name = f"sub-{bids_info['sub']}_ses-{bids_info['ses']}_sample-{bids_info['sample']}_acq-{bids_info['acq']}_stain-{stain}_run-{bids_info['run']}_res-{resolution}_micr"
    
    return folder_path, root_name

def prepare_bids_metadata(summary, channel_name, channel_idx, scene_idx):
    """Prépare les métadonnées pour un fichier BIDS principal"""
    metadata = summary.copy()
    metadata['channel_name'] = channel_name
    metadata['channel_index'] = channel_idx
    metadata['scene_index'] = scene_idx
    return metadata


def prepare_derivative_metadata(summary, channel_name, channel_idx, downsampling_factor):
    """Prépare les métadonnées pour un fichier derivative"""
    metadata = summary.copy()
    metadata['channel_name'] = channel_name
    metadata['channel_index'] = channel_idx
    metadata['Resolution'] = f"Downsampled by factor {downsampling_factor}"
    metadata['DownsamplingFactor'] = downsampling_factor
    metadata['OriginalResolution'] = summary.get('acq_sig', 'Unknown')
    metadata['ProcessingPipeline'] = 'downsampled'
    return metadata