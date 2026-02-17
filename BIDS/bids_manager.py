import os
import ancpbids
from pathlib import Path
import ancpbids.utils
from ancpbids import BIDSLayout, DatasetOptions
import re

# Mappings globaux : persistent pendant tout le pipeline
acq_signature_mapping = {}
run_context_mapping = {}


def initialize_dataset(bids_root_path):
    bids_root_path = os.path.abspath(bids_root_path)

    if not os.path.exists(bids_root_path):
        os.makedirs(bids_root_path)

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
    return layout, dataset, bids_root_path


def create_sourcedata_links(czi_file_path, subject, bids_root_path):
    """Cree des liens durs vers les CZI originaux dans sourcedata/"""
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
            "GeneratedBy": [{"Name": "mimosa_hpc_convert", "Version": "1.0",
                             "Description": f"{pipeline_name} of CZI microscopy images"}],
            "SourceDatasets": [{"URL": "../..", "Version": "1.0"}]
        }
        ancpbids.utils.write_contents(desc_file, desc)
        print(f"dataset_description.json cree pour {pipeline_name}")

    return derivatives_path


def get_bids_info(layout, summary_meta, bids_root_path, channel_name=None):
    """
    Calcule les infos BIDS (sub, ses, sample, acq).
    Si channel_name fourni, calcule aussi run.

    IMPORTANT : quand channel_name est fourni, appeler cette fonction
    UNE SEULE FOIS par canal par fichier CZI (avant la boucle des scenes).
    Le meme run sera reutilise pour tous les chunks du meme fichier.

    Args:
        layout: BIDSLayout du dataset
        summary_meta: dict avec sub, ses, sample, acq_sig (le summary du CZI)
        bids_root_path: chemin racine du dataset BIDS
        channel_name: nom du canal (ex: "DAPI"). Si fourni, run est calcule.
    """
    sub = summary_meta.get('sub')
    ses = summary_meta.get('ses')
    sample = summary_meta.get('sample')
    acq_sig = summary_meta.get('acq_sig', 'Unknown')

    existing_entities = layout.get_entities()

    # ACQ base sur la signature d'acquisition (microscope + resolution)
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

    # Run calcule seulement si canal fourni
    if channel_name:
        stain = re.sub(r'[^a-zA-Z0-9]', '', channel_name)
        context_key = (sub, ses, sample, acq_idx, stain)

        if context_key not in run_context_mapping:
            # Premiere fois pour ce contexte : run-01
            run_context_mapping[context_key] = 1
        else:
            # Meme config, nouveau fichier CZI : incrementer
            run_context_mapping[context_key] += 1

        result['run'] = f"{run_context_mapping[context_key]:02d}"

    return result


def get_bids_filename(bids_info, channel_name):
    """Genere le nom de fichier BIDS (nomenclature uniquement, sans extension)"""
    stain = re.sub(r'[^a-zA-Z0-9]', '', channel_name)
    return (f"sub-{bids_info['sub']}_ses-{bids_info['ses']}_sample-{bids_info['sample']}"
            f"_acq-{bids_info['acq']}_stain-{stain}_run-{bids_info['run']}")


def get_channel_path(bids_info, channel_name):
    """Cree les dossiers BIDS et retourne (chemin_dossier, nom_base_fichier)"""
    folder_path = os.path.join(
        bids_info['bids_root_path'],
        f"sub-{bids_info['sub']}",
        f"ses-{bids_info['ses']}",
        "micr"
    )
    os.makedirs(folder_path, exist_ok=True)
    root_name = get_bids_filename(bids_info, channel_name)
    return folder_path, root_name


def get_derivative_path(bids_info, channel_name, resolution, pipeline_name="downsampled"):
    """Genere le chemin pour un fichier derive (downsampled)"""
    derivatives_root = os.path.join(bids_info['bids_root_path'], "derivatives", pipeline_name)
    folder_path = os.path.join(
        derivatives_root,
        f"sub-{bids_info['sub']}",
        f"ses-{bids_info['ses']}",
        "micr"
    )
    os.makedirs(folder_path, exist_ok=True)

    stain = re.sub(r'[^a-zA-Z0-9]', '', channel_name)
    root_name = (f"sub-{bids_info['sub']}_ses-{bids_info['ses']}_sample-{bids_info['sample']}"
                 f"_acq-{bids_info['acq']}_stain-{stain}_run-{bids_info['run']}"
                 f"_res-{resolution}_micr")
    return folder_path, root_name


def write_bids_sidecar(target_path, metadata):
    """Cree le fichier .json correspondant"""
    json_path = os.path.splitext(target_path)[0] + ".json"
    ancpbids.utils.write_contents(json_path, metadata)
    print(f"Sidecar JSON cree: {os.path.basename(json_path)}")


def prepare_bids_metadata(summary, channel_name, channel_idx, scene_idx):
    """Prepare les metadonnees pour un fichier BIDS principal"""
    metadata = summary.copy()
    metadata['channel_name'] = channel_name
    metadata['channel_index'] = channel_idx
    metadata['scene_index'] = scene_idx
    return metadata


def prepare_derivative_metadata(summary, channel_name, channel_idx, downsampling_factor):
    """Prepare les metadonnees pour un fichier derivative"""
    metadata = summary.copy()
    metadata['channel_name'] = channel_name
    metadata['channel_index'] = channel_idx
    metadata['Resolution'] = f"Downsampled by factor {downsampling_factor}"
    metadata['DownsamplingFactor'] = downsampling_factor
    metadata['OriginalResolution'] = summary.get('acq_sig', 'Unknown')
    metadata['ProcessingPipeline'] = 'downsampled'
    return metadata


def create_channel_sidecars(bids_infos_per_channel, summary, channels_info, nb_scenes, downsampling_factor):
    """
    Cree tous les JSON sidecars :
    - BIDS principal : un par canal par scene (chunk)
    - Derivatives : un par canal
    """
    for channel_idx, channel_name in channels_info.items():
        bids_info = bids_infos_per_channel[channel_idx]

        # JSON BIDS principal : un par scene (chunk)
        for scene_idx in range(nb_scenes):
            bids_folder, bids_root = get_channel_path(bids_info, channel_name)
            bids_json_path = os.path.join(bids_folder, f"{bids_root}_chunk-{scene_idx:02d}")
            bids_metadata = prepare_bids_metadata(summary, channel_name, channel_idx, scene_idx)
            write_bids_sidecar(bids_json_path, bids_metadata)

        # JSON derivatives : un par canal
        deriv_folder, deriv_root = get_derivative_path(
            bids_info, channel_name, resolution=f"ds{downsampling_factor}"
        )
        deriv_json_path = os.path.join(deriv_folder, deriv_root)
        deriv_metadata = prepare_derivative_metadata(summary, channel_name, channel_idx, downsampling_factor)
        write_bids_sidecar(deriv_json_path, deriv_metadata)