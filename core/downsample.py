"""CZI downsampling (via the CZI zoom) and slice geometry (the sform).

Downsampling is done with the CZI `zoom` argument, which serves ZEN's pyramid
levels. The reduced value of each pixel is produced by ZEN's own resampling.

slice_sform builds where each downsampled slice sits in physical space (mm).
"""

from __future__ import annotations

import numpy as np

UM_TO_MM = 1e-3


def downsample_scene_zoom(czidoc, roi, scene, channel, exponents):
    """Reduce one scene to every requested resolution using the CZI zoom.

    For each exponent, factor = 2**exponent and the CZI is read with
    zoom = 1 / factor. Returns {exponent: 2D array}.
    """
    exponents = sorted({int(e) for e in exponents})
    x0, y0, width, height = (int(v) for v in roi)
    out = {}
    for exponent in exponents:
        factor = 2 ** exponent
        img = np.asarray(
            czidoc.read(roi=(x0, y0, width, height), plane={"C": int(channel)},
                        scene=int(scene), zoom=1.0 / factor)
        ).squeeze()
        if img.ndim == 3:
            img = img[..., 0]
        out[exponent] = img
    return out


def slice_sform(pixel_size_um, native_pixel_um, native_width, native_height,
                slice_position, nb_slices, thickness_um,
                ds_width=None, ds_height=None):
    """Build the 4x4 sform of one slice, in mm, centered on the scene.

    When the exported (downsampled) width/height are given, the origin centers
    the image on its own downsampled pixel grid. With every slice exported at an
    odd size, a pixel center sits exactly on 0 for every slice and every
    resolution, so the raw slices, their padded versions and the 3D volume all
    align, and the resolutions align with each other. Without them, it falls
    back to native-grid centering.
    """
    if native_width <= 0 or native_height <= 0:
        raise ValueError("native size must be positive")
    if not 0 <= slice_position < nb_slices:
        raise ValueError(f"slice {slice_position} outside 0..{nb_slices - 1}")

    step_x, step_y = (float(v) * UM_TO_MM for v in pixel_size_um[:2])
    native_x, native_y = (float(v) * UM_TO_MM for v in native_pixel_um[:2])
    step_z = float(thickness_um) * UM_TO_MM

    # Center on the EXPORTED (downsampled) grid when its size is known: the
    # tissue center then lands exactly on 0 for every slice, whatever its native
    # size (with odd sizes, a real pixel center sits on 0). All slices then share
    # the same origin and overlay exactly, and the resolutions stay nested.
    # Centering on the native grid instead leaves a per-slice sub-pixel offset,
    # because floor(native/factor) drops a variable "native mod factor" remainder.
    if ds_width is not None and ds_height is not None:
        origin_x = -(float(ds_width) - 1) / 2 * step_x
        origin_y = -(float(ds_height) - 1) / 2 * step_y
    else:
        origin_x = -(native_width - 1) / 2 * native_x   # fallback: native centering
        origin_y = -(native_height - 1) / 2 * native_y

    origin_z = (slice_position - (nb_slices - 1) / 2) * step_z

    return np.array([[step_x, 0.0, 0.0, origin_x],
                     [0.0, step_y, 0.0, origin_y],
                     [0.0, 0.0, step_z, origin_z],
                     [0.0, 0.0, 0.0, 1.0]], dtype=float)


def grids_nested(fine, coarse, native_pixel_um, axis=0, tol=0.01):
    """Tell whether a coarse sform tiles a fine one exactly along one axis."""
    native = float(native_pixel_um[axis]) * UM_TO_MM
    step_fine = float(fine[axis, axis]) / native
    step_coarse = float(coarse[axis, axis]) / native
    edge_fine = float(fine[axis, 3]) / native - step_fine / 2
    edge_coarse = float(coarse[axis, 3]) / native - step_coarse / 2

    ratio = step_coarse / step_fine
    return abs(edge_fine - edge_coarse) < tol and abs(ratio - round(ratio)) < tol
