# czi_convert2.py
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
        # fallback
        while True:
            try:
                _ = czidoc.read(roi=(0, 0, 10, 10), plane={"C": n})
                n += 1
            except Exception:
                break
    return n


def safe_mkdir(p: str):
    os.makedirs(p, exist_ok=True)


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
   
    czifile_path = os.path.join(pathin, czifilename)

    # assure dataset_description + derivatives/.. description
    bm.ensure_dataset_description(bids_root_path)
    bm.initialize_derivatives(bids_root_path, pipeline_name=pipeline_name)

    with pyczi.open_czi(czifile_path) as czidoc:
        scenes = czidoc.scenes_bounding_rectangle
        nb_channels = get_nb_channels(czidoc)

        # dossiers cibles
        raw_folder = bm.get_raw_micr_folder(bids_root_path, bids_info)
        deriv_folder = bm.get_deriv_micr_folder(bids_root_path, pipeline_name, bids_info)

        zoom_factor = float(1.0 / downsampling_factor)

        for scene_idx in range(len(scenes)):
            chunk = f"{scene_idx:02d}"
            rect = scenes[scene_idx]
            roi = (rect[0], rect[1], rect[2], rect[3])

            # lecture de toutes les channels pour cette scene
            channel_images = {}
            for c in range(nb_channels):
                channel_images[c] = czidoc.read(roi=roi, plane={"C": c}, scene=scene_idx, zoom=zoom_factor)

            with alive_bar(nb_channels, force_tty=True, title=f"Scene {scene_idx}") as bar:
                for c in range(nb_channels):
                    channel_name = f"C{c}"   # simple et stable
                    stain = channel_name

                    # run: incrémente pour éviter collisions
                    run_counter["run"] = run_counter.get("run", 0) + 1
                    run = f"{run_counter['run']:02d}"

                    base = bm.build_bids_basename(
                        bids_info=bids_info,
                        stain=stain,
                        run=run,
                        chunk=chunk,
                        suffix="micr",
                    )

                    if output_format == "tiff":
                        out_path = os.path.join(raw_folder, base + ".tiff")
                        tf.imwrite(out_path, channel_images[c], imagej=True)

                        # sidecar JSON raw
                        md = bm.prepare_bids_metadata(bids_info.get("summary_for_json", {}), channel_name, c, scene_idx)
                        bm.write_bids_sidecar(out_path, md)

                        print(f"  -> BIDS raw: {os.path.relpath(out_path, bids_root_path)}")

                    elif output_format == "nii":
                        out_path = os.path.join(deriv_folder, base + ".nii.gz")
                        arr = np.swapaxes(channel_images[c], 0, 1)
                        img = nib.Nifti1Image(arr, np.eye(4))
                        nib.save(img, out_path)

                        # sidecar JSON derivative
                        md = bm.prepare_derivative_metadata(
                            bids_info.get("summary_for_json", {}),
                            channel_name,
                            c,
                            downsampling_factor,
                        )
                        bm.write_bids_sidecar(out_path, md)

                        print(f"  -> derivatives: {os.path.relpath(out_path, bids_root_path)}")

                    else:
                        raise ValueError("output_format must be 'tiff' or 'nii'")

                    bar()

    return True