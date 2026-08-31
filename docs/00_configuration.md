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

## Exporting a subset

Keep the **complete** slice list in the YAML and use `-only_slices` on the
converter to export just a few slices. The total and the positions still come
from the full list, so the exported slices keep their true depth. Do **not**
delete slices from the YAML to make a partial run — that would corrupt the
depths (see [geometry.md](geometry.md#why-numberofslices-must-be-the-complete-brain)).
