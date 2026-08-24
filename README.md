# The Mimosa Project

A set of tools for **M**ultiscale **I**maging for mar**MO**set **S**oftware &amp; **A**nalysis.

# Description

The MIMOSA project aims to provide a multiscale, automated, versatile, and user-friendly tool for 3D reconstruction and cell quantification in the brain of the marmoset (<i>Callithrix jacchus</i>) using histological sections. Designed to meet the need for precise and accurate quantification in viral tracing experiments, MIMOSA facilitates efficient analysis.

The tool utilizes DAPI staining to register histological sections to MRI atlases of the marmoset brain, while fluorescent protein labeling enables neuron quantification in targeted areas. MIMOSA integrates Cellpose, allowing users to develop custom-trained models for neuron quantification. Additionally, it includes CZI conversion tools that produce downsampled TIFF/NIfTI derivatives and whole-slide OME-TIFF overview images. The current TIFF/NIfTI converter requests reduced-resolution data through the CZI reader `zoom` mechanism, while the spatial position of each NIfTI image is encoded in its SForm/QForm matrices.


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
  a valid BIDS microscopy format and provides a convenient overview of the
  acquisition.
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

```text
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
- For each listed file, MIMOSA tries to extract the **slice numbers** from the
  filename (for example `MIO..._104_112_120_128.czi` declares slices 104, 112,
  120 and 128).
- These slice numbers define the order of the histological sections in the
  complete brain stack. MIMOSA converts them into a continuous
  `SlicePosition`, which is used to calculate the physical position of each
  slice.
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

```text
                    ┌─── mimosa_czi2ometiff_converter.py ──►  OME-TIFF mosaic
                    │                                         (filed under: raw, micr/)
   .czi  ───────────┤
 (the only          │
  real source)      └─── mimosa_hpc_converter.py ─────────►  downsampled NIfTI/TIFF
                                                              (filed under: derivatives)
                                                                     │
                                                                     │  mimosa_slice_preprocessor.py
                                                                     ▼
                                                              padded 2D slices
                                                              (derivatives)
                                                                     │
                                                                     │  mimosa_stacking_2D_2_3D.py
                                                                     ▼
                                                              3D volume
                                                              (derivatives)
```

In the diagram, the OME-TIFF `raw` is only an overview of the data. The actual
processing pipeline starts from the original `.czi` files.


# Usage

Each script runs on its own. For each one: what it does, the command, an
option table, and an explanation of the options that carry a real concept.

---

## 1. `mimosa_hpc_converter.py` — CZI → downsampled NIfTI / TIFF

Reads each CZI and generates downsampled TIFF and/or NIfTI images in
`derivatives/2D/downsampled/`. Multiple resolutions can be requested in a
single run. For NIfTI outputs, each slice keeps its physical position in the
brain volume through its SForm/QForm matrices.

```bash
python mimosa_hpc_converter.py -f nii -df 4,6,8 \
  -o /path/to/BIDS -y metadata.yml \
  -original_thickness 100
```

| Option | What it does | Default |
|--------|--------------|---------|
| `-f` | Output format: `tif`, `nii` or `both`. **Required.** | — |
| `-df` | Downsampling exponent(s), factor = `2^exp`. **Required.** | — |
| `-o` | Output BIDS root. **Required.** | — |
| `-y` | metadata YAML. | `metadata.yml` |
| `-original_thickness` | Section thickness/spacing in µm. | `100` |
| `-reorient` | Reorients the slice's **SForm matrix** (not the pixels) into the anatomical frame, e.g. `x,-z,-y`. | `none` |
| `-refreeze` | Recompute the frozen slice count. | off |

**Understanding the options**

- **`-df` (downsampling).** You give an *exponent*: the real reduction factor
  is `2^exp`. So `-df 4` means factor 16, `-df 8` means factor 256. You can
  pass several at once (`-df 4,6,8`). The current converter requests the
  reduced image through the CZI reader `zoom` mechanism.

- **`-refreeze` (slice count).** MIMOSA records the total number of slice
  positions of each brain the first time it processes a complete dataset.
  This frozen value is then reused to compute the physical position of every
  slice, even if only a subset of CZI files is processed later. Without this
  reference, exporting only a few slices would change their computed depth in
  the reconstructed volume. Use `-refreeze` only when the complete slice set
  of a brain has genuinely changed, for example when slices were permanently
  added or removed, not for routine partial exports.

- **`-reorient` (orient the slices in the anatomical frame).** A scanned slide
  is not always aligned with the anatomical reference frame that viewers like
  FSLeyes expect. `-reorient` permutes and flips the axes, e.g. `x,-z,-y`
  (the `-` flips that axis). `none` keeps the acquisition axes.

  **Important — it changes only the SForm matrix, not the pixels.** For a 2D
  slice, `-reorient` rewrites the spatial matrix that places the slice in
  physical space. It does **not** rotate, interpolate or resample the 2D pixel
  array. The actual 3D array reorientation is performed later when the 3D
  volume is built.

### How the affine matrix of a 2D slice is calculated

Each downsampled NIfTI slice receives a 4 × 4 affine matrix:

```text
[ pixel_spacing_x       0                  0              origin_x ]
[       0         pixel_spacing_y          0              origin_y ]
[       0               0            slice_spacing        origin_z ]
[       0               0                  0                  1     ]
```

where:

```text
pixel_spacing_x = physical size of one exported pixel along X, in mm
pixel_spacing_y = physical size of one exported pixel along Y, in mm
slice_spacing   = physical spacing between histological sections, in mm

