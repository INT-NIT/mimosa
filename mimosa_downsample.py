"""MIMoSA downsampling core: exact reduction and consistent geometry.

Single source of truth for two things that must always agree:

  1. HOW a native CZI block is turned into one exported pixel;
  2. WHERE that exported pixel sits in physical space.

Design decisions, and why
------------------------

**The CZI `zoom` parameter is never used.**
Measured on real MIMoSA data (MIO21100401, scene 0, 55424x26332):

    native read of a 55424x4096 strip : 5.02 s
    same strip with zoom=1/256        : 0.01 s   (x736)

Decompressing 227 million pixels in 10 ms is impossible. `zoom` serves ZEN
pyramid levels, which are pre-averaged by an algorithm we do not control, and
it returns floor(n/f) instead of ceil(n/f), silently dropping up to 220 rows
and 128 columns of tissue. Fast and exact are mutually exclusive here, and we
choose exact.

**One output pixel is one native BLOCK, never a point.**
A NIfTI voxel cannot be a dimensionless point: writing a pixel size of
f x native already declares that the voxel occupies a f x f block. Placing it
anywhere other than its block center contradicts its own declared size, and
that contradiction is what makes coarse and fine grids fail to tile in a
viewer (a res-8x edge landing exactly on a res-6x center).

So the voxel k of factor f always represents native block
``[k*f, k*f + f - 1]`` and is placed at its center ``k*f + (f-1)/2``.
Since all factors are powers of two, every resolution then tiles the same
native grid from index 0 and they are exactly nested: 4x4 res-6x voxels fill
exactly one res-8x voxel, edges included.

``reduce_method`` only chooses how the block's value is estimated:
  - "decimate" : the top-left native pixel of the block. No value is ever
                 invented, but 1 native pixel out of f*f is kept.
  - "mean"     : the exact average of the block, computed here in int64 from
                 native data. Reproducible, and describable in a methods
                 section, unlike the ZEN pyramid.

Neither is an interpolation: no value is ever blended across block boundaries,
and no output pixel is ever placed between two native pixels.
"""

from __future__ import annotations

import numpy as np

UM_TO_MM = 1e-3

REDUCE_METHODS = ("decimate", "mean")

# Maximum native pixels held in RAM for one streaming band (~128 MB uint16).
BAND_BUDGET_PIXELS = 64_000_000


# ---------------------------------------------------------------------------
# Reduction
# ---------------------------------------------------------------------------

def reduce_block(band: np.ndarray, factor: int, method: str) -> np.ndarray:
    """Reduce a native band by ``factor``.

    Output size is ``ceil(n / factor)``: the trailing partial block is kept,
    never dropped. For "mean" it is averaged over the pixels that exist.
    """
    if method not in REDUCE_METHODS:
        raise ValueError(f"method must be one of {REDUCE_METHODS}, got {method!r}")

    if factor == 1:
        return band.copy()

    if method == "decimate":
        return band[::factor, ::factor]

    height, width = band.shape
    rows = np.arange(0, height, factor)
    cols = np.arange(0, width, factor)

    # int64 accumulation is mandatory: a 64x64 block of uint16 sums to 2.7e8,
    # far past the 2**24 exact-integer limit of float32, which silently
    # corrupts res-6x and beyond. reduceat writes into the reduced-size output,
    # so the full band is never copied to a wider dtype.
    is_integer = np.issubdtype(band.dtype, np.integer)
    accum = np.int64 if is_integer else np.float64

    acc = np.add.reduceat(band, rows, axis=0, dtype=accum)
    acc = np.add.reduceat(acc, cols, axis=1, dtype=accum)

    counts_y = np.diff(np.append(rows, height))
    counts_x = np.diff(np.append(cols, width))
    mean = acc.astype(np.float64) / (counts_y[:, None] * counts_x[None, :])

    if is_integer:
        info = np.iinfo(band.dtype)
        mean = np.clip(np.rint(mean), info.min, info.max)

    return mean.astype(band.dtype)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def _read_native_band(czidoc, x0, y0, width, height, scene_idx, channel_idx):
    """Read a native band. No ``zoom``: no pyramid, no resampling."""
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
            f"Expected a 2D CZI band, got shape {band.shape} "
            f"(scene {scene_idx}, channel {channel_idx})"
        )
    return band


