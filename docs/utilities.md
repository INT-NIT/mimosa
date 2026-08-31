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
`SlicePosition` and `NumberOfSlices`, and writes one row per slice:

```text
subject   NumberOfSlices   SliceIndex   Z_mm   path
```

- `Z_mm` is the physical depth, computed from the centered stack formula
  (see [geometry.md](geometry.md#slice-vocabulary-and-depth)). Its sign follows
  the reorientation recorded in the JSON (`-z` / `flip_z` flips the axis).
- `path` is the relative path truncated to the session folder (`ses-XX`), so
  each row tells you which session the slice belongs to. The chunk itself is
  already given by the `SliceIndex` column, so the full filename is not repeated.

The file is a TSV (tab-separated), which opens directly in a spreadsheet or with
`pandas.read_csv(path, sep="\t")`.