origin_x = physical X coordinate of voxel (0, 0, 0)
origin_y = physical Y coordinate of voxel (0, 0, 0)
origin_z = physical Z coordinate of the current histological section
```

#### X and Y spacing

The output pixel spacing comes from the exported image resolution:

```text
pixel_spacing_x = exported_pixel_size_x_um / 1000
pixel_spacing_y = exported_pixel_size_y_um / 1000
```

The division by 1000 converts micrometres to millimetres.

#### X and Y origin

The X/Y origin is based on the **native physical extent** of the CZI scene,
rather than on the rounded number of pixels of the downsampled image.

Conceptually:

```text
origin_x = - native_physical_width_mm / 2
origin_y = - native_physical_height_mm / 2
```

This allows different output resolutions to stay in the same physical
reference. A fine image can contain many small pixels and a coarse image fewer
large pixels while both describe the same physical field of view.

#### Z spacing

The stack spacing is:

```text
slice_spacing = original_thickness_um / 1000
```

For example:

```text
original_thickness = 100 um
slice_spacing = 100 / 1000
slice_spacing = 0.1 mm
```

#### Z position of a slice

Let:

```text
slice_position = SlicePosition of the current slice
number_of_slices = total number of slice positions in the complete brain
```

The physical Z position of the current slice is:

```text
origin_z =
(slice_position - (number_of_slices - 1) / 2) * slice_spacing
```

This places the complete stack around physical coordinate zero.

Example with:

```text
number_of_slices = 4
slice_spacing = 0.1 mm
```

The slice positions are:

```text
slice_position = 0 -> Z = -0.15 mm
slice_position = 1 -> Z = -0.05 mm
slice_position = 2 -> Z =  0.05 mm
slice_position = 3 -> Z =  0.15 mm
```

The geometric center of the complete stack is therefore at:

```text
Z = 0
```

With an even number of slices, zero lies between the two central slices.

---

## 2. `mimosa_czi2ometiff_converter.py` — CZI → OME-TIFF mosaic

Stitches all scenes of a CZI into one whole-slide OME-TIFF written to
`sub-<subject>/ses-<session>/micr/`. This is the BIDS raw image.

```bash
python mimosa_czi2ometiff_converter.py -y metadata.yml \
  -bids_root /path/to/BIDS -df 8 -channels 0,1 -threads 16
```

| Option | What it does | Default |
|--------|--------------|---------|
| `-y` | metadata YAML. **Required.** | — |
| `-bids_root` | Output BIDS root. **Required.** | — |
| `-df` | Downsampling **factor** among `1, 2, 4, 6, 8`. | `8` |
| `-channels` | Channels to convert, e.g. `0` or `0,1`. | `0,1` |
| `-patch_size` | Patch size (px) used to read the CZI. | `6144` |
| `-compression` | `zlib` (lossless), `jpegxr` or `jpeg2000` (lossy, much smaller). | `zlib` |
| `-quality` | Force of the lossy compression. **Only affects `jpegxr`/`jpeg2000`, ignored for `zlib`.** | `0.5` |

**Understanding the options**

- **`-df` (downsampling factor, not exponent).** Here the number *is* the
  factor: `-df 8` means factor 8. This differs from the NIfTI converter, where
  `-df 8` means factor 256.

- **`-channels`.** A CZI can hold several fluorescence channels. Give the ones
  you want, comma-separated. Each produces its own OME-TIFF.

- **`-patch_size`.** The mosaic is too big to read at once, so it is read in
  square patches of this size.

- **`-compression`.** `zlib` is lossless. `jpegxr` and `jpeg2000` are lossy
  and produce smaller files.

- **`-quality`.** Controls the lossy compression level. It has no effect on
  `zlib`.

---

## 3. `mimosa_slice_preprocessor.py` — pad 2D slices

Pads the reduced 2D slices to a common size so they can be stacked into a
single 3D array.

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
  preprocess one resolution at a time.

- **`-padding_delta`.** Slices can have different shapes. Padding adds a
  margin so that all slices reach the same final shape before stacking.

### How padding updates the affine matrix

Padding adds zero-valued pixels around the original image. The biological
tissue must remain at the same physical coordinates after this operation.

Before padding, the affine matrix contains:

```text
[ pixel_spacing_x       0                  0              origin_x ]
[       0         pixel_spacing_y          0              origin_y ]
[       0               0            slice_spacing        origin_z ]
[       0               0                  0                  1     ]
```

where:

```text
pixel_spacing_x = physical size of one pixel along X, in mm
pixel_spacing_y = physical size of one pixel along Y, in mm
slice_spacing   = physical spacing between sections, in mm

