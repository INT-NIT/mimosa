from __future__ import annotations

import os
import numpy as np
import tifffile as tf
import nibabel as nib

from pylibCZIrw import czi as pyczi
from alive_progress import alive_bar

import bids_manager as bm


def get_nb_channels(czidoc) -> int:
    md = czidoc.metadata
    n = int(md["ImageDocument"]["Metadata"]["Information"]["Image"]["SizeC"])
    if n == 0:
        while True:
            try:
                _ = czidoc.read(roi=(0, 0, 10, 10), plane={"C": n})
                n += 1
            except Exception:
                break
    return n


def czi2bitmapHPC(
    pathin: str,
    czifilename: str,
    bids_root_path: str,
    bids_info: dict,
    run_counter: dict,
    downsampling_factor: int,
    output_format: str,
    pipeline_name: str = "downsampled",
):
    """
    - output_format == "tiff" : écrit dans <bids_root_path>/sub-*/ses-*/micr/
    - output_format == "nii"  : écrit dans <bids_root_path>/derivatives/<pipeline>/sub-*/ses-*/micr/
    """

    output_format = output_format.strip().lower()
    if output_format not in ("tiff", "nii"):
        raise ValueError("output_format must be 'tiff' or 'nii'")

    czifile_path = os.path.join(pathin, czifilename)

    # derivatives ok (dataset_description raw déjà fait dans initialize_dataset)
    bm.initialize_derivatives(bids_root_path, pipeline_name=pipeline_name)

    with pyczi.open_czi(czifile_path) as czidoc:
        scenes = czidoc.scenes_bounding_rectangle
        nb_channels = get_nb_channels(czidoc)

        zoom_factor = float(1.0 / downsampling_factor)

        for scene_idx in range(len(scenes)):
            chunk = f"{scene_idx:02d}"
            rect = scenes[scene_idx]
            roi = (rect[0], rect[1], rect[2], rect[3])

            # lire chaque channel de cette scene
            channel_images = {}
            for c in range(nb_channels):
                channel_images[c] = czidoc.read(
                    roi=roi,
                    plane={"C": c},
                    scene=scene_idx,
                    zoom=zoom_factor,
                )

            with alive_bar(nb_channels, force_tty=True, title=f"Scene {scene_idx}") as bar:
                for c in range(nb_channels):
                    channel_name = f"C{c}"   # stable
                    stain = channel_name

                    # run global: évite collisions (comme tu faisais)
                    run_counter["run"] = run_counter.get("run", 0) + 1
                    run = f"{run_counter['run']:02d}"

                    # ---------- RAW TIFF ----------
                    if output_format == "tiff":
                        raw_folder = os.path.join(
                            bids_root_path,
                            f"sub-{bids_info['sub']}",
                            f"ses-{bids_info['ses']}",
                            "micr",
                        )
                        os.makedirs(raw_folder, exist_ok=True)

                        base = (
                            f"sub-{bids_info['sub']}"
                            f"_ses-{bids_info['ses']}"
                            f"_sample-{bids_info['sample']}"
                            f"_acq-{bids_info['acq']}"
                            f"_stain-{stain}"
                            f"_run-{run}"
                            f"_chunk-{chunk}"
                            f"_micr"
                        )

                        out_path = os.path.join(raw_folder, base + ".tiff")
                        tf.imwrite(out_path, channel_images[c], imagej=True)

                        md = bm.prepare_bids_metadata(
                            bids_info.get("summary_for_json", {}),
                            channel_name,
                            c,
                            scene_idx
                        )
                        bm.write_bids_sidecar(out_path, md)

                        print(f"  -> BIDS: {os.path.relpath(out_path, bids_root_path)}")

                    # ---------- DERIV NIfTI ----------
                    else:
                        deriv_folder = os.path.join(
                            bids_root_path,
                            "derivatives",
                            pipeline_name,
                            f"sub-{bids_info['sub']}",
                            f"ses-{bids_info['ses']}",
                            "micr",
                        )
                        os.makedirs(deriv_folder, exist_ok=True)

                        resolution = f"ds{downsampling_factor}"
                        base = (
                            f"sub-{bids_info['sub']}"
                            f"_ses-{bids_info['ses']}"
                            f"_sample-{bids_info['sample']}"
                            f"_acq-{bids_info['acq']}"
                            f"_stain-{stain}"
                            f"_run-{run}"
                            f"_chunk-{chunk}"
                            f"_res-{resolution}"
                            f"_micr"
                        )

                        out_path = os.path.join(deriv_folder, base + ".nii.gz")
                        arr = np.swapaxes(channel_images[c], 0, 1)
                        img = nib.Nifti1Image(arr, np.eye(4))
                        nib.save(img, out_path)

                        md = bm.prepare_derivative_metadata(
                            bids_info.get("summary_for_json", {}),
                            channel_name,
                            c,
                            downsampling_factor,
                        )
                        bm.write_bids_sidecar(out_path, md)

                        print(f"  -> derivatives: {os.path.relpath(out_path, bids_root_path)}")

                    bar()

    return True