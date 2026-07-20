from __future__ import annotations

import os

import nibabel as nib
import numpy as np
import tifffile as tf
from alive_progress import alive_bar
from pylibCZIrw import czi as pyczi

from BIDS import bids_manager as bm
from BIDS import bids_metadata as bmeta
from BIDS.czi_reader import MimosaReader


def _read_from_reference_resolution(
    czidoc,
    roi: tuple[int, int, int, int],
    scene_idx: int,
    channel_idx: int,
    downsampling_exponent: int,
    reference_exponent: int = 4,
) -> np.ndarray:
    """Read one fixed CZI reference resolution, then decimate from it.

    The CZI reader is used only once at the fixed reference resolution
    ``2**reference_exponent``. Coarser outputs are produced by direct NumPy
    pixel selection, so all generated resolutions stay nested without an
    additional interpolation step.
    """
    if downsampling_exponent < 0:
        raise ValueError("downsampling_exponent must be greater than or equal to 0")

    if downsampling_exponent < reference_exponent:
        zoom_factor = 1.0 / float(2**downsampling_exponent)
        return np.asarray(
            czidoc.read(
                roi=roi,
                plane={"C": channel_idx},
                scene=scene_idx,
                zoom=zoom_factor,
            )
        ).squeeze()

    reference_factor = 2**reference_exponent
    reference_image = np.asarray(
        czidoc.read(
            roi=roi,
            plane={"C": channel_idx},
            scene=scene_idx,
            zoom=1.0 / float(reference_factor),
        )
    ).squeeze()

    if reference_image.ndim != 2:
        raise RuntimeError(
            "Expected a 2D CZI image, "
            f"got shape {reference_image.shape} for scene {scene_idx}, "
            f"channel {channel_idx}."
        )

    relative_factor = 2 ** (downsampling_exponent - reference_exponent)
    return reference_image[::relative_factor, ::relative_factor].copy()


def czi2bitmapHPC(
    pathin: str,
    czifilename: str,
    bids_root_path: str,
    bids_info: dict,
    downsampling_factor: int,
    output_format: str,
    res_label: str,
    reader=None,
    slice_position_map=None,
    original_thickness: float = 100,
    reorient: str = "none",
):
    effective_downsampling_factor = 2**downsampling_factor
    desc_label = "downsampled"
    czifile_path = os.path.join(pathin, czifilename)

    output_format = output_format.lower().strip()
    if output_format not in ("tif", "nii", "both"):
        raise ValueError("output_format must be 'tif', 'nii' or 'both'")

    write_tif = output_format in ("tif", "both")
    write_nii = output_format in ("nii", "both")

    with pyczi.open_czi(czifile_path) as czidoc:
        scenes = czidoc.scenes_bounding_rectangle
        nb_channels = MimosaReader.get_nb_channels(czidoc)

        deriv_folder = bm.get_derivative_folder(
            bids_root_path,
            bids_info,
            res_label,
        )
        os.makedirs(deriv_folder, exist_ok=True)

        for scene_idx in range(len(scenes)):
            rect = scenes[scene_idx]
            roi = (
                int(rect[0]),
                int(rect[1]),
                int(rect[2]),
                int(rect[3]),
            )

            slice_idx = reader.get_slice_index_for_scene(scene_idx)
            if slice_idx is None:
                print(
                    f"  WARNING: no slice index for scene {scene_idx}, skipping"
                )
                continue

            bids_info["chunk"] = slice_idx

            with alive_bar(
                nb_channels,
                force_tty=True,
                title=f"Scene {scene_idx}",
            ) as bar:
                for channel_idx in range(nb_channels):
                    channel_image = _read_from_reference_resolution(
                        czidoc=czidoc,
                        roi=roi,
                        scene_idx=scene_idx,
                        channel_idx=channel_idx,
                        downsampling_exponent=downsampling_factor,
                        reference_exponent=4,
                    )

                    stain = f"C{channel_idx}"
                    base = bm.build_bids_basename(
                        bids_info=bids_info,
                        stain=stain,
                        suffix="FLUO",
                    )

                    if "_res-" not in base:
                        base = base.replace(
                            "_FLUO",
                            f"_res-{res_label}_desc-{desc_label}_FLUO",
                        )

                    if write_tif:
                        tif_path = os.path.join(deriv_folder, base + ".tif")
                        tf.imwrite(tif_path, channel_image, imagej=True)

                        meta_tiff = reader.get_converted_file_metadata(
                            rect=rect,
                            stain=stain,
                            downsampling_factor=effective_downsampling_factor,
                            is_nifti=False,
                            scene_idx=scene_idx,
                            exported_shape=(
                                int(channel_image.shape[1]),
                                int(channel_image.shape[0]),
                            ),
                        )
                        bmeta.write_micr_sidecar_json(tif_path, meta_tiff)
                        print(
                            "  -> BIDS raw: "
                            f"{os.path.relpath(tif_path, bids_root_path)}"
                        )

                    if write_nii:
                        nii_path = os.path.join(
                            deriv_folder,
                            base + ".nii.gz",
                        )
                        arr = np.swapaxes(channel_image, 0, 1)

                        meta_nii = reader.get_converted_file_metadata(
                            rect=rect,
                            stain=stain,
                            downsampling_factor=effective_downsampling_factor,
                            is_nifti=True,
                            scene_idx=scene_idx,
                            exported_shape=(
                                int(arr.shape[0]),
                                int(arr.shape[1]),
                            ),
                        )

                        if slice_position_map is not None:
                            meta_nii = bmeta.add_sform_to_json_metadata(
                                meta=meta_nii,
                                slice_position_map=slice_position_map,
                                original_thickness=original_thickness,
                            )

                        sform = np.asarray(
                            meta_nii.get("SFormMatrix", np.eye(4)),
                            dtype=float,
                        )

                        img = nib.Nifti1Image(arr, sform)
                        img.set_sform(sform, code=1)
                        img.set_qform(sform, code=1)
                        img.header.set_xyzt_units("mm")
                        nib.save(img, nii_path)

                        bmeta.write_micr_sidecar_json(nii_path, meta_nii)
                        print(
                            "  -> derivatives: "
                            f"{os.path.relpath(nii_path, bids_root_path)}"
                        )

                    del channel_image
                    bar()

    return True