origin_x = physical X coordinate of voxel (0, 0, 0)
origin_y = physical Y coordinate of voxel (0, 0, 0)
origin_z = physical Z coordinate of the slice
```

Let:

```text
padding_before_x = number of pixels added before the image along X
padding_before_y = number of pixels added before the image along Y
```

Each added pixel corresponds to a physical displacement.

Therefore:

```text
padded_origin_x =
original_origin_x - padding_before_x * pixel_spacing_x

padded_origin_y =
original_origin_y - padding_before_y * pixel_spacing_y

padded_origin_z =
original_origin_z
```

The Z origin does not change because padding is added only in the 2D image
plane.

The same operation can be written in vector form:

```text
padded_origin =
original_origin
- padding_before_x * x_axis_vector
- padding_before_y * y_axis_vector
```

where:

```text
x_axis_vector = first column of the original affine matrix
y_axis_vector = second column of the original affine matrix
```

So the image grid becomes larger, but the original tissue remains at exactly
the same physical coordinates.

---

## 4. `mimosa_stacking_2D_2_3D.py` — 2D slices → 3D volume

Stacks the padded slices into a single 3D volume.

```bash
python mimosa_stacking_2D_2_3D.py -bids_root /path/to/BIDS \
  -res 4x -reorient x,-z,-y -original_thickness 100
```

| Option | What it does | Default |
|--------|--------------|---------|
| `-bids_root` | BIDS root. **Required.** | — |
| `-res` | Resolution label to stack, e.g. `4x`. **Required.** | — |
| `-reorient` | Orientation of the final 3D volume. | `none` |
| `-original_thickness` | Spacing between sections in µm. | `200` |

**Understanding the options**

- **`-reorient` (put the brain in the right anatomical frame).** The final 3D
  volume can be permuted and flipped to match the desired anatomical frame.

  For example:

  ```text
  x,-z,-y
  ```

  means:

  ```text
  new axis 0 <- old X
  new axis 1 <- old Z, flipped
  new axis 2 <- old Y, flipped
  ```

- **`-original_thickness`.** The physical distance between two sections, in
  µm. It sets the spacing of the volume along the stack axis.

### How the affine matrix of the 3D volume is calculated

The 3D volume does not receive a completely unrelated spatial matrix.

MIMOSA starts from the affine matrix of one padded slice used as a reference.

The available slices are sorted by `SlicePosition`, and the first available
padded slice is selected as the reference.

For clarity, the following names are used:

```text
reference_slice_position =
SlicePosition of the padded slice used as reference

reference_slice_matrix =
affine matrix of the padded reference slice

reference_slice_origin =
translation stored in the reference slice matrix

stack_axis_vector =
third column of the reference slice matrix

volume_matrix =
affine matrix assigned to the reconstructed 3D volume

volume_origin =
translation stored in the volume matrix
```

#### Step 1 - Start from the reference slice matrix

The reference slice already contains:

```text
- X/Y pixel spacing
- X/Y origin after padding
- spacing along the stack axis
- physical position of the reference slice
```

MIMOSA copies this matrix as the starting point for the volume matrix.

#### Step 2 - Recover the origin of volume position 0

The reference slice matrix describes the physical position of one particular
slice.

The volume matrix must instead describe the physical position of:

```text
volume[:, :, 0]
```

If the reference slice is at:

```text
reference_slice_position = 20
```

then its origin corresponds to stack position 20, not stack position 0.

MIMOSA therefore moves the origin backward by 20 stack steps.

In general:

```text
volume_origin =
reference_slice_origin
- reference_slice_position * stack_axis_vector
```

Before reorientation, the stack axis corresponds to the third affine column.

For a simple axis-aligned stack, the calculation along Z becomes:

```text
volume_z_origin =
reference_slice_z
- reference_slice_position * slice_spacing
```

where:

```text
reference_slice_z =
physical Z coordinate stored in the reference slice matrix

