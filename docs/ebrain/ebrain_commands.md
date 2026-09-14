Create dataset folder
```bash
mkdir BIDS-EBrains_test
```

```bash
python 2D/conversion/mimosa_czi2ometif_converter.py  -y  ../metadata_ebrain.yml -bids_root ../BIDS-EBrains_test/ -df 5  -channels 0,1
```

```
BIDS-EBrains_test/
├── dataset_description.json
├── participants.json
├── participants.tsv
├── samples.tsv
├── sourcedata
│   ├── sub-01
│   │   ├── MJO16052401_Cx_296_298.czi
│   │   └── MJO16052401_Cx_36_38_40_42_44_46_48_50_52.czi
│   └── sub-02
│       ├── MIO21100401_Cx_104_112_120_128.czi
│       └── MIO21100401_Cx_390_394.czi
├── sub-01
│   ├── ses-01
│   │   └── micr
│   │       ├── sub-01_ses-01_sample-slide01_stain-C0_FLUO.json
│   │       ├── sub-01_ses-01_sample-slide01_stain-C0_FLUO.ome.tif
│   │       ├── sub-01_ses-01_sample-slide01_stain-C1_FLUO.json
│   │       └── sub-01_ses-01_sample-slide01_stain-C1_FLUO.ome.tif
│   ├── ses-02
│   │   └── micr
│   │       ├── sub-01_ses-02_sample-slide02_stain-C0_FLUO.json
│   │       ├── sub-01_ses-02_sample-slide02_stain-C0_FLUO.ome.tif
│   │       ├── sub-01_ses-02_sample-slide02_stain-C1_FLUO.json
│   │       └── sub-01_ses-02_sample-slide02_stain-C1_FLUO.ome.tif
│   └── sub-01_sessions.tsv
└── sub-02
    ├── ses-01
    │   └── micr
    │       ├── sub-02_ses-01_sample-slide01_stain-C0_FLUO.json
    │       ├── sub-02_ses-01_sample-slide01_stain-C0_FLUO.ome.tif
    │       ├── sub-02_ses-01_sample-slide01_stain-C1_FLUO.json
    │       └── sub-02_ses-01_sample-slide01_stain-C1_FLUO.ome.tif
    ├── ses-02
    │   └── micr
    │       ├── sub-02_ses-02_sample-slide02_stain-C0_FLUO.json
    │       ├── sub-02_ses-02_sample-slide02_stain-C0_FLUO.ome.tif
    │       ├── sub-02_ses-02_sample-slide02_stain-C1_FLUO.json
    │       └── sub-02_ses-02_sample-slide02_stain-C1_FLUO.ome.tif
    └── sub-02_sessions.tsv
```

<table>
<tr>
    <td align="center">
    <img src="https://github.com/mimosa/docs/ebrain/sub-01_ses-01_sample-slide01_stain-C0_FLUO.ome.tif" width="320" />
    </td>
    <td align="center">
    <img src="https://github.com/mimosa/docs/ebrain/sub-01_ses-02_sample-slide02_stain-C1_FLUO.ome.tif" width="400" />
    </td>
</tr>
<tr> 
    <td align="center">sub-01_ses-01_sample-slide01_stain-C0_FLUO.ome.tif </td> 
    <td align="center">sub-01_ses-02_sample-slide02_stain-C1_FLUO.ome.tif</td> 
</tr>

