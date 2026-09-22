# Configuration: the `metadata.yml` file

Every command reads a `metadata.yml` that declares your subjects and where their
`.czi` files live. Minimal shape:

```yaml
samples:
  entries:
    - path: /path/to/Una/czi/folder     # folder holding this subject's CZI
      subject: Una
      samples:
        - sample_type: technical sample
          derived_from: midbrain
          participant_id: sub-Una
          files: []    
          - filename: 2026_02_02__12_17__0122.czi
            slices:
            - 67
            - 69
            - 71
            - 73                  # empty => scan the folder automatically
```

## How the slices are found

- If `files` is empty, MIMOSA scans the folder and lists every `.czi`
  automatically (`update_yaml_with_slices` in `core/bids/bids_metadata.py`).
- For each listed file, MIMOSA tries to extract the **slice numbers** from the
  filename (for example `MIO..._104_112_120_128.czi` declares slices 104, 112,
  120 and 128).
- These slice numbers define the order of the histological sections in the
  complete brain stack. MIMOSA converts them into a continuous `SlicePosition`,
  used to compute the physical position of each slice
  (see [geometry.md](geometry.md#slice-vocabulary-and-depth)).
- **If the name does not follow that pattern, the slice list stays empty and the
  file is skipped.** In that case, fill the `slices` field by hand:

  ```yaml
  files:
    - filename: scan_without_numbers.czi
      slices: [104, 112, 120, 128]     # written manually
  ```

- You can list several subjects; each is treated as its own brain.
## The `slice_reference` block

```yaml
slice_reference:
  number_of_slices: 277            # depth of the complete volume
  slice_index_to_position:         # chunk (slide label) -> voxel position (rank)
    '2': 0
    '4': 1
    '66': 32
```

Chunk = slide label (2, 4, 6…, with gaps); position = its rank = the voxel index.
Using the chunk directly would inflate the volume and add empty planes between
adjacent sections. Stored once so a partial run (`-only_slices`) reuses the same
total and positions — every slice always lands at the same depth.

## Exporting a subset with `-only_slices`

This is the whole point of keeping the complete `slice_reference`.

- **With the complete reference**, `-only_slices` exports just a few slices, and
  each one is placed at its **true position** in the complete volume — with empty
  (black) gaps where the other slices would be. Example: convert only slices 10
  and 20, and they land at positions 10 and 20, not next to each other.
- **Without it** (a reduced reference, or slices deleted from the YAML), the
  positions are renumbered 0, 1, 2, … and the few slices get **packed one after
  another**, losing their real depth.

So keep the **complete** slice list and its `slice_reference` in the YAML, and use
`-only_slices` on the converter to export a subset. Do **not** delete slices from
the YAML to make a partial run — that would corrupt the depths
(see [geometry.md](geometry.md#why-numberofslices-must-be-the-complete-brain)).

A slice that is declared in `slice_reference` but not converted simply leaves its
position empty in the volume — this is what the stacking reports as `empty slice
positions` (see [04_stacking.md](04_stacking.md)).