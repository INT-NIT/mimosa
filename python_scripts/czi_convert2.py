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


# Maximum number of native pixels held in RAM for one streaming band.
# 64e6 uint16 pixels ~= 128 MB per band and per channel.
BAND_BUDGET_PIXELS = 64_000_000

# Native rows are only skipped when the decimation factor is large enough to
# jump over whole CZI sub-blocks. Below that threshold, skipping rows forces
# libCZI to decompress the same sub-block several times and is slower than
# streaming everything. Typical CZI sub-blocks are 1024 or 2048 rows high.
ROW_SKIP_MIN_FACTOR = 2048


def _read_native_band(czidoc, x0, y0, width, height, scene_idx, channel_idx):
    """Read a native-resolution band. No ``zoom``, therefore no interpolation."""
    band = np.asarray(
        czidoc.read(
            roi=(int(x0), int(y0), int(width), int(height)),
            plane={"C": int(channel_idx)},
            scene=int(scene_idx),
        )
    ).squeeze()

    if band.ndim == 3:
        band = band[..., 0]

    if band.ndim != 2:
        raise RuntimeError(
            "Expected a 2D CZI band, "
            f"got shape {band.shape} for scene {scene_idx}, "
            f"channel {channel_idx}."
        )

    return band


def read_decimated_multi(
    czidoc,
    roi: tuple[int, int, int, int],
    scene_idx: int,
    channel_idx: int,
    exponents,
    band_budget_pixels: int = BAND_BUDGET_PIXELS,
) -> dict[int, np.ndarray]:
    """Produce every requested resolution from a single native streaming pass.

    Each output is a strict decimation ``native[::f, ::f]`` with ``f = 2**e``.
    The CZI is never read with ``zoom``, so no interpolation, no resampling and
    no value blending ever happens: every exported pixel is a native pixel,
    bit for bit.

    Because all factors are powers of two and every band starts on a multiple
    of the largest factor, all resolutions sample the same native grid and are
    exactly nested: 1 pixel of ``res-8x`` covers exactly 4x4 pixels of
    ``res-6x``, whose corners coincide.

    Returns
    -------
    dict mapping the exponent to its decimated 2D array.
    """
    exponents = sorted({int(e) for e in exponents})
    if not exponents:
        raise ValueError("At least one downsampling exponent is required")
    if exponents[0] < 0:
        raise ValueError("Downsampling exponents must be >= 0")

    x0, y0, width, height = (int(v) for v in roi)
    factors = {e: 2**e for e in exponents}
    factor_max = max(factors.values())
    factor_min = min(factors.values())

    outputs: dict[int, np.ndarray] = {}
    dtype = None

    # --- Band height: a multiple of the largest factor so that, inside every
    # band, the rows to keep are always at local indices 0, f, 2f, ... -------
    rows_per_budget = max(1, int(band_budget_pixels // max(1, width)))
    band_height = max(factor_max, (rows_per_budget // factor_max) * factor_max)
    band_height = min(band_height, height)

    # --- Fast path: when one output row is further apart than a whole CZI
    # sub-block, read only the native rows that are actually kept. The bigger
    # the downsampling, the fewer bytes are decompressed. -------------------
    skip_rows = factor_min >= ROW_SKIP_MIN_FACTOR

    y = 0
    while y < height:
        current_height = min(band_height, height - y)

        if skip_rows:
            # Only the single native row that each output row keeps.
            band = _read_native_band(
                czidoc, x0, y0 + y, width, 1, scene_idx, channel_idx
            )
            band = band[np.newaxis, :] if band.ndim == 1 else band
            current_height = 1
        else:
            band = _read_native_band(
                czidoc, x0, y0 + y, width, current_height, scene_idx, channel_idx
            )

        if dtype is None:
            dtype = band.dtype
            for exponent, factor in factors.items():
                outputs[exponent] = np.empty(
                    (
                        (height + factor - 1) // factor,
                        (width + factor - 1) // factor,
                    ),
                    dtype=dtype,
                )

        for exponent, factor in factors.items():
            if skip_rows and (y % factor) != 0:
                continue
            block = band[::factor, ::factor]
            row0 = y // factor
            outputs[exponent][row0 : row0 + block.shape[0], :] = block

        del band
        y += current_height if not skip_rows else factor_min

    return outputs


def czi2bitmapHPC(
    pathin: str,
    czifilename: str,
    bids_root_path: str,
    bids_info: dict,
    downsampling_factor,
    output_format: str,
    res_label=None,
    reader=None,
    slice_position_map=None,
    original_thickness: float = 100,
    reorient: str = "none",
):
    """Export one CZI to every requested resolution in a single native pass.

    ``downsampling_factor`` is an exponent, or a list of exponents. Passing
    several exponents at once costs almost nothing: the native data is read
    only once and decimated to each resolution on the fly.
    """
    if isinstance(downsampling_factor, (list, tuple, set)):
        exponents = sorted({int(e) for e in downsampling_factor})
    else:
        exponents = [int(downsampling_factor)]

    if res_label is None:
        res_labels = {e: f"{e}x" for e in exponents}
    elif isinstance(res_label, dict):
        res_labels = {int(k): v for k, v in res_label.items()}
    else:
        if len(exponents) != 1:
            raise ValueError(
                "A single res_label cannot be used with several exponents"
            )
        res_labels = {exponents[0]: res_label}

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

        deriv_folders = {
            exponent: bm.get_derivative_folder(
                bids_root_path,
                bids_info,
                res_labels[exponent],
            )
            for exponent in exponents
        }
        for folder in deriv_folders.values():
            os.makedirs(folder, exist_ok=True)

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
                    # One native streaming pass -> every resolution at once.
                    images_by_exponent = read_decimated_multi(
                        czidoc=czidoc,
                        roi=roi,
                        scene_idx=scene_idx,
                        channel_idx=channel_idx,
                        exponents=exponents,
                    )

                    stain = f"C{channel_idx}"

                    for exponent in exponents:
                        channel_image = images_by_exponent[exponent]
                        effective_downsampling_factor = 2**exponent
                        deriv_folder = deriv_folders[exponent]

                        base = bm.build_bids_basename(
                            bids_info=bids_info,
                            stain=stain,
                            suffix="FLUO",
                        )

                        if "_res-" not in base:
                            base = base.replace(
                                "_FLUO",
                                f"_res-{res_labels[exponent]}"
                                f"_desc-{desc_label}_FLUO",
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

                    del images_by_exponent
                    bar()

    return True