command line output:
```
Downsampling exponent: 5 -> factor 32
dataset_description.json created
participants.json created
participants.tsv created
============================================================
BIDS dataset initialized: /envau/work/nit/users/boudlal.h/BIDS-EBrains_test
============================================================
MIMOSA - reading slices from metadata.yml
============================================================
  sub-01          3 files  (from YAML)
  sub-02          2 files  (from YAML)
WARNING: no slices for: MJO16052401_Cx_512_514x.czi

>>> Processing: MJO16052401_Cx_36_38_40_42_44_46_48_50_52.czi
    Subject: 01, Date: 2024-07-26T18:18:25.7716027+02:00, Sample: slide
BIDS info: {'sub': '01', 'ses': '01', 'acq_time': '2024-07-26T18:18:25.7716027+02:00', 'acq_sig': 'Fluorescence-resolution-0.32x0.32', 'sample': None, 'chunk': None, 'bids_root_path': '/envau/work/nit/users/boudlal.h/BIDS-EBrains_test'}
Placeholder: MJO16052401_Cx_36_38_40_42_44_46_48_50_52.czi

================================================================================
Input CZI: /envau/work/invibe/USERS/IBOS/data/Marmoset/lames/1-renamed/6-Marmot-MJO16052401/originaux/MJO16052401_Cx_36_38_40_42_44_46_48_50_52.czi
Subject: 01 | Session: 01 | Sample: slide01
SliceIndices: [36, 38, 40, 42, 44, 46, 48, 50, 52] | Channels: (0, 1)
Downsampling: 32 | Patch size: 6144
================================================================================

Output pixel size: X=10.392423922960162 um  Y=10.392423922960162 um

Total bounding rectangle: (-168700, 3061, 133622, 63109)
Mosaic output size: (4175, 1972)

--------------------------------------------------------------------------------
Converting sample=slide01, SliceIndices=[36, 38, 40, 42, 44, 46, 48, 50, 52], stain=C0
--------------------------------------------------------------------------------
slide01 C0 ds32x |████████████████████████████████████████| 242/242 [100%] in 4.5s (51.77/s) 
Written: /envau/work/nit/users/boudlal.h/BIDS-EBrains_test/sub-01/ses-01/micr/sub-01_ses-01_sample-slide01_stain-C0_FLUO.ome.tif
sidecar created: /envau/work/nit/users/boudlal.h/BIDS-EBrains_test/sub-01/ses-01/micr/sub-01_ses-01_sample-slide01_stain-C0_FLUO.json
is_ome: True | is_bigtiff: True | shape: (1972, 4175) | axes: YX

--------------------------------------------------------------------------------
Converting sample=slide01, SliceIndices=[36, 38, 40, 42, 44, 46, 48, 50, 52], stain=C1
--------------------------------------------------------------------------------
slide01 C1 ds32x |████████████████████████████████████████| 242/242 [100%] in 4.0s (58.36/s) 
Written: /envau/work/nit/users/boudlal.h/BIDS-EBrains_test/sub-01/ses-01/micr/sub-01_ses-01_sample-slide01_stain-C1_FLUO.ome.tif
sidecar created: /envau/work/nit/users/boudlal.h/BIDS-EBrains_test/sub-01/ses-01/micr/sub-01_ses-01_sample-slide01_stain-C1_FLUO.json
is_ome: True | is_bigtiff: True | shape: (1972, 4175) | axes: YX

>>> Processing: MJO16052401_Cx_296_298.czi
    Subject: 01, Date: 2024-07-28T12:17:02.8186747+02:00, Sample: slide
BIDS info: {'sub': '01', 'ses': '02', 'acq_time': '2024-07-28T12:17:02.8186747+02:00', 'acq_sig': 'Fluorescence-resolution-0.32x0.32', 'sample': None, 'chunk': None, 'bids_root_path': '/envau/work/nit/users/boudlal.h/BIDS-EBrains_test'}
Placeholder: MJO16052401_Cx_296_298.czi

================================================================================
Input CZI: /envau/work/invibe/USERS/IBOS/data/Marmoset/lames/1-renamed/6-Marmot-MJO16052401/originaux/MJO16052401_Cx_296_298.czi
Subject: 01 | Session: 02 | Sample: slide02
SliceIndices: [296, 298] | Channels: (0, 1)
Downsampling: 32 | Patch size: 6144
================================================================================

Output pixel size: X=10.392423922960162 um  Y=10.392423922960162 um

Total bounding rectangle: (-167162, 6108, 144400, 60054)
Mosaic output size: (4512, 1876)

--------------------------------------------------------------------------------
Converting sample=slide02, SliceIndices=[296, 298], stain=C0
--------------------------------------------------------------------------------
slide02 C0 ds32x |████████████████████████████████████████| 240/240 [100%] in 7.0s (33.47/s) 
Written: /envau/work/nit/users/boudlal.h/BIDS-EBrains_test/sub-01/ses-02/micr/sub-01_ses-02_sample-slide02_stain-C0_FLUO.ome.tif
sidecar created: /envau/work/nit/users/boudlal.h/BIDS-EBrains_test/sub-01/ses-02/micr/sub-01_ses-02_sample-slide02_stain-C0_FLUO.json
is_ome: True | is_bigtiff: True | shape: (1876, 4512) | axes: YX

--------------------------------------------------------------------------------
Converting sample=slide02, SliceIndices=[296, 298], stain=C1
--------------------------------------------------------------------------------
slide02 C1 ds32x |████████████████████████████████████████| 240/240 [100%] in 6.5s (35.90/s) 
Written: /envau/work/nit/users/boudlal.h/BIDS-EBrains_test/sub-01/ses-02/micr/sub-01_ses-02_sample-slide02_stain-C1_FLUO.ome.tif
sidecar created: /envau/work/nit/users/boudlal.h/BIDS-EBrains_test/sub-01/ses-02/micr/sub-01_ses-02_sample-slide02_stain-C1_FLUO.json
is_ome: True | is_bigtiff: True | shape: (1876, 4512) | axes: YX

>>> Processing: MIO21100401_Cx_104_112_120_128.czi
    Subject: 02, Date: 2024-05-24T13:22:39.2626295+02:00, Sample: slide
BIDS info: {'sub': '02', 'ses': '01', 'acq_time': '2024-05-24T13:22:39.2626295+02:00', 'acq_sig': 'Fluorescence-resolution-0.32x0.32', 'sample': None, 'chunk': None, 'bids_root_path': '/envau/work/nit/users/boudlal.h/BIDS-EBrains_test'}
Placeholder: MIO21100401_Cx_104_112_120_128.czi

================================================================================
Input CZI: /envau/work/invibe/USERS/IBOS/data/Marmoset/lames/1-renamed/5-Sully-MIO21100401/originaux/MIO21100401_Cx_104_112_120_128.czi
Subject: 02 | Session: 01 | Sample: slide01
SliceIndices: [104, 112, 120, 128] | Channels: (0, 1)
Downsampling: 32 | Patch size: 6144
================================================================================

Output pixel size: X=10.395654616370356 um  Y=10.395654616370356 um

Total bounding rectangle: (-156427, 4590, 121376, 58508)
Mosaic output size: (3793, 1828)

--------------------------------------------------------------------------------
Converting sample=slide01, SliceIndices=[104, 112, 120, 128], stain=C0
--------------------------------------------------------------------------------
slide01 C0 ds32x |████████████████████████████████████████| 200/200 [100%] in 5.0s (40.00/s) 
Written: /envau/work/nit/users/boudlal.h/BIDS-EBrains_test/sub-02/ses-01/micr/sub-02_ses-01_sample-slide01_stain-C0_FLUO.ome.tif
sidecar created: /envau/work/nit/users/boudlal.h/BIDS-EBrains_test/sub-02/ses-01/micr/sub-02_ses-01_sample-slide01_stain-C0_FLUO.json
is_ome: True | is_bigtiff: True | shape: (1828, 3793) | axes: YX

--------------------------------------------------------------------------------
Converting sample=slide01, SliceIndices=[104, 112, 120, 128], stain=C1
--------------------------------------------------------------------------------
slide01 C1 ds32x |████████████████████████████████████████| 200/200 [100%] in 4.6s (43.16/s) 
Written: /envau/work/nit/users/boudlal.h/BIDS-EBrains_test/sub-02/ses-01/micr/sub-02_ses-01_sample-slide01_stain-C1_FLUO.ome.tif
sidecar created: /envau/work/nit/users/boudlal.h/BIDS-EBrains_test/sub-02/ses-01/micr/sub-02_ses-01_sample-slide01_stain-C1_FLUO.json
is_ome: True | is_bigtiff: True | shape: (1828, 3793) | axes: YX

>>> Processing: MIO21100401_Cx_390_394.czi
    Subject: 02, Date: 2024-06-09T02:43:50.3226373+02:00, Sample: slide
BIDS info: {'sub': '02', 'ses': '02', 'acq_time': '2024-06-09T02:43:50.3226373+02:00', 'acq_sig': 'Fluorescence-resolution-0.32x0.32', 'sample': None, 'chunk': None, 'bids_root_path': '/envau/work/nit/users/boudlal.h/BIDS-EBrains_test'}
Placeholder: MIO21100401_Cx_390_394.czi

================================================================================
Input CZI: /envau/work/invibe/USERS/IBOS/data/Marmoset/lames/1-renamed/5-Sully-MIO21100401/originaux/MIO21100401_Cx_390_394.czi
Subject: 02 | Session: 02 | Sample: slide02
SliceIndices: [390, 394] | Channels: (0, 1)
Downsampling: 32 | Patch size: 6144
================================================================================

Output pixel size: X=10.395654616370356 um  Y=10.395654616370356 um

Total bounding rectangle: (-144158, 4593, 104532, 61571)
Mosaic output size: (3266, 1924)

--------------------------------------------------------------------------------
Converting sample=slide02, SliceIndices=[390, 394], stain=C0
--------------------------------------------------------------------------------
slide02 C0 ds32x |████████████████████████████████████████| 198/198 [100%] in 4.1s (47.01/s) 
Written: /envau/work/nit/users/boudlal.h/BIDS-EBrains_test/sub-02/ses-02/micr/sub-02_ses-02_sample-slide02_stain-C0_FLUO.ome.tif
sidecar created: /envau/work/nit/users/boudlal.h/BIDS-EBrains_test/sub-02/ses-02/micr/sub-02_ses-02_sample-slide02_stain-C0_FLUO.json
is_ome: True | is_bigtiff: True | shape: (1924, 3266) | axes: YX

--------------------------------------------------------------------------------
Converting sample=slide02, SliceIndices=[390, 394], stain=C1
--------------------------------------------------------------------------------
slide02 C1 ds32x |████████████████████████████████████████| 198/198 [100%] in 3.9s (49.00/s) 
Written: /envau/work/nit/users/boudlal.h/BIDS-EBrains_test/sub-02/ses-02/micr/sub-02_ses-02_sample-slide02_stain-C1_FLUO.ome.tif
sidecar created: /envau/work/nit/users/boudlal.h/BIDS-EBrains_test/sub-02/ses-02/micr/sub-02_ses-02_sample-slide02_stain-C1_FLUO.json
is_ome: True | is_bigtiff: True | shape: (1924, 3266) | axes: YX
samples.tsv updated

[SUCCESS] Total bounding-box raw OME-TIFF conversion done.
```

