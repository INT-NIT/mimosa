Create dataset folder
```bash
mkdir BIDS-EBrains_test
```

```bash
python 2D/conversion/mimosa_czi2ometif_converter.py  -y  ../metadata_ebrain.yml -bids_root ../BIDS-EBrains_test/ -df 3  -channels 0,1
```


output:
```bash
Downsampling exponent: 3 -> factor 8
dataset_description.json created
participants.json created
participants.tsv created
============================================================
BIDS dataset initialized: /envau/work/nit/users/boudlal.h/BIDS-EBrains_test
============================================================
MIMOSA - reading slices from metadata.yml
============================================================
  sub-01        119 files  (from YAML)
  sub-02        116 files  (from YAML)
WARNING: no slices for: MJO16052401_Cx_512_514x.czi

>>> Processing: MJO16052401_Cx_36_38_40_42_44_46_48_50_52.czi
    Subject: 01, Date: 2024-07-26T18:18:25.7716027+02:00, Sample: slide
BIDS info: {'sub': '01', 'ses': '01', 'acq_time': '2024-07-26T18:18:25.7716027+02:00', 'acq_sig': 'Fluorescence-resolution-0.32x0.32', 'sample': None, 'chunk': None, 'bids_root_path': '/envau/work/nit/users/boudlal.h/BIDS-EBrains_test'}
Placeholder: MJO16052401_Cx_36_38_40_42_44_46_48_50_52.czi

================================================================================
Input CZI: /envau/work/invibe/USERS/IBOS/data/Marmoset/lames/1-renamed/6-Marmot-MJO16052401/originaux/MJO16052401_Cx_36_38_40_42_44_46_48_50_52.czi
Subject: 01 | Session: 01 | Sample: slide01
SliceIndices: [36, 38, 40, 42, 44, 46, 48, 50, 52] | Channels: (0, 1)
Downsampling: 8 | Patch size: 6144
================================================================================

Output pixel size: X=2.5981059807400406 um  Y=2.5981059807400406 um

Total bounding rectangle: (-168700, 3061, 133622, 63109)
Mosaic output size: (16702, 7888)

--------------------------------------------------------------------------------
Converting sample=slide01, SliceIndices=[36, 38, 40, 42, 44, 46, 48, 50, 52], stain=C0
--------------------------------------------------------------------------------
slide01 C0 ds8x |████████████████████████████████████████| 242/242 [100%] in 15.8s (15.22/s) 
Written: /envau/work/nit/users/boudlal.h/BIDS-EBrains_test/sub-01/ses-01/micr/sub-01_ses-01_sample-slide01_stain-C0_FLUO.ome.tif
sidecar created: /envau/work/nit/users/boudlal.h/BIDS-EBrains_test/sub-01/ses-01/micr/sub-01_ses-01_sample-slide01_stain-C0_FLUO.json
is_ome: True | is_bigtiff: True | shape: (7888, 16702) | axes: YX

--------------------------------------------------------------------------------
Converting sample=slide01, SliceIndices=[36, 38, 40, 42, 44, 46, 48, 50, 52], stain=C1
--------------------------------------------------------------------------------
slide01 C1 ds8x |████████████████████████████████████████| 242/242 [100%] in 14.1s (17.06/s) 
Written: /envau/work/nit/users/boudlal.h/BIDS-EBrains_test/sub-01/ses-01/micr/sub-01_ses-01_sample-slide01_stain-C1_FLUO.ome.tif
sidecar created: /envau/work/nit/users/boudlal.h/BIDS-EBrains_test/sub-01/ses-01/micr/sub-01_ses-01_sample-slide01_stain-C1_FLUO.json
is_ome: True | is_bigtiff: True | shape: (7888, 16702) | axes: YX
```
