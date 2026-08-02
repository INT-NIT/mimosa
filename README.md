# The Mimosa Project

A set of tools for **M**ultiscale **I**maging for mar**MO**set **S**oftware &amp; **A**nalysis.

# Description

The MIMOSA project aims to provide a multiscale, automated, versatile, and user-friendly tool for 3D reconstruction and cell quantification in the brain of the marmoset (<i>Callithrix jacchus</i>) using histological sections. Designed to meet the need for precise and accurate quantification in viral tracing experiments, MIMOSA facilitates efficient analysis.

The tool utilizes DAPI staining to register histological sections to MRI atlases of the marmoset brain, while fluorescent protein labeling enables neuron quantification in targeted areas. MIMOSA integrates Cellpose, allowing users to develop custom-trained models for neuron quantification. Additionally, it includes a built-in `.czi` converter that reads the native image and produces downsampled TIFF, OME-TIFF and NIfTI images, without interpolation.


# Installing for development

```bash
git clone https://github.com/INT-NIT/mimosa.git
cd mimosa
```

### Create the conda environment

**macOS** (tested on macOS Ventura 13.4.1):

```bash
conda env create -f install_env/Mac/environment_macosX_13.4.yml
conda activate mimosa_dev
pip install install_env/Mac/additionnal_package/pylibCZIrw-3.5.1-cp311-cp311-macosx_10_9_universal2.whl
```

**Linux** (tested on Debian 12 bookworm):

```bash
conda env create -f install_env/Linux/requirements_Debian12.yml
conda activate mimosa_dev
```


# The output is a BIDS dataset

MIMOSA does not just produce image files: it builds an organized **BIDS**
dataset. BIDS (Brain Imaging Data Structure) is a widely used convention that
fixes *where each file goes* and *how it is named*, so that any tool or
collaborator can find and understand the data without asking.

A BIDS dataset has three layers, and MIMOSA fills all three:

- **`sourcedata/`** — stands for the original acquisition. Because the `.czi`
  files are very large, MIMOSA does **not** copy them here: it writes only a
  small marker (an empty placeholder named after the CZI). The real `.czi`
  stay in the acquisition folder referenced by the YAML.
- **raw** (`sub-<subject>/ses-<session>/micr/`) — the primary images in a BIDS
  format. MIMOSA writes the whole-slide **OME-TIFF** mosaics here. OME-TIFF is
  a valid BIDS microscopy format, lighter than the `.czi`.
- **`derivatives/`** — the downsampled images, the preprocessed slices, and the
  reconstructed 3D volumes.

### An honest note on the BIDS layers

**We did not fully follow the BIDS convention, and we want to be clear about
it.** BIDS says that files in `derivatives/` must be produced from the `raw`
data. Here the `raw` data are the OME-TIFF mosaics, but they are only there to
give an idea of the data — to see the whole set of scenes at a reasonable size.
The real inputs are the `.czi` files, not the OME-TIFFs. So our downsampled
`derivatives/` are computed from the `.czi`, not from the OME-TIFF `raw`.

File names follow the BIDS entities, for example:

```
sub-Una_ses-01_sample-slide1_chunk-67_stain-C0_res-8x_desc-downsampled_FLUO.nii.gz
   │       │        │            │          │        │         │          │
subject  session   sample      slice      stain  resolution  method    modality
```

You do not build this layout by hand. You describe your inputs once in a small
YAML file, and the scripts create the folders, the names, and the metadata.


# The `metadata.yml` file

Every command reads a `metadata.yml` that declares your subjects and where
their `.czi` files live. Minimal shape:

```yaml
samples:
  entries:
    - path: /path/to/Una/czi/folder     # folder holding this subject's CZI
      subject: Una
      samples:
        - sample_type: technical sample
          derived_from: midbrain
          participant_id: sub-Una
          files: []                      # empty => scan the folder automatically
```

- If `files` is empty, MIMOSA scans the folder and lists every `.czi`
  automatically (function `update_yaml_with_slices` in
  `BIDS/bids_metadata.py`).
- For each listed file, it tries to read the **slice numbers** from the file
  name, e.g. `MIO..._104_112_120_128.czi` declares slices 104, 112, 120, 128
  (function `extract_slices_from_filename`). The pattern needs the numbers at
  the end of the name, separated by `-` or `_`.
- **If the name does not follow that pattern, the slice list stays empty and
  the file is skipped.** In that case you must fill the `slices` field by hand
  in the YAML:

  ```yaml
  files:
    - filename: scan_without_numbers.czi
      slices: [104, 112, 120, 128]     # written manually
  ```

- You can list several subjects; each is treated as its own brain.


# Pipeline overview

Each brain is a stack of histological sections. The pipeline converts them,
places each one correctly in physical space, and can rebuild a 3D volume.

**Honest note: we did not fully follow the BIDS convention.** BIDS says the
`derivatives` must be produced from the `raw` data. In our dataset the `raw`
data are the OME-TIFF mosaics, but these are only there to **give an idea of
the data** — a way to see the whole set of scenes at a reasonable size. The
real inputs of the pipeline are the `.czi` files, **not** the OME-TIFFs. So
the downsampled derivatives are computed from the `.czi`, not from the
OME-TIFF `raw`.

