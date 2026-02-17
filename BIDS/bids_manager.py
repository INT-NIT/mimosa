# bids_manager.py
from __future__ import annotations

import os
import re
from pathlib import Path
import ancpbids


def ensure_dataset_description(bids_root: str, name: str = "MIMOSA microscopy dataset", bids_version: str = "1.8.0"):
    """Crée dataset_description.json à la racine si absent."""
    bids_root = Path(bids_root)
    bids_root.mkdir(parents=True, exist_ok=True)

    desc_path = bids_root / "dataset_description.json"
    if not desc_path.exists():
        desc = {
            "Name": name,
            "BIDSVersion": bids_version,
            "DatasetType": "raw",
        }
        ancpbids.utils.write_contents(str(desc_path), desc)


def write_bids_sidecar(target_path: str, metadata: dict):
    """Crée le fichier .json correspondant (sidecar) à côté du fichier data."""
    json_path = os.path.splitext(target_path)[0] + ".json"
    ancpbids.utils.write_contents(json_path, metadata)


def initialize_derivatives(bids_root: str, pipeline_name: str = "downsampled", bids_version: str = "1.8.0") -> str:
    """Crée derivatives/<pipeline_name>/dataset_description.json si absent."""
    bids_root = Path(bids_root)
    derivatives_path = bids_root / "derivatives" / pipeline_name
    derivatives_path.mkdir(parents=True, exist_ok=True)

    desc_file = derivatives_path / "dataset_description.json"
    if not desc_file.exists():
        desc = {
            "Name": f"{pipeline_name} microscopy images",
            "BIDSVersion": bids_version,
            "DatasetType": "derivative",
            "GeneratedBy": [
                {
                    "Name": "mimosa_hpc_convert",
                    "Version": "1.0",
                    "Description": f"{pipeline_name} outputs of CZI microscopy images",
                }
            ],
            "SourceDatasets": [{"URL": "../.."}],
        }
        ancpbids.utils.write_contents(str(desc_file), desc)

    return str(derivatives_path)


def sanitize_label(x: str) -> str:
    """Garde seulement [a-zA-Z0-9], pratique pour stain/acq."""
    return re.sub(r"[^a-zA-Z0-9]", "", x)


def get_raw_micr_folder(bids_root: str, bids_info: dict) -> str:
    """
    Raw BIDS (TIFF) :
    <bids_root>/sub-XX/ses-YYYYMMDD/micr/
    """
    folder = Path(bids_root) / f"sub-{bids_info['sub']}" / f"ses-{bids_info['ses']}" / "micr"
    folder.mkdir(parents=True, exist_ok=True)
    return str(folder)


def get_deriv_micr_folder(bids_root: str, pipeline_name: str, bids_info: dict) -> str:
    """
    Derivatives (NIfTI) :
    <bids_root>/derivatives/<pipeline>/sub-XX/ses-YYYYMMDD/micr/
    """
    folder = Path(bids_root) / "derivatives" / pipeline_name / f"sub-{bids_info['sub']}" / f"ses-{bids_info['ses']}" / "micr"
    folder.mkdir(parents=True, exist_ok=True)
    return str(folder)


def build_bids_basename(
    bids_info: dict,
    stain: str,
    run: str,
    chunk: str,
    extra_entities: dict | None = None,
    suffix: str = "micr",
) -> str:
    """
    Construit le nom BIDS de base (sans extension) en respectant l’ordre demandé:
    sub, ses, sample, acq, stain, run, chunk, (extras), suffix
    """
    parts = [
        f"sub-{bids_info['sub']}",
        f"ses-{bids_info['ses']}",
        f"sample-{bids_info['sample']}",
        f"acq-{bids_info['acq']}",
        f"stain-{sanitize_label(stain)}",
        f"run-{run}",
        f"chunk-{chunk}",
    ]

    if extra_entities:
        for k, v in extra_entities.items():
            parts.append(f"{k}-{v}")

    return "_".join(parts) + f"_{suffix}"


def prepare_bids_metadata(summary: dict, channel_name: str, channel_idx: int, scene_idx: int) -> dict:
    """Métadonnées sidecar pour le raw TIFF."""
    md = dict(summary)
    md["ChannelName"] = channel_name
    md["ChannelIndex"] = channel_idx
    md["SceneIndex"] = scene_idx
    return md


def prepare_derivative_metadata(summary: dict, channel_name: str, channel_idx: int, downsampling_factor: int) -> dict:
    """Métadonnées sidecar pour les derivatives (NIfTI)."""
    md = dict(summary)
    md["ChannelName"] = channel_name
    md["ChannelIndex"] = channel_idx
    md["DownsamplingFactor"] = downsampling_factor
    md["Pipeline"] = "downsampled"
    return md