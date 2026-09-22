# Stacking (2D slices -> 3D reconstruction)

Stacks the padded 2D slices of a subject into a single 3D NIfTI reconstruction.
Reads from `derivatives/2D/padded/` and writes the 3D volume under
`derivatives/`. The volume gets a spatial matrix (SForm/QForm) that keeps every
slice at its true physical depth, and can be reoriented into the desired
anatomical frame.

## Command

```bash
python 3D/mimosa_stacking_2D_2_3D.py \
  -bids_root /path/to/BIDS \
  -res 4x \
  -reorient x,-z,-y \
  -original_thickness 100
```

## Options

| Option | What it does | Default |
|--------|--------------|---------|
| `-bids_root` | BIDS root. **Required.** | — |
| `-res` | Resolution label to stack, e.g. `4x`. **Required.** | — |
| `-reorient` | Orientation of the final 3D volume, e.g. `x,-z,-y`. | `none` |
| `-original_thickness` | Spacing between sections in µm. | `200` |

## Understanding the options

- **`-res`.** Stack one resolution at a time (`4x`, `6x`, `8x`). It must match a
  resolution you have padded.

- **`-reorient` (put the brain in the right anatomical frame).** The final 3D
  volume can be permuted and flipped to match the desired frame. For example
  `x,-z,-y` means:

```text
  new axis 0 <- old X
  new axis 1 <- old Z, flipped
  new axis 2 <- old Y, flipped
```

  Unlike the 2D step, here the reorientation is applied to **both** the voxel
  array and its matrix, using only axis permutations and flips (no resampling,
  no interpolation).

- **`-original_thickness`.** The physical distance between two consecutive
  sections, in µm. It sets the spacing of the volume along the stack axis.

## Geometry

How the volume affine is derived from a reference slice, why it stays centered
on zero whatever the reference, and how reorientation is applied are explained
in [geometry.md](geometry.md#3d-volume-affine-matrix).
