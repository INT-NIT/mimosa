# EBrains dataset — commands

The dataset contains OME-TIFF and NIfTI images. Resolution: `8x` for all slices,
`2x` for a few chosen slices. Reorientation: `x,-z,-y`.

Run the commands from the repository root, and replace every `.../` with your own
paths (the BIDS root and the `metadata.yml`).

---

## Configuration — `metadata.yml`

Details: [`../00_configuration.md`](../00_configuration.md)

```yaml
dataset_description:
  Name: MIMOSA Microscopy Dataset
  BIDSVersion: 1.11.1
  DatasetType: raw
  Authors: [Hanane Boudlal, Guillaume Ibos, Arnaud Le Troter]
  GeneratedBy:
  - Name: MIMOSA
    Description: CZI microscopy conversion pipeline
    CodeURL: https://github.com/INT-NIT/mimosa.git

participants_tsv:
  columns: [participant_id, species]
  rows:
  - {participant_id: sub-Marmot, species: Marmouset}
  - {participant_id: sub-Sully, species: Marmouset}

raw_json:
  MicroscopyTechnique: Fluorescence microscopy
  SampleEnvironment: ex vivo
  BodyPart: Brain

samples:
  columns: [sample_id, participant_id, sample_type, derived_from, source_filename]
  entries:
  - path: .../6-Marmot-MJO16052401/originaux
    subject: '01'
    samples:
    - sample_type: tissue
      participant_id: sub-01
      SampleStaining: [DAPI, EGFP, DsRed]
      files:
      - filename: MJO16052401_Cx_104_106_108_110.czi
        slices: [104, 106, 108, 110]
      # ... (all of sub-01's .czi files)
    slice_reference:
      number_of_slices: 251          # total slices of sub-01
      slice_index_to_position:       # each slice index -> its position in the volume
        '104': 51
        '106': 52
        # ... (251 entries in total)

  - path: .../5-Sully-MIO21100401/originaux
    subject: '02'
    samples:
    - sample_type: tissue
      participant_id: sub-02
      SampleStaining: [DAPI, EGFP]
      files:
      - filename: MIO21100401_Cx_66_68_70_74.czi
        slices: [66, 68, 70, 74]
      # ... (all of sub-02's .czi files)
    slice_reference:
      number_of_slices: 277          # total slices of sub-02
      slice_index_to_position:
        '66': 32
        '68': 33
        # ... (277 entries in total)
```

---

## 1. CZI → OME-TIFF

Details: [`../01_czi_to_ometif.md`](../01_czi_to_ometif.md)

```bash
python 2D/conversion/mimosa_czi2ometif_converter.py \
  -y .../metadata.yml \
  -bids_root .../BIDS-EBrains \
  -df 8 \
  -channels 0
```

**Terminal output:**