slice_spacing =
physical spacing between consecutive histological sections, in mm
```

#### Step 3 - Why the volume remains centered along the stack axis

The reference slice already has the centered position:

```text
reference_slice_z =
(reference_slice_position - (number_of_slices - 1) / 2)
* slice_spacing
```

The volume origin is:

```text
volume_z_origin =
reference_slice_z
- reference_slice_position * slice_spacing
```

Replace `reference_slice_z` by its formula:

```text
volume_z_origin =
(reference_slice_position - (number_of_slices - 1) / 2)
* slice_spacing
- reference_slice_position * slice_spacing
```

The two terms containing `reference_slice_position` cancel:

```text
volume_z_origin =
-((number_of_slices - 1) / 2) * slice_spacing
```

Therefore, the volume matrix always starts at the physical position of stack
position 0, independently of which available slice was used as the reference.

#### Example

Suppose:

```text
number_of_slices = 4
slice_spacing = 0.1 mm
```

Then:

```text
volume_z_origin =
-((4 - 1) / 2) * 0.1

volume_z_origin =
-1.5 * 0.1

volume_z_origin = -0.15 mm
```

The physical positions of the volume slices are:

```text
volume slice 0 -> -0.15 mm
volume slice 1 -> -0.05 mm
volume slice 2 ->  0.05 mm
volume slice 3 ->  0.15 mm
```

The position of any volume slice is therefore:

```text
physical_z_of_volume_slice =
volume_z_origin
+ volume_slice_index * slice_spacing
```

#### Step 4 - Geometric center of the complete volume

The center of an axis containing `number_of_slices` positions is:

```text
center_slice_index =
(number_of_slices - 1) / 2
```

Its physical position is:

```text
center_z =
volume_z_origin
+ center_slice_index * slice_spacing
```

Because:

```text
volume_z_origin =
-((number_of_slices - 1) / 2) * slice_spacing
```

the two terms cancel:

```text
center_z = 0
```

The complete stack is therefore centered around physical coordinate zero along
the stack axis.

With an even number of slices, the center lies between the two central slices.

### Reorientation of the 3D volume

When `-reorient` is used, MIMOSA applies the same axis operation to:

```text
1. the voxel array
2. the volume matrix
```

For an axis permutation, the corresponding affine columns are permuted in the
same way.

For a flipped axis, the direction stored in the corresponding affine column
changes sign.

The origin must also move to the position of the old last voxel of that axis.

The calculation is:

```text
new_volume_origin =
old_volume_origin
+ old_axis_vector * (axis_size - 1)
```

where:

```text
old_volume_origin =
origin before the flip

old_axis_vector =
affine column corresponding to the flipped axis before the flip

axis_size =
number of voxels along that axis
```

This preserves the physical position of every voxel after the flip.

The operation uses only axis permutations and flips. It does not require
resampling or interpolation of the 3D voxel values.

Finally, the resulting volume matrix is written to both the SForm and the
QForm of the output NIfTI.


# Data organization (BIDS layout)

```text
BIDS/
├── sourcedata/
│   └── sub-X/                                  marker of the original CZI
├── sub-X/ses-Y/micr/
│   └── ..._FLUO.ome.tiff                       raw OME-TIFF mosaic
├── derivatives/2D/
│   ├── mimosa_slice_references.json            frozen slice count per subject
│   ├── downsampled/sub-X/ses-Y/micr/res-Nx/
│   │   └── ..._desc-downsampled_FLUO.nii.gz    downsampled NIfTI images
│   └── preproc/                                padded 2D slices
└── derivatives/                                reconstructed 3D volumes
```


# Frozen slice count

The total number of slice positions of a brain is computed once per subject
and stored in:

```text
derivatives/2D/mimosa_slice_references.json
```

After the first complete pass, this reference is reused unchanged.

The physical depth of a slice depends on the total number of positions because
the centered stack coordinate uses:

```text
physical_z =
(slice_position - (number_of_slices - 1) / 2)
* slice_spacing
```

where:

```text
slice_position =
position of the current histological section in the complete stack

number_of_slices =
total number of slice positions in the complete brain

slice_spacing =
physical spacing between consecutive histological sections
```

If `number_of_slices` changed simply because only a subset of CZI files was
present during a later run, all physical slice positions would move.

For example, if the complete brain contains:

```text
number_of_slices = 200
```

and a later run exports only 10 slices, those slices must still be positioned
using:

```text
number_of_slices = 200
```

not:

```text
number_of_slices = 10
```

Freezing the complete reference prevents this problem.

It allows MIMOSA to export only a few high-resolution slices later while
keeping exactly the same physical positions that those slices have in the
complete brain.

Run the first full pass with all CZI files present so that the frozen reference
is correct.

Use `-refreeze` only when the complete slice set of a brain has genuinely
changed.
