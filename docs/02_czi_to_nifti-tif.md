# CZI -> NIfTI / TIFF (per-scene extraction)

Reads each `.czi` slide and extracts every scene as an individual downsampled
image in `derivatives/2D/downsampled/`, as NIfTI and/or TIFF. Several
resolutions can be requested in a single run. Both formats carry the geometry
(the SForm matrix) in their JSON sidecar, so a slice keeps its physical position
in the brain in either format. The NIfTI additionally writes the SForm / QForm
into the `.nii.gz` header itself — which is why the NIfTI is the output consumed
by the rest of the pipeline (padding, stacking). With `-f both`, the two
sidecars carry the exact same SForm and differ only in their `ConvertedTo` field.

## Command

```bash
python 2D/conversion/mimosa_czi2nii-tif_converter.py \
  -f nii \
  -df 4,6,8 \
  -o /path/to/BIDS \
  -y metadata.yml \
  -original_thickness 100
```

## Options

| Option | What it does | Default |
|--------|--------------|---------|
| `-f` | Output format: `tif`, `nii` or `both`. **Required.** | — |
| `-df` | Downsampling exponent(s), factor = `2^exp`. **Required.** | — |
| `-o` | Output BIDS root. **Required.** | — |
| `-y` | metadata YAML. | `metadata.yml` |
| `-original_thickness` | Section thickness/spacing in µm. | `100` |
| `-reorient` | Reorients the slice **SForm matrix** (not the pixels), e.g. `x,-z,-y`. | `none` |
| `-only_slices` | Convert only these slice indices (e.g. `60,62,63`). Positions still come from the full YAML. | all |

## Understanding the options

- **`-df` (exponent).** The real reduction factor is `2^exp`: `-df 4` -> 16,
  `-df 8` -> 256. Pass several at once (`-df 4,6,8`); several resolutions cost
  one single native read.

- **`-f` (output format).** In `both` mode the two JSON sidecars carry the same
  SForm and differ only in `ConvertedTo` (`NIfTI and TIF`). Only the NIfTI writes
  the SForm/QForm into its header, so only the NIfTI feeds the next steps.

- **`-only_slices`.** Positions and totals always come from the **complete** YAML
  slice list, so exported slices keep their true depth. Use it to export a
  subset instead of deleting slices from the YAML.

- **`-reorient`.** Rewrites only the SForm matrix, not the pixels — the real 3D
  reorientation happens at stacking.

## Geometry

How the 2D slice affine matrix (pixel spacing, origin, Z depth) is computed is
explained in [geometry.md](geometry.md#2d-slice-affine-matrix).