```text
Downsampling exponent: 8 -> factor 256
dataset_description.json created
participants.json created
participants.tsv created
============================================================
BIDS dataset initialized: /envau/work/nit/users/boudlal.h/BIDS-EBrains-test
============================================================
MIMOSA - reading slices from metadata.yml
============================================================
  sub-01        119 files  (from YAML)
  sub-02        116 files  (from YAML)
WARNING: no slices for: MJO16052401_Cx_512_514x.czi

>>> Processing: MJO16052401_Cx_36_38_40_42_44_46_48_50_52.czi
    Subject: 01, Date: 2024-07-26T18:18:25.7716027+02:00, Sample: slide
BIDS info: {'sub': '01', 'ses': '01', 'acq_time': '2024-07-26T18:18:25.7716027+02:00', 'acq_sig': 'Fluorescence-resolution-0.32x0.32', 'sample': None, 'chunk': None, 'bids_root_path': '/envau/work/nit/users/boudlal.h/BIDS-EBrains-test'}
Placeholder: MJO16052401_Cx_36_38_40_42_44_46_48_50_52.czi

================================================================================
Input CZI: /envau/work/invibe/USERS/IBOS/data/Marmoset/lames/1-renamed/6-Marmot-MJO16052401/originaux/MJO16052401_Cx_36_38_40_42_44_46_48_50_52.czi
Subject: 01 | Session: 01 | Sample: slide01
SliceIndices: [36, 38, 40, 42, 44, 46, 48, 50, 52] | Channels: (0,)
Downsampling: 256 | Patch size: 6144
================================================================================

Output pixel size: X=83.1393913836813 um  Y=83.1393913836813 um

Total bounding rectangle: (-168700, 3061, 133622, 63109)
Mosaic output size: (522, 247)

--------------------------------------------------------------------------------
Converting sample=slide01, SliceIndices=[36, 38, 40, 42, 44, 46, 48, 50, 52], stain=C0
--------------------------------------------------------------------------------
slide01 C0 ds256x |████████████████████████████████████████| 242/242 [100%] in 1.9s (129.00/s) 
Written: /envau/work/nit/users/boudlal.h/BIDS-EBrains-test/sub-01/ses-01/micr/sub-01_ses-01_sample-slide01_stain-C0_FLUO.ome.tif
sidecar created: /envau/work/nit/users/boudlal.h/BIDS-EBrains-test/sub-01/ses-01/micr/sub-01_ses-01_sample-slide01_stain-C0_FLUO.json
is_ome: True | is_bigtiff: True | shape: (247, 522) | axes: YX

>>> Processing: MJO16052401_Cx_54_56_58_60_62_64_66_68_70.czi
    Subject: 01, Date: 2024-07-26T19:19:12.5071834+02:00, Sample: slide
BIDS info: {'sub': '01', 'ses': '01', 'acq_time': '2024-07-26T19:19:12.5071834+02:00', 'acq_sig': 'Fluorescence-resolution-0.32x0.32', 'sample': None, 'chunk': None, 'bids_root_path': '/envau/work/nit/users/boudlal.h/BIDS-EBrains-test'}
Placeholder: MJO16052401_Cx_54_56_58_60_62_64_66_68_70.czi

================================================================================
Input CZI: /envau/work/invibe/USERS/IBOS/data/Marmoset/lames/1-renamed/6-Marmot-MJO16052401/originaux/MJO16052401_Cx_54_56_58_60_62_64_66_68_70.czi
Subject: 01 | Session: 01 | Sample: slide02
SliceIndices: [54, 56, 58, 60, 62, 64, 66, 68, 70] | Channels: (0,)
Downsampling: 256 | Patch size: 6144
================================================================================

Output pixel size: X=83.1393913836813 um  Y=83.1393913836813 um

Total bounding rectangle: (-165629, 1519, 142825, 69257)
Mosaic output size: (558, 271)

--------------------------------------------------------------------------------
Converting sample=slide02, SliceIndices=[54, 56, 58, 60, 62, 64, 66, 68, 70], stain=C0
--------------------------------------------------------------------------------
slide02 C0 ds256x |████████████████████████████████████████| 288/288 [100%] in 2.8s (101.42/s) 
Written: /envau/work/nit/users/boudlal.h/BIDS-EBrains-test/sub-01/ses-01/micr/sub-01_ses-01_sample-slide02_stain-C0_FLUO.ome.tif
sidecar created: /envau/work/nit/users/boudlal.h/BIDS-EBrains-test/sub-01/ses-01/micr/sub-01_ses-01_sample-slide02_stain-C0_FLUO.json
is_ome: True | is_bigtiff: True | shape: (271, 558) | axes: YX

>>> Processing: MJO16052401_Cx_72_74_76_78_80_82_84_86.czi
    Subject: 01, Date: 2024-07-26T20:29:41.3662634+02:00, Sample: slide
BIDS info: {'sub': '01', 'ses': '01', 'acq_time': '2024-07-26T20:29:41.3662634+02:00', 'acq_sig': 'Fluorescence-resolution-0.32x0.32', 'sample': None, 'chunk': None, 'bids_root_path': '/envau/work/nit/users/boudlal.h/BIDS-EBrains-test'}
Placeholder: MJO16052401_Cx_72_74_76_78_80_82_84_86.czi


```