```
                    ┌─── mimosa_czi2ometiff_converter.py ──►  OME-TIFF mosaic
                    │                                         (filed under: raw, micr/)
   .czi  ───────────┤
 (the only          │
  real source)      └─── mimosa_hpc_converter2.py ────────►  downsampled NIfTI
                                                              (filed under: derivatives)
                                                                     │
                                                                     │  mimosa_slice_preprocessor.py
                                                                     ▼
                                                              padded 2D slices
                                                              (derivatives)
                                                                     │
                                                                     │  mimosa_stacking_2D_2_3D-2.py
                                                                     ▼
                                                              3D volume
                                                              (derivatives)
```

In the diagram, the OME-TIFF `raw` is only an overview of the data. The real
input is the `.czi`, and the downsampled derivatives are computed from it — not
from the OME-TIFF. This is the part that does not fully follow BIDS.


# Usage

Each script runs on its own. For each one: what it does, the command, an
option table, and an explanation of the options that carry a real concept.

---

## 1. `mimosa_hpc_converter2.py` — CZI → downsampled NIfTI / TIFF

Reads each CZI at native resolution and writes reduced images into
`derivatives/2D/downsampled/`. This is the main conversion script.

```bash
python mimosa_hpc_converter2.py -f nii -df 4,6,8 \
  -o /path/to/BIDS -y metadata.yml \
  --block-value mean --threads 16
```

| Option | What it does | Default |
|--------|--------------|---------|
| `-f` | Output format: `tif`, `nii` or `both`. **Required.** | — |
| `-df` | Downsampling exponent(s), factor = 2^exp. **Required.** | — |
| `-o` | Output BIDS root. **Required.** | — |
| `-y` | metadata YAML. | `metadata.yml` |
| `-original_thickness` | Section thickness in µm. | `100` |
| `-reorient` | Currently not applied here (see note). | `none` |
| `--block-value` | `decimate` or `mean`. | `decimate` |
| `--threads` | Threads to produce one image faster. | cores |
| `--refreeze` | Recompute the frozen slice count. | off |

**Understanding the options**

- **`-df` (downsampling).** You give an *exponent*: the real reduction factor
  is `2^exp`. So `-df 4` means factor 16, `-df 8` means factor 256. You can
  pass several at once (`-df 4,6,8`): they are produced from a single native
  read, so extra resolutions are almost free. *(Note: the OME-TIFF converter
  below uses the factor directly, not the exponent.)*

- **`--block-value` (how a block becomes one pixel).** Each output pixel stands
  for a block of native pixels. `decimate` keeps one native pixel per block,
  bit for bit. `mean` averages the whole block, which keeps more signal and is
  better for quantification. Neither invents values, and the vendor
  `zoom`/pyramid is never used. The two methods coexist: `decimate` is tagged
  `desc-downsampled`, `mean` is tagged `desc-downsampledavg`.

- **`--threads` (speed of one image).** One image is read and reduced in
  parallel bands. Set it near your number of CPU cores; beyond that it stops
  helping. The output is identical whatever the thread count.

- **`--refreeze` (slice count).** The total number of slices per brain is
  frozen once (see *Frozen slice count* below). Use `--refreeze` only when the
  complete set of a brain genuinely changed; never for routine partial runs.

- **`-reorient` (currently does nothing here).** This option is accepted but
  not applied at the conversion step. The real reorientation of the brain into
  the anatomical frame happens later, at the 3D stacking step
  (`mimosa_stacking_2D_2_3D-2.py`, see its `-reorient`).

---

## 2. `mimosa_czi2ometiff_converter.py` — CZI → OME-TIFF mosaic

Stitches all scenes of a CZI into one whole-slide OME-TIFF written to
`sub-<subject>/ses-<session>/micr/`. This is the BIDS raw image.

```bash
python mimosa_czi2ometiff_converter.py -y metadata.yml \
  -bids_root /path/to/BIDS -df 8 -channels 0,1 --threads 16
```

| Option | What it does | Default |
|--------|--------------|---------|
| `-y` | metadata YAML. **Required.** | — |
| `-bids_root` | Output BIDS root. **Required.** | — |
| `-df` | Downsampling **factor** among `1, 2, 4, 6, 8`. | `8` |
| `-channels` | Channels to convert, e.g. `0` or `0,1`. | `0,1` |
| `-patch_size` | Patch size (px) used to read the CZI. | `6144` |
| `--threads` | Patches read in parallel. | cores |
| `--compression` | `zlib` (lossless), `jpegxr` or `jpeg2000` (lossy, much smaller). | `zlib` |
| `--quality` | Force of the lossy compression. **Only affects `jpegxr`/`jpeg2000`, ignored for `zlib`.** | `0.5` |

**Understanding the options**

- **`-df` (downsampling factor, not exponent).** Here the number *is* the
  factor: `-df 8` means factor 8. This differs from the NIfTI converter, where
  `-df 8` means factor 256. Do not confuse the two.

- **`-channels`.** A CZI can hold several fluorescence channels. Give the ones
  you want, comma-separated. Each produces its own OME-TIFF.