def read_reduced_multi(
    czidoc,
    roi,
    scene_idx: int,
    channel_idx: int,
    exponents,
    reduce_method: str = "decimate",
    band_budget_pixels: int = BAND_BUDGET_PIXELS,
) -> dict[int, np.ndarray]:
    """Produce every requested resolution from one native streaming pass.

    Reading the native data once and reducing it to all factors on the fly
    makes extra resolutions almost free: exporting 4x + 6x + 8x costs the same
    as exporting 4x alone.
    """
    exponents = sorted({int(e) for e in exponents})
    if not exponents:
        raise ValueError("At least one exponent is required")
    if exponents[0] < 0:
        raise ValueError("Exponents must be >= 0")
    if reduce_method not in REDUCE_METHODS:
        raise ValueError(f"Unknown reduce_method: {reduce_method!r}")

    x0, y0, width, height = (int(v) for v in roi)
    factors = {e: 2**e for e in exponents}
    factor_max = max(factors.values())

    # Band height is a multiple of the largest factor, so no block ever
    # straddles two bands and the result equals a whole-image reduction.
    rows_per_budget = max(1, int(band_budget_pixels // max(1, width)))
    band_height = max(factor_max, (rows_per_budget // factor_max) * factor_max)
    band_height = min(band_height, height)

    outputs: dict[int, np.ndarray] = {}
    dtype = None

    y = 0
    while y < height:
        current = min(band_height, height - y)
        band = _read_native_band(
            czidoc, x0, y0 + y, width, current, scene_idx, channel_idx
        )

        if dtype is None:
            dtype = band.dtype
            for exponent, factor in factors.items():
                outputs[exponent] = np.empty(
                    ((height + factor - 1) // factor,
                     (width + factor - 1) // factor),
                    dtype=dtype,
                )

        for exponent, factor in factors.items():
            block = reduce_block(band, factor, reduce_method)
            row0 = y // factor
            outputs[exponent][row0 : row0 + block.shape[0], :] = block

        del band
        y += current

    return outputs


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def block_center_offset(factor: float) -> float:
    """Offset, in native pixels, from a block's first pixel to its center."""
    return (float(factor) - 1.0) / 2.0


def build_slice_sform(
    pixel_size_um,
    native_pixel_size_um,
    native_width: int,
    native_height: int,
    slice_position: int,
    nb_slices: int,
    thickness_um: float,
):
    """SForm of one exported 2D slice, in mm, scene-centered.

    Voxel k covers native block [k*f, k*f + f - 1] and is placed at its center.
    Every resolution therefore tiles the same native grid, and all resolutions
    of one scene share the same physical extent.
    """
    if native_width <= 0 or native_height <= 0:
        raise ValueError("native_width and native_height must be positive")
    if nb_slices <= 0:
        raise ValueError("nb_slices must be positive")
    if not 0 <= slice_position < nb_slices:
        raise ValueError(
            f"Invalid slice position {slice_position} for {nb_slices} slices"
        )

    res_x_mm = float(pixel_size_um[0]) * UM_TO_MM
    res_y_mm = float(pixel_size_um[1]) * UM_TO_MM
    nat_x_mm = float(native_pixel_size_um[0]) * UM_TO_MM
    nat_y_mm = float(native_pixel_size_um[1]) * UM_TO_MM

    factor_x = res_x_mm / nat_x_mm
    factor_y = res_y_mm / nat_y_mm

    # Native pixel i sits at (i - (N-1)/2) * native_res, so the scene is
    # centered on 0. Voxel 0 covers native [0, f-1] -> center at (f-1)/2.
    origin_x_mm = (block_center_offset(factor_x) - (native_width - 1.0) / 2.0) * nat_x_mm
    origin_y_mm = (block_center_offset(factor_y) - (native_height - 1.0) / 2.0) * nat_y_mm
    origin_z_mm = (
        float(slice_position) - (float(nb_slices) - 1.0) / 2.0
    ) * float(thickness_um) * UM_TO_MM

    sform = np.array(
        [
            [res_x_mm, 0.0, 0.0, origin_x_mm],
            [0.0, res_y_mm, 0.0, origin_y_mm],
            [0.0, 0.0, float(thickness_um) * UM_TO_MM, origin_z_mm],
            [0.0, 0.0, 0.0, 1.0],
        ],
        dtype=float,
    )
    return sform


def grids_are_nested(sform_fine, sform_coarse, native_px_um, axis=0, tol=1e-9):
    """True if the coarse grid tiles the fine one exactly along ``axis``.

    Used by the test suite and by check_alignment.py. Compares the left edge
    of voxel 0 and the spacing ratio, both expressed in native pixels.
    """
    nat_mm = float(native_px_um[axis]) * UM_TO_MM
    step_f = float(sform_fine[axis, axis]) / nat_mm
    step_c = float(sform_coarse[axis, axis]) / nat_mm
    edge_f = float(sform_fine[axis, 3]) / nat_mm - step_f / 2.0
    edge_c = float(sform_coarse[axis, 3]) / nat_mm - step_c / 2.0

    ratio = step_c / step_f
    return (
        abs(edge_f - edge_c) < tol
        and abs(ratio - round(ratio)) < tol
    )