**Example output:**

[OME-TIFF ](../../EBrains-images/sub-01_ses-01_sample-slide06_stain-C0_FLUO.ome.tif)

---

## 2. CZI → NIfTI / TIFF

Details: [`../02_czi_to_nifti-tif.md`](../02_czi_to_nifti-tif.md)

```bash
# 1) all slices, 8x
python 2D/conversion/mimosa_czi2nii-tif_converter.py \
  -f nii \
  -df 8 \
  -o /envau/work/nit/users/boudlal.h/BIDS-EBrains \
  -y metadata.yml \
  -reorient x,-z,-y \
  -original_thickness 100



```

**Terminal output:**

```text
Exported resolutions: 8x
Reduction method    : zoom (ZEN pyramid)
============================================================
BIDS dataset initialized: /envau/work/nit/users/boudlal.h/BIDS-EBrains-test
============================================================
MIMOSA - reading slices from metadata.yml
============================================================
  sub-01        119 files  (from YAML)
  sub-02        116 files  (from YAML)
  SKIP YAML file without slices: MJO16052401_Cx_512_514x.czi
  SKIP YAML file without slices: MJO16052401_Cx_400x_402.czi
  SKIP YAML file without slices: MJO16052401_Cx_416x_418.czi
  SKIP YAML file without slices: MJO16052401_Cx_432x_434.czi
  SKIP YAML file without slices: MJO16052401_Cx_436x_438.czi
  SKIP YAML file without slices: MJO16052401_Cx_444x_446.czi
  SKIP YAML file without slices: MJO16052401_Cx_448x_450x.czi
  SKIP YAML file without slices: MJO16052401_Cx_452x_454.czi
  SKIP YAML file without slices: MJO16052401_Cx_464x_466.czi
  SKIP YAML file without slices: MJO16052401_Cx_472x_474x.czi
  SKIP YAML file without slices: MJO16052401_Cx_480x_482.czi
  SKIP YAML file without slices: MJO16052401_Cx_484x.czi
  SKIP YAML file without slices: MJO16052401_Cx_528_530x.czi
  SKIP YAML file without slices: MJO16052401_Cx_532x_534.czi
  SKIP YAML file without slices: MJO16052401_Cx_502x.czi
  SKIP YAML file without slices: MJO16052401_Cx_548x_550.czi
  SKIP YAML file without slices: MJO16052401_Cx_486x_488.czi
  SKIP YAML file without slices: MJO16052401_Cx_498x_500x.czi
  SKIP YAML file without slices: MJO16052401_Cx_560x_562.czi
  SKIP YAML file without slices: MJO16052401_Cx_564x_566.czi
  SKIP YAML file without slices: MJO16052401_Cx_540x_542x.czi

>>> Processing: MJO16052401_Cx_36_38_40_42_44_46_48_50_52.czi
    Subject: 01, Date: 2024-07-26T18:18:25.7716027+02:00, Sample: slide
on 0: sidecar created: sub-01_ses-01_sample-slide1_chunk-36_stain-C0_res-8x_desc-downsampled_FLUO.json
on 0:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide1_chunk-36_stain-C0_res-8x_desc-downsampled_FLUO.nii.gz
on 1: sidecar created: sub-01_ses-01_sample-slide1_chunk-36_stain-C1_res-8x_desc-downsampled_FLUO.json
on 1:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide1_chunk-36_stain-C1_res-8x_desc-downsampled_FLUO.nii.gz
on 2: sidecar created: sub-01_ses-01_sample-slide1_chunk-36_stain-C2_res-8x_desc-downsampled_FLUO.json
on 2:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide1_chunk-36_stain-C2_res-8x_desc-downsampled_FLUO.nii.gz
Scene 0 |████████████████████████████████████████| 3/3 [100%] in 0.1s (21.58/s) 
on 0: sidecar created: sub-01_ses-01_sample-slide1_chunk-38_stain-C0_res-8x_desc-downsampled_FLUO.json
on 0:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide1_chunk-38_stain-C0_res-8x_desc-downsampled_FLUO.nii.gz
on 1: sidecar created: sub-01_ses-01_sample-slide1_chunk-38_stain-C1_res-8x_desc-downsampled_FLUO.json
on 1:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide1_chunk-38_stain-C1_res-8x_desc-downsampled_FLUO.nii.gz
on 2: sidecar created: sub-01_ses-01_sample-slide1_chunk-38_stain-C2_res-8x_desc-downsampled_FLUO.json
on 2:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide1_chunk-38_stain-C2_res-8x_desc-downsampled_FLUO.nii.gz
Scene 1 |████████████████████████████████████████| 3/3 [100%] in 0.1s (21.61/s) 
on 0: sidecar created: sub-01_ses-01_sample-slide1_chunk-40_stain-C0_res-8x_desc-downsampled_FLUO.json
on 0:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide1_chunk-40_stain-C0_res-8x_desc-downsampled_FLUO.nii.gz
on 1: sidecar created: sub-01_ses-01_sample-slide1_chunk-40_stain-C1_res-8x_desc-downsampled_FLUO.json
on 1:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide1_chunk-40_stain-C1_res-8x_desc-downsampled_FLUO.nii.gz
on 2: sidecar created: sub-01_ses-01_sample-slide1_chunk-40_stain-C2_res-8x_desc-downsampled_FLUO.json
on 2:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide1_chunk-40_stain-C2_res-8x_desc-downsampled_FLUO.nii.gz
Scene 2 |████████████████████████████████████████| 3/3 [100%] in 0.1s (19.32/s) 
on 0: sidecar created: sub-01_ses-01_sample-slide1_chunk-42_stain-C0_res-8x_desc-downsampled_FLUO.json
on 0:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide1_chunk-42_stain-C0_res-8x_desc-downsampled_FLUO.nii.gz
on 1: sidecar created: sub-01_ses-01_sample-slide1_chunk-42_stain-C1_res-8x_desc-downsampled_FLUO.json
on 1:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide1_chunk-42_stain-C1_res-8x_desc-downsampled_FLUO.nii.gz
on 2: sidecar created: sub-01_ses-01_sample-slide1_chunk-42_stain-C2_res-8x_desc-downsampled_FLUO.json
on 2:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide1_chunk-42_stain-C2_res-8x_desc-downsampled_FLUO.nii.gz
Scene 3 |████████████████████████████████████████| 3/3 [100%] in 0.1s (20.24/s) 
on 0: sidecar created: sub-01_ses-01_sample-slide1_chunk-44_stain-C0_res-8x_desc-downsampled_FLUO.json
on 0:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide1_chunk-44_stain-C0_res-8x_desc-downsampled_FLUO.nii.gz
on 1: sidecar created: sub-01_ses-01_sample-slide1_chunk-44_stain-C1_res-8x_desc-downsampled_FLUO.json
on 1:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide1_chunk-44_stain-C1_res-8x_desc-downsampled_FLUO.nii.gz
on 2: sidecar created: sub-01_ses-01_sample-slide1_chunk-44_stain-C2_res-8x_desc-downsampled_FLUO.json
on 2:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide1_chunk-44_stain-C2_res-8x_desc-downsampled_FLUO.nii.gz
Scene 4 |████████████████████████████████████████| 3/3 [100%] in 0.1s (18.93/s) 
on 0: sidecar created: sub-01_ses-01_sample-slide1_chunk-46_stain-C0_res-8x_desc-downsampled_FLUO.json
on 0:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide1_chunk-46_stain-C0_res-8x_desc-downsampled_FLUO.nii.gz
on 1: sidecar created: sub-01_ses-01_sample-slide1_chunk-46_stain-C1_res-8x_desc-downsampled_FLUO.json
on 1:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide1_chunk-46_stain-C1_res-8x_desc-downsampled_FLUO.nii.gz
on 2: sidecar created: sub-01_ses-01_sample-slide1_chunk-46_stain-C2_res-8x_desc-downsampled_FLUO.json
on 2:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide1_chunk-46_stain-C2_res-8x_desc-downsampled_FLUO.nii.gz
Scene 5 |████████████████████████████████████████| 3/3 [100%] in 0.1s (18.22/s) 
on 0: sidecar created: sub-01_ses-01_sample-slide1_chunk-48_stain-C0_res-8x_desc-downsampled_FLUO.json
on 0:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide1_chunk-48_stain-C0_res-8x_desc-downsampled_FLUO.nii.gz
on 1: sidecar created: sub-01_ses-01_sample-slide1_chunk-48_stain-C1_res-8x_desc-downsampled_FLUO.json
on 1:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide1_chunk-48_stain-C1_res-8x_desc-downsampled_FLUO.nii.gz
on 2: sidecar created: sub-01_ses-01_sample-slide1_chunk-48_stain-C2_res-8x_desc-downsampled_FLUO.json
on 2:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide1_chunk-48_stain-C2_res-8x_desc-downsampled_FLUO.nii.gz
Scene 6 |████████████████████████████████████████| 3/3 [100%] in 0.1s (22.01/s) 
on 0: sidecar created: sub-01_ses-01_sample-slide1_chunk-50_stain-C0_res-8x_desc-downsampled_FLUO.json
on 0:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide1_chunk-50_stain-C0_res-8x_desc-downsampled_FLUO.nii.gz
on 1: sidecar created: sub-01_ses-01_sample-slide1_chunk-50_stain-C1_res-8x_desc-downsampled_FLUO.json
on 1:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide1_chunk-50_stain-C1_res-8x_desc-downsampled_FLUO.nii.gz
on 2: sidecar created: sub-01_ses-01_sample-slide1_chunk-50_stain-C2_res-8x_desc-downsampled_FLUO.json
on 2:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide1_chunk-50_stain-C2_res-8x_desc-downsampled_FLUO.nii.gz
Scene 7 |████████████████████████████████████████| 3/3 [100%] in 0.1s (20.34/s) 
on 0: sidecar created: sub-01_ses-01_sample-slide1_chunk-52_stain-C0_res-8x_desc-downsampled_FLUO.json
on 0:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide1_chunk-52_stain-C0_res-8x_desc-downsampled_FLUO.nii.gz
on 1: sidecar created: sub-01_ses-01_sample-slide1_chunk-52_stain-C1_res-8x_desc-downsampled_FLUO.json
on 1:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide1_chunk-52_stain-C1_res-8x_desc-downsampled_FLUO.nii.gz
on 2: sidecar created: sub-01_ses-01_sample-slide1_chunk-52_stain-C2_res-8x_desc-downsampled_FLUO.json
on 2:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide1_chunk-52_stain-C2_res-8x_desc-downsampled_FLUO.nii.gz
Scene 8 |████████████████████████████████████████| 3/3 [100%] in 0.1s (20.59/s) 

>>> Processing: MJO16052401_Cx_54_56_58_60_62_64_66_68_70.czi
    Subject: 01, Date: 2024-07-26T19:19:12.5071834+02:00, Sample: slide
on 0: sidecar created: sub-01_ses-01_sample-slide2_chunk-54_stain-C0_res-8x_desc-downsampled_FLUO.json
on 0:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide2_chunk-54_stain-C0_res-8x_desc-downsampled_FLUO.nii.gz
on 1: sidecar created: sub-01_ses-01_sample-slide2_chunk-54_stain-C1_res-8x_desc-downsampled_FLUO.json
on 1:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide2_chunk-54_stain-C1_res-8x_desc-downsampled_FLUO.nii.gz
on 2: sidecar created: sub-01_ses-01_sample-slide2_chunk-54_stain-C2_res-8x_desc-downsampled_FLUO.json
on 2:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide2_chunk-54_stain-C2_res-8x_desc-downsampled_FLUO.nii.gz
Scene 0 |████████████████████████████████████████| 3/3 [100%] in 0.1s (21.13/s) 
on 0: sidecar created: sub-01_ses-01_sample-slide2_chunk-56_stain-C0_res-8x_desc-downsampled_FLUO.json
on 0:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide2_chunk-56_stain-C0_res-8x_desc-downsampled_FLUO.nii.gz
on 1: sidecar created: sub-01_ses-01_sample-slide2_chunk-56_stain-C1_res-8x_desc-downsampled_FLUO.json
on 1:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide2_chunk-56_stain-C1_res-8x_desc-downsampled_FLUO.nii.gz
on 2: sidecar created: sub-01_ses-01_sample-slide2_chunk-56_stain-C2_res-8x_desc-downsampled_FLUO.json
on 2:   -> derivatives: derivatives/2D/downsampled/sub-01/ses-01/micr/res-8x/sub-01_ses-01_sample-slide2_chunk-56_stain-C2_res-8x_desc-downsampled_FLUO.nii.gz

```

