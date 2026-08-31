# Padding (align 2D slices)

Pads the downsampled 2D slices of a subject to a common target shape, so that
all slices — and all resolutions — can be stacked into a single 3D array later.
Reads from `derivatives/2D/downsampled/` and writes to
`derivatives/2D/padded/`. The padded slices keep the tissue at exactly the same
physical position (only the image grid grows), and their JSON sidecar is
updated with the padding metadata.

## Algorithm

1. **Scan the subject's slices** and find the **largest width** and the
   **largest height** among them.
2. **Set one common target shape** for the subject:
   `target = (max_width + padding_delta, max_height + padding_delta)`.
3. **Center each slice** inside that target with symmetric zero-padding: the
   tissue is not moved, it is only surrounded by background, so a slice that was
   smaller than its neighbours simply receives more padding.

The result: every slice of the subject ends up with the exact same shape, ready
to be stacked, while each one stays at its true physical position.

## Command

```bash
python 2D/padding/mimosa_slice_padding.py \
  -bids_root /path/to/BIDS \
  -res 4x \
  -padding_delta 100
```

## Options

| Option | What it does | Default |
|--------|--------------|---------|
| `-bids_root` | BIDS root. **Required.** | — |
| `-res` | Resolution label to pad, e.g. `4x`. **Required.** | — |
| `-padding_delta` | Padding margin added in pixels. | `100` |
| `-reorient` | Reference reorientation used to write the SForm of the padded slices. | `none` |

## Understanding the options

- **`-res`.** Slices exist in several resolutions (`4x`, `6x`, `8x`). You pad
  one resolution at a time; run the command again for each resolution you need.

- **`-padding_delta`.** The extra margin added on top of the largest slice, so
  the common target is a bit bigger than the biggest slice of the subject.

- **`-reorient`.** Same reference frame as the conversion step, used to compute
  the SForm of the padded slices. Keep it consistent across steps.

## Output

```text
derivatives/2D/padded/sub-<subject>/ses-<session>/micr/res-<Nx>/
  ..._desc-padded_FLUO.nii.gz
  ..._desc-padded_FLUO.json
```

The padded image's `.json` sidecar is copied from the input (downsampled) slice
and gets two extra fields: `SubjectMaxSize` (the subject's biggest slice size)
and `PaddingTargetShape` (the common padded size). It also recomputes the slice's spatial position (its SForm matrix) so it matches
the shared coordinate system of the final stacked volume.

## Geometry

How padding shifts the affine origin so the tissue stays at the same physical
position is explained in
[geometry.md](geometry.md#padding-and-the-affine-matrix).
