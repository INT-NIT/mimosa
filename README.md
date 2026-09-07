# The Mimosa Project

A set of tools for **M**ultiscale **I**maging for mar**MO**set **S**oftware &amp; **A**nalysis.

# Description

The MIMOSA project aims to provide a multiscale, automated, versatile, and user-friendly tool for 3D reconstruction and cell quantification in the brain of the marmoset (<i>Callithrix jacchus</i>) using histological sections. Designed to meet the need for precise and accurate quantification in viral tracing experiments, MIMOSA facilitates efficient analysis.

The tool utilizes DAPI staining to register histological sections to MRI atlases of the marmoset brain, while fluorescent protein labeling enables neuron quantification in targeted areas. MIMOSA integrates Cellpose, allowing users to develop custom-trained models for neuron quantification. Additionally, it includes CZI conversion tools that produce downsampled TIFF/NIfTI derivatives and whole-slide OME-TIF overview images. The current TIFF/NIfTI converter requests reduced-resolution data through the CZI reader `zoom` mechanism, while the spatial position of each NIfTI image is encoded in its SForm/QForm matrices.


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
  format. MIMOSA writes the whole-slide **OME-TIF** mosaics here. OME-TIF is
  a valid BIDS microscopy format and provides a convenient overview of the
  acquisition.
- **`derivatives/`** — the downsampled images, the preprocessed slices, and the
  reconstructed 3D volumes.

### An honest note on the BIDS layers

**We did not fully follow the BIDS convention, and we want to be clear about
it.** BIDS says that files in `derivatives/` must be produced from the `raw`
data. Here the `raw` data are the OME-TIF mosaics, but they are only there to
give an idea of the data — to see the whole set of scenes at a reasonable size.
The real inputs are the `.czi` files, not the OME-TIFs. So our downsampled
`derivatives/` are computed from the `.czi`, not from the OME-TIF `raw`.

File names follow the BIDS entities, for example:

```text
sub-Una_ses-01_sample-slide1_chunk-67_stain-C0_res-8x_desc-downsampled_FLUO.nii.gz
   │       │        │            │          │        │         │          │
subject  session   sample      slice      stain  resolution  method    modality
```

You do not build this layout by hand. You describe your inputs once in a small
YAML file, and the scripts create the folders, the names, and the metadata.





## How to use ?

This repository provides a complete pipeline that takes the original `.czi`
microscopy slides and processes them up to a stacked 3D reconstruction. The
workflow runs in three stages:

1. **Conversion** — convert the original `.czi` slides, either to a global
   overview image or to individual per-scene images
2. **Padding** — align every 2D slice of a subject to a common shape
3. **Stacking** — stack the padded 2D slices into a 3D reconstruction

Follow the stages in order. Each one below links to a detailed page with the
exact command, arguments and expected inputs/outputs.

---

### 1. Conversion

Two converters are provided. They serve different purposes, not just different
formats:

[**PART 1: CZI → OME-TIF**](docs/01_czi_to_ometif.md) — produces a single
OME-TIF per slide, a global overview image that gives an idea of the whole
scanned `.czi` slide, with its JSON sidecar (for microscopy viewers).

[**PART 2: CZI → NIfTI / TIF**](docs/02_czi_to_nifti-tif.md) — extracts every scene
from each slide as an individual, downsampled NIfTI and/or TIF image (with the
correct physical depth in the brain), so each scene can be worked on separately.
This is the output used by the rest of the pipeline.

---

### 2. Padding

[**Slice padding**](docs/03_padding.md) — pad every 2D slice of a subject to a
common target shape so that all slices, resolutions and the stacked result
align.

---

### 3. Stacking

[**2D → 3D stacking**](docs/04_stacking.md) — stack the padded 2D slices into a
single 3D reconstruction.

---

### Utilities & geometry

Extra scripts (slice-reference table, slice finder) and the explanation of the
coordinate system (SForm, `reorient`, physical Z) are documented separately:

[**Utilities**](docs/utilities.md) · [**Geometry**](docs/geometry.md)







# Pipeline overview

Each brain is a stack of histological sections. The pipeline converts them,
places each one correctly in physical space, and can rebuild a 3D volume.

**note: we did not fully follow the BIDS convention.** BIDS says the
`derivatives` must be produced from the `raw` data. In our dataset the `raw`
data are the OME-TIF mosaics, but these are only there to **give an idea of
the data** a way to see the whole set of scenes at a reasonable size. The
real inputs of the pipeline are the `.czi` files, **not** the OME-TIFs. So
the downsampled derivatives are computed from the `.czi`, not from the
OME-TIF `raw`.

```text
                    ┌─── mimosa_czi2ometif_converter.py ──►  OME-TIF mosaic
                    │                                         (filed under: raw, micr/)
   .czi  ───────────┤
 (the only          │
  real source)      └─── mimosa_czi2nii-tif_converter.py ──►  downsampled NIfTI/TIFF
                                                              (filed under: derivatives)
                                                                     │
                                                                     │  mimosa_slice_padding.py
                                                                     ▼
                                                              padded 2D slices
                                                              (derivatives)
                                                                     │
                                                                     │  mimosa_stacking_2D_2_3D.py
                                                                     ▼
                                                              3D volume
                                                              (derivatives)
```

In the diagram, the OME-TIF `raw` is only an overview of the data. The actual
processing pipeline starts from the original `.czi` files.























































































