```bash
# 2) a few chosen slices, 2x (kept at their true position via -only_slices)
python 2D/conversion/mimosa_czi2nii-tif_converter.py \
  -f both \
  -df 2 \
  -o .../BIDS-EBrains \
  -y .../metadata.yml \
  -reorient x,-z,-y \
  -original_thickness 100 \
  -only_slices <chosen slice indices, e.g. 66,94,428>
```


**Example output:**

[NIfTI ](../../EBrains-images/sub-01_ses-01_sample-slide6_chunk-108_stain-C0_res-8x_desc-downsampled_FLUO.nii.gz)

---

## 3. Padding

Details: [`../03_padding.md`](../03_padding.md)

```bash
python 2D/padding/mimosa_slice_padding.py \
  -bids_root .../BIDS-EBrains \
  -res 8x \
  -padding_delta 100 \
  -reorient x,-z,-y
```

**Terminal output:**

```text
============================================================
MIMOSA - 2D slice padding
  BIDS root                : /envau/work/nit/users/boudlal.h/BIDS-EBrains-test
  Resolution               : res-8x
  Downsampled slices found : 74
  Already padded           : 0
============================================================
Padding 74 remaining slice(s)...

Subject: sub-01 — target shape: (305, 197)
  IN : sub-01_ses-01_sample-slide1_chunk-36_stain-C0_res-8x_desc-downsampled_FLUO.nii.gz
  OUT: sub-01_ses-01_sample-slide1_chunk-36_stain-C0_res-8x_desc-padded_FLUO.nii.gz
  IN : sub-01_ses-01_sample-slide1_chunk-36_stain-C1_res-8x_desc-downsampled_FLUO.nii.gz
  OUT: sub-01_ses-01_sample-slide1_chunk-36_stain-C1_res-8x_desc-padded_FLUO.nii.gz
  IN : sub-01_ses-01_sample-slide1_chunk-36_stain-C2_res-8x_desc-downsampled_FLUO.nii.gz
  OUT: sub-01_ses-01_sample-slide1_chunk-36_stain-C2_res-8x_desc-padded_FLUO.nii.gz
  IN : sub-01_ses-01_sample-slide1_chunk-38_stain-C0_res-8x_desc-downsampled_FLUO.nii.gz
  OUT: sub-01_ses-01_sample-slide1_chunk-38_stain-C0_res-8x_desc-padded_FLUO.nii.gz
  IN : sub-01_ses-01_sample-slide1_chunk-38_stain-C1_res-8x_desc-downsampled_FLUO.nii.gz
  OUT: sub-01_ses-01_sample-slide1_chunk-38_stain-C1_res-8x_desc-padded_FLUO.nii.gz
  IN : sub-01_ses-01_sample-slide1_chunk-38_stain-C2_res-8x_desc-downsampled_FLUO.nii.gz
  OUT: sub-01_ses-01_sample-slide1_chunk-38_stain-C2_res-8x_desc-padded_FLUO.nii.gz
  IN : sub-01_ses-01_sample-slide1_chunk-40_stain-C0_res-8x_desc-downsampled_FLUO.nii.gz
  OUT: sub-01_ses-01_sample-slide1_chunk-40_stain-C0_res-8x_desc-padded_FLUO.nii.gz
  IN : sub-01_ses-01_sample-slide1_chunk-40_stain-C1_res-8x_desc-downsampled_FLUO.nii.gz
  OUT: sub-01_ses-01_sample-slide1_chunk-40_stain-C1_res-8x_desc-padded_FLUO.nii.gz
  IN : sub-01_ses-01_sample-slide1_chunk-40_stain-C2_res-8x_desc-downsampled_FLUO.nii.gz
  OUT: sub-01_ses-01_sample-slide1_chunk-40_stain-C2_res-8x_desc-padded_FLUO.nii.gz
  IN : sub-01_ses-01_sample-slide1_chunk-42_stain-C0_res-8x_desc-downsampled_FLUO.nii.gz
  OUT: sub-01_ses-01_sample-slide1_chunk-42_stain-C0_res-8x_desc-padded_FLUO.nii.gz
  IN : sub-01_ses-01_sample-slide1_chunk-42_stain-C1_res-8x_desc-downsampled_FLUO.nii.gz
  OUT: sub-01_ses-01_sample-slide1_chunk-42_stain-C1_res-8x_desc-padded_FLUO.nii.gz
  IN : sub-01_ses-01_sample-slide1_chunk-42_stain-C2_res-8x_desc-downsampled_FLUO.nii.gz
  OUT: sub-01_ses-01_sample-slide1_chunk-42_stain-C2_res-8x_desc-padded_FLUO.nii.gz
  IN : sub-01_ses-01_sample-slide1_chunk-44_stain-C0_res-8x_desc-downsampled_FLUO.nii.gz
  OUT: sub-01_ses-01_sample-slide1_chunk-44_stain-C0_res-8x_desc-padded_FLUO.nii.gz
  IN : sub-01_ses-01_sample-slide1_chunk-44_stain-C1_res-8x_desc-downsampled_FLUO.nii.gz
  OUT: sub-01_ses-01_sample-slide1_chunk-44_stain-C1_res-8x_desc-padded_FLUO.nii.gz

```

