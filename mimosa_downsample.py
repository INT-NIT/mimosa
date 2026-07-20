"""Exact CZI downsampling: how a native block becomes a pixel, and where it sits.

These two rules must always agree, so they live in one file.

One output pixel of factor f is the native block [k*f, k*f+f-1], placed at its
center. Declaring a pixel size of f x native already commits to the block
interpretation; placing the voxel anywhere else contradicts its own size, and
that contradiction is what stops coarse and fine grids from tiling in a viewer.
Because factors are powers of two, every resolution then tiles the same native
grid and they nest exactly.

BLOCK_VALUE picks how the block value is estimated, never where it sits:
"decimate" takes the block's first native pixel, "mean" averages the block.
Neither interpolates: no value is blended across block boundaries, no pixel
lands between two native pixels.

The CZI `zoom` argument is never used. Measured on MIO21100401 scene 0, a
55424x4096 native strip takes 5.02 s to read but 0.01 s with zoom=1/256.
Decompressing 227 million pixels in 10 ms is impossible: zoom serves ZEN
pyramid levels, pre-averaged by an algorithm we do not control, and it returns
floor(n/f) instead of ceil(n/f), silently dropping up to 220 rows of tissue.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np

UM_TO_MM = 1e-3

BLOCK_VALUES = ("decimate", "mean")

# Native pixels per streaming band, ~230 MB of uint16.
# A band ending mid sub-block makes libCZI decompress it twice. Measured on
# scene 0 (width 55424), same 4096 native rows: 512 rows 11.6 s, 1024 rows
# 6.9 s, 2048 rows 5.0 s, 4096 rows 3.9 s. But "mean" is compute-bound and
# gets slower on very large bands, so 2048 rows is the compromise.
BAND_PIXELS = 115_000_000

# Bands read and reduced concurrently. This is what makes ONE image fast.
# pyczi releases the GIL while decoding and NumPy releases it during the
# reduction, so both halves scale; concurrent reads were verified
# byte-identical to serial ones. Measured on one scene, 3 resolutions, 4 cores:
# decimate 7.26 s -> 3.26 s, mean 7.46 s -> 3.23 s. Scaling flattens once
# threads exceed the number of cores.
READ_THREADS = min(8, (os.cpu_count() or 4))


def downsample_band(band, factors, block_value):
    """Reduce one native band to several factors at once.

    For "mean" the levels are cascaded: res-6x is built from the res-4x sums,
    res-8x from the res-6x sums, so only the first level touches the full band
    and extra resolutions are nearly free. Sums and pixel counts are carried
    separately and divided only at the end, which keeps partial edge blocks
    exact -- averaging averages would not.

    Returns {factor: array}, each of size ceil(n / factor): the trailing
    partial block is kept, never dropped.
    """
    if block_value not in BLOCK_VALUES:
        raise ValueError(f"block_value must be one of {BLOCK_VALUES}")

    factors = sorted(factors)

    if block_value == "decimate":
        return {f: band[::f, ::f] if f > 1 else band.copy() for f in factors}

    integer = np.issubdtype(band.dtype, np.integer)
    accum = np.int64 if integer else np.float64
    limits = np.iinfo(band.dtype) if integer else None

    out, sums, counts, previous = {}, band, None, 1

    for factor in factors:
        step = factor // previous
        if step > 1 or counts is None:
            rows = np.arange(0, sums.shape[0], step)
            cols = np.arange(0, sums.shape[1], step)
            if counts is None:
                counts = (
                    np.diff(np.append(rows, sums.shape[0]))[:, None]
                    * np.diff(np.append(cols, sums.shape[1]))[None, :]
                )
            else:
                counts = np.add.reduceat(
                    np.add.reduceat(counts, rows, axis=0), cols, axis=1
                )
            sums = np.add.reduceat(
                np.add.reduceat(sums, rows, axis=0, dtype=accum),
                cols, axis=1, dtype=accum,
            )

        mean = sums.astype(np.float64) / counts
        if integer:
            mean = np.clip(np.rint(mean), limits.min, limits.max)
        out[factor] = mean.astype(band.dtype)
        previous = factor

    return out


def read_band(czidoc, roi, scene, channel):
    """Read one native band from a CZI. No zoom, so no pyramid and no resampling."""
    x, y, width, height = (int(v) for v in roi)
    band = np.asarray(
        czidoc.read(roi=(x, y, width, height), plane={"C": int(channel)},
                    scene=int(scene))
    ).squeeze()

    if band.ndim == 3:
        band = band[..., 0]
    if band.ndim != 2:
        raise RuntimeError(
            f"expected a 2D CZI band, got {band.shape} "
            f"(scene {scene}, channel {channel})"
        )
    return band


def downsample_scene(czidoc, roi, scene, channel, exponents,
                     block_value="decimate", band_pixels=BAND_PIXELS,
                     threads=READ_THREADS):
    """Produce every requested resolution from one native streaming pass.

    Reading the native data once and reducing it to all factors on the fly
    makes extra resolutions almost free: 4x + 6x + 8x costs about the same as
    4x alone. Returns {exponent: array}.
    """
    exponents = sorted({int(e) for e in exponents})
    if not exponents:
        raise ValueError("at least one exponent is required")
    if exponents[0] < 0:
        raise ValueError("exponents must be >= 0")
    if block_value not in BLOCK_VALUES:
        raise ValueError(f"block_value must be one of {BLOCK_VALUES}")

    x0, y0, width, height = (int(v) for v in roi)
    factors = {e: 2**e for e in exponents}
    largest = max(factors.values())

    # Band height is a multiple of the largest factor, so no block straddles
    # two bands and the result equals reducing the whole scene at once.
    rows = max(1, band_pixels // max(1, width))
    band_height = min(height, max(largest, (rows // largest) * largest))
    starts = list(range(0, height, band_height))

    out = {}

    def build(y):
        """Read one band and reduce it, both inside the worker thread.

        Reducing here rather than in the caller matters twice over: NumPy
        releases the GIL, so the int64 accumulation runs in parallel too, and
        only the small reduced blocks travel back instead of the whole band.
        """
        height_here = min(band_height, height - y)
        band = read_band(czidoc, (x0, y0 + y, width, height_here), scene, channel)
        return y, band.dtype, downsample_band(band, factors.values(), block_value)

    def place(y, dtype, blocks):
        if not out:
            for exponent, factor in factors.items():
                out[exponent] = np.empty(
                    (-(-height // factor), -(-width // factor)), dtype=dtype
                )
        for exponent, factor in factors.items():
            block = blocks[factor]
            out[exponent][y // factor : y // factor + block.shape[0], :] = block

    if threads > 1 and len(starts) > 1:
        # Bands are disjoint and each writes its own output rows, so order does
        # not matter. Submitting in waves of `threads` caps memory at that many
        # bands: mapping every start at once would queue them all at full size.
        with ThreadPoolExecutor(max_workers=int(threads)) as pool:
            for i in range(0, len(starts), threads):
                for result in pool.map(build, starts[i : i + threads]):
                    place(*result)
    else:
        for y in starts:
            place(*build(y))

    return out


def slice_sform(pixel_size_um, native_pixel_um, native_width, native_height,
                slice_position, nb_slices, thickness_um):
    """Build the 4x4 sform of one exported slice, in mm, centered on the scene.

    Voxel k covers native block [k*f, k*f+f-1] and sits at its center, so every
    resolution of a scene tiles the same native grid and shares its extent.
    """
    if native_width <= 0 or native_height <= 0:
        raise ValueError("native size must be positive")
    if nb_slices <= 0:
        raise ValueError("nb_slices must be positive")
    if not 0 <= slice_position < nb_slices:
        raise ValueError(f"slice {slice_position} outside 0..{nb_slices - 1}")

    step_x, step_y = (float(v) * UM_TO_MM for v in pixel_size_um[:2])
    native_x, native_y = (float(v) * UM_TO_MM for v in native_pixel_um[:2])
    step_z = float(thickness_um) * UM_TO_MM

    # Native pixel i sits at (i - (N-1)/2) * native, so the scene is centered
    # on 0. Voxel 0 covers native [0, f-1], hence a center at (f-1)/2.
    origin_x = ((step_x / native_x - 1.0) / 2.0 - (native_width - 1.0) / 2.0) * native_x
    origin_y = ((step_y / native_y - 1.0) / 2.0 - (native_height - 1.0) / 2.0) * native_y
    origin_z = (float(slice_position) - (float(nb_slices) - 1.0) / 2.0) * step_z

    return np.array(
        [[step_x, 0.0, 0.0, origin_x],
         [0.0, step_y, 0.0, origin_y],
         [0.0, 0.0, step_z, origin_z],
         [0.0, 0.0, 0.0, 1.0]],
        dtype=float,
    )


def grids_nested(fine, coarse, native_pixel_um, axis=0, tol=0.01):
    """Tell whether a coarse sform tiles a fine one exactly along one axis.

    Compares the left edge of voxel 0 and the spacing ratio, both in native
    pixels. The default tolerance is a hundredth of a native pixel because
    NIfTI stores the sform as float32, which alone costs ~1e-3 pixel.
    """
    native = float(native_pixel_um[axis]) * UM_TO_MM
    step_fine = float(fine[axis, axis]) / native
    step_coarse = float(coarse[axis, axis]) / native
    edge_fine = float(fine[axis, 3]) / native - step_fine / 2.0
    edge_coarse = float(coarse[axis, 3]) / native - step_coarse / 2.0

    ratio = step_coarse / step_fine
    return abs(edge_fine - edge_coarse) < tol and abs(ratio - round(ratio)) < tol
