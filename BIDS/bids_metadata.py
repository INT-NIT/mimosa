# bids_metadata.py
import os
import ancpbids.utils

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