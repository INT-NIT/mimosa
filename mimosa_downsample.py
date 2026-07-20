"""Exact CZI downsampling: how a native block becomes a pixel, and where it sits.

These two rules must agree, so they live in one file.

One output pixel of factor f is the native block [k*f, k*f+f-1], placed at its
center. Writing a pixel size of f x native already says the voxel covers a
block; placing it anywhere else contradicts its own size, and that is what
stops coarse and fine grids from tiling in a viewer.

block_value picks how the block value is estimated, never where it sits.
Neither option interpolates: no value is blended across block boundaries.

The CZI `zoom` argument is never used: it serves ZEN pyramid levels, averaged
by an unknown algorithm, and drops the trailing rows (floor instead of ceil).
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np

UM_TO_MM = 1e-3

BLOCK_VALUES = ("decimate", "mean")

# ~2048 native rows per band at width 55424. Larger bands read faster (a band
# ending mid sub-block makes libCZI decompress it twice) but make "mean"
# slower, so this is the compromise.
BAND_PIXELS = 115_000_000

# Bands read and reduced concurrently: this is what makes one image fast.
# Measured on 4 cores, one scene, 3 resolutions: 7.3 s -> 3.3 s.
READ_THREADS = min(8, os.cpu_count() or 4)


def downsample_band(band, factors, block_value):
    """Reduce one native band to several factors at once.

    Returns {factor: array}, each of size ceil(n / factor) so the trailing
    partial block is kept.
    """
    if block_value not in BLOCK_VALUES:
        raise ValueError(f"block_value must be one of {BLOCK_VALUES}")

    factors = sorted(factors)

    if block_value == "decimate":
        return {f: band[::f, ::f] if f > 1 else band.copy() for f in factors}

    integer = np.issubdtype(band.dtype, np.integer)
    # int64 is mandatory: a 64x64 block of uint16 sums past what float32 can
    # hold exactly, which silently corrupts res-6x and beyond.
    accum = np.int64 if integer else np.float64
    limits = np.iinfo(band.dtype) if integer else None

    out, sums, counts, previous = {}, band, None, 1

    for factor in factors:
        # Cascade: res-6x is built from the res-4x sums, so only the first
        # level touches the full band. Sums and pixel counts travel separately
        # and are divided at the end, which keeps partial edge blocks exact.
        step = factor // previous
        if step > 1 or counts is None:
            rows = np.arange(0, sums.shape[0], step)
            cols = np.arange(0, sums.shape[1], step)
            if counts is None:
                counts = (np.diff(np.append(rows, sums.shape[0]))[:, None]
                          * np.diff(np.append(cols, sums.shape[1]))[None, :])
            else:
                counts = np.add.reduceat(
                    np.add.reduceat(counts, rows, axis=0), cols, axis=1)
            sums = np.add.reduceat(
                np.add.reduceat(sums, rows, axis=0, dtype=accum),
                cols, axis=1, dtype=accum)

        mean = sums.astype(np.float64) / counts
        if integer:
            mean = np.clip(np.rint(mean), limits.min, limits.max)
        out[factor] = mean.astype(band.dtype)
        previous = factor

    return out


def read_band(czidoc, roi, scene, channel):
    """Read one native band from a CZI. No zoom, so no pyramid."""
    x, y, width, height = (int(v) for v in roi)
    band = np.asarray(
        czidoc.read(roi=(x, y, width, height), plane={"C": int(channel)},
                    scene=int(scene))
    ).squeeze()

    if band.ndim == 3:
        band = band[..., 0]
    if band.ndim != 2:
        raise RuntimeError(f"expected a 2D band, got {band.shape}")
    return band


def downsample_scene(czidoc, roi, scene, channel, exponents,
                     block_value="decimate", band_pixels=BAND_PIXELS,
                     threads=READ_THREADS):
    """Produce every requested resolution from one native pass.

    Reading once and reducing to all factors on the fly makes extra
    resolutions nearly free. Returns {exponent: array}.
    """
    exponents = sorted({int(e) for e in exponents})
    if not exponents or exponents[0] < 0:
        raise ValueError("exponents must be a non-empty list of values >= 0")
    if block_value not in BLOCK_VALUES:
        raise ValueError(f"block_value must be one of {BLOCK_VALUES}")

    x0, y0, width, height = (int(v) for v in roi)
    factors = {e: 2**e for e in exponents}
    largest = max(factors.values())

    # A multiple of the largest factor, so no block straddles two bands.
    rows = max(1, band_pixels // max(1, width))
    band_height = min(height, max(largest, (rows // largest) * largest))
    starts = list(range(0, height, band_height))

    out = {}

    def build(y):
        """Read and reduce one band, both inside the worker thread."""
        height_here = min(band_height, height - y)
        band = read_band(czidoc, (x0, y0 + y, width, height_here), scene, channel)
        return y, band.dtype, downsample_band(band, factors.values(), block_value)

    def place(y, dtype, blocks):
        """Copy one band's reduced blocks into the output arrays."""
        if not out:
            for exponent, factor in factors.items():
                out[exponent] = np.empty(
                    (-(-height // factor), -(-width // factor)), dtype=dtype)
        for exponent, factor in factors.items():
            block = blocks[factor]
            out[exponent][y // factor: y // factor + block.shape[0], :] = block

    if threads > 1 and len(starts) > 1:
        # Waves of `threads` bands, so memory stays bounded.
        with ThreadPoolExecutor(max_workers=int(threads)) as pool:
            for i in range(0, len(starts), threads):
                for result in pool.map(build, starts[i: i + threads]):
                    place(*result)
    else:
        for y in starts:
            place(*build(y))

    return out


def slice_sform(pixel_size_um, native_pixel_um, native_width, native_height,
                slice_position, nb_slices, thickness_um):
    """Build the 4x4 sform of one slice, in mm, centered on the scene."""
    if native_width <= 0 or native_height <= 0:
        raise ValueError("native size must be positive")
    if not 0 <= slice_position < nb_slices:
        raise ValueError(f"slice {slice_position} outside 0..{nb_slices - 1}")

    step_x, step_y = (float(v) * UM_TO_MM for v in pixel_size_um[:2])
    native_x, native_y = (float(v) * UM_TO_MM for v in native_pixel_um[:2])
    step_z = float(thickness_um) * UM_TO_MM

    # Native pixel i sits at (i - (N-1)/2) * native, centering the scene on 0.
    # Voxel 0 covers native [0, f-1], hence a center at (f-1)/2.
    origin_x = ((step_x / native_x - 1) / 2 - (native_width - 1) / 2) * native_x
    origin_y = ((step_y / native_y - 1) / 2 - (native_height - 1) / 2) * native_y
    origin_z = (slice_position - (nb_slices - 1) / 2) * step_z

    return np.array([[step_x, 0.0, 0.0, origin_x],
                     [0.0, step_y, 0.0, origin_y],
                     [0.0, 0.0, step_z, origin_z],
                     [0.0, 0.0, 0.0, 1.0]], dtype=float)


def grids_nested(fine, coarse, native_pixel_um, axis=0, tol=0.01):
    """Tell whether a coarse sform tiles a fine one exactly along one axis.

    The tolerance is a hundredth of a native pixel: NIfTI stores the sform as
    float32, which alone costs about a thousandth.
    """
    native = float(native_pixel_um[axis]) * UM_TO_MM
    step_fine = float(fine[axis, axis]) / native
    step_coarse = float(coarse[axis, axis]) / native
    edge_fine = float(fine[axis, 3]) / native - step_fine / 2
    edge_coarse = float(coarse[axis, 3]) / native - step_coarse / 2

    ratio = step_coarse / step_fine
    return abs(edge_fine - edge_coarse) < tol and abs(ratio - round(ratio)) < tol