**Example output:**

[Padding ](../../EBrains-images/sub-02_ses-05_sample-slide85_chunk-428_stain-C1_res-8x_desc-padded_FLUO.nii.gz)

---

## 4. Stacking

Details: [`../04_stacking.md`](../04_stacking.md)

```bash
python 3D/mimosa_stacking_2D_2_3D.py \
  -bids_root .../BIDS-EBrains \
  -res 8x \
  -reorient x,-z,-y \
  -original_thickness 100
```

**Terminal output:**

```text
Running VolumeBuilder3D...
VOLUME: /envau/work/nit/users/boudlal.h/BIDS-EBrains/derivatives/3D/stacking/sub-01/micr/res-8x/sub-01_C0_res-8x_volume.nii.gz
VOLUME: /envau/work/nit/users/boudlal.h/BIDS-EBrains/derivatives/3D/stacking/sub-01/micr/res-8x/sub-01_C1_res-8x_volume.nii.gz
VOLUME: /envau/work/nit/users/boudlal.h/BIDS-EBrains/derivatives/3D/stacking/sub-01/micr/res-8x/sub-01_C2_res-8x_volume.nii.gz
WARNING: 3 empty slice positions for sub-02 C0: [9, 30, 276]
VOLUME: /envau/work/nit/users/boudlal.h/BIDS-EBrains/derivatives/3D/stacking/sub-02/micr/res-8x/sub-02_C0_res-8x_volume.nii.gz
WARNING: 3 empty slice positions for sub-02 C1: [9, 30, 276]
VOLUME: /envau/work/nit/users/boudlal.h/BIDS-EBrains/derivatives/3D/stacking/sub-02/micr/res-8x/sub-02_C1_res-8x_volume.nii.gz

```

**Example output:**

[3D volume ](../../EBrains-images/sub-01_C1_res-8x_volume.nii.gz)