- **`-patch_size`.** The mosaic is too big to read at once, so it is read in
  square patches of this size (native pixels). You rarely need to change it.

- **`--threads`.** Patches are read in parallel. They cover disjoint regions of
  the mosaic, so the result is byte-for-byte identical to a single-thread run,
  only faster.

- **`--compression` (which method).** Chooses how the OME-TIFF is compressed.
  `zlib` is **lossless**: it keeps every pixel value exactly, but it barely
  compresses fluorescence data, so a full-resolution file can be larger than
  the CZI. `jpegxr` and `jpeg2000` are **lossy**: much smaller (like the CZI),
  at the cost of slightly altered pixel values. Use lossy only to **look** at
  the data, never to quantify — quantification is done on the downsampled
  NIfTI.

- **`--quality` (how hard the lossy method compresses).** This is a slider for
  the lossy codecs, like the quality setting when you save a JPEG: lower means
  smaller and more degraded. Measured about 6x smaller than lossless at `0.5`.
  **It only affects `jpegxr` and `jpeg2000`. With `zlib` it does nothing,
  because `zlib` is lossless and has no such slider.**

---

## 3. `mimosa_slice_preprocessor.py` — pad 2D slices

Pads the reduced 2D slices to a common size so they can be stacked, into
`derivatives/2D/preproc/`.

```bash
python mimosa_slice_preprocessor.py -bids_root /path/to/BIDS -res 4x
```

| Option | What it does | Default |
|--------|--------------|---------|
| `-bids_root` | BIDS root. **Required.** | — |
| `-res` | Resolution label to preprocess, e.g. `4x`. **Required.** | — |
| `-padding_delta` | Padding margin in pixels. | `100` |
| `-reorient` | Reorientation for the position. | `none` |

**Understanding the options**

- **`-res`.** Slices come in several resolutions (`4x`, `6x`, `8x`). You
  preprocess one resolution at a time; this picks which.

- **`-padding_delta`.** Slices have slightly different sizes. Padding adds a
  margin so they all reach the same shape, which is required before stacking.

---

## 4. `mimosa_stacking_2D_2_3D-2.py` — 2D slices → 3D volume

Stacks the padded slices into a single 3D volume.

```bash
python mimosa_stacking_2D_2_3D-2.py -bids_root /path/to/BIDS \
  -res 4x -reorient x,-z,-y -original_thickness 100
```

| Option | What it does | Default |
|--------|--------------|---------|
| `-bids_root` | BIDS root. **Required.** | — |
| `-res` | Resolution label to stack, e.g. `4x`. **Required.** | — |
| `-reorient` | Orientation of the final 3D volume. | `none` |
| `-original_thickness` | Spacing between sections in µm. | `200` |

**Understanding the options**

- **`-reorient` (put the brain in the right anatomical frame).** A scanned
  slide is not always aligned with the anatomical reference frame that viewers
  like FSLeyes expect (left/right, anterior/posterior, superior/inferior). So
  the stacked volume can come out rotated or flipped compared to the real
  anatomy. `-reorient` fixes this: it rotates and flips the volume axes so the
  3D brain is correctly oriented in the anatomical frame. You give the target
  axis order, e.g. `x,-z,-y` (the `-` means that axis is flipped). `none`
  keeps the acquisition axes unchanged. **This is where the real
  reorientation happens** — the reorientation of the whole reconstructed
  brain.

- **`-original_thickness`.** The physical distance between two sections, in µm.
  It sets the spacing of the volume along the depth (Z) axis.

---

## 5. `check_alignment.py` — verification tool

Checks that two resolutions of the same slice tile exactly. For debugging,
not part of the conversion.

```bash
python check_alignment.py image_res-6x.nii.gz image_res-8x.nii.gz
```

It prints `the two grids tile exactly` when everything is correct.


# Data organization (BIDS layout)

```
BIDS/
├── sourcedata/
│   └── sub-X/                                  marker of the original CZI
├── sub-X/ses-Y/micr/
│   └── ..._FLUO.ome.tiff                       raw OME-TIFF mosaic
├── derivatives/2D/
│   ├── downsampled/sub-X/ses-Y/micr/res-Nx/
│   │   ├── ..._desc-downsampled_FLUO.nii.gz    reduced images (decimate)
│   │   └── ..._desc-downsampledavg_FLUO.nii.gz reduced images (mean)
│   └── preproc/                                padded 2D slices
├── derivatives/ (3D)                           reconstructed volumes
└── code/
    └── mimosa_slice_references.json            frozen slice count per subject
```


# Frozen slice count

The total number of slices of a brain is computed **once** per subject and
stored in `code/mimosa_slice_references.json`. After that first pass it is
reused unchanged.

Why it matters: a slice's depth in the volume depends on this total. If the
total could change, deleting CZI files or interrupting a run would shift every
slice. By freezing it, you can delete CZI to export only a few
high-resolution slices and they still land at the exact depth they occupy in
the complete brain.

Run the **first full pass with all CZI present**, so the frozen total is
correct. Use `--refreeze` only when a brain's complete slice set genuinely
changes.
