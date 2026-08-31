# Utilities

Helper scripts that are not part of the main pipeline but are useful around it.

## Slice reference table

Builds a table of the correspondence between each subject and its slices: for
every slice, its chunk, its Z coordinate (depth) and the path to the slice.

### Command

```bash
python utils/mimosa_slice_references_tsv.py <bids_root> [output.tsv]
```

If the output path is omitted, it writes
`derivatives/2D/mimosa_slice_references.tsv`.

### What it does

It scans every `sub-*.json` sidecar that has a matching `.nii.gz` and carries
`SlicePosition` and `NumberOfSlices`, and writes one row per slice
(subject, session, chunk):

```text
subject   session   chunk   Z_mm   channels   resolutions
```

- `chunk` is the slice's chunk number (`SliceIndex`).
- `Z_mm` is the physical depth, computed from the centered stack formula
  (see [geometry.md](geometry.md#slice-vocabulary-and-depth)). Its sign follows
  the reorientation recorded in the JSON (`-z` / `flip_z` flips the axis).
- `channels` lists every stain found for that slice (e.g. `C0,C1`).
- `resolutions` lists every resolution found for that slice (e.g. `4x,6x,8x`).

The file is a TSV (tab-separated), which opens directly in a spreadsheet or with
`pandas.read_csv(path, sep="\t")`.
