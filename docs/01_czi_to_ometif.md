# CZI → OME-TIF (whole-slide overview)

Stitches all the scenes of a `.czi` slide into a single whole-slide OME-TIF,
written to `sub-<subject>/ses-<session>/micr/`. This image is a global overview
that gives an idea of the whole scanned slide. It is the raw image of the
dataset, with its JSON sidecar.

## Command

```bash
python 2D/conversion/mimosa_czi2ometiff_converter.py \
  -y metadata.yml \
  -bids_root /path/to/BIDS \
  -df 8 \
  -channels 0,1
```

## Options

| Option | What it does | Default |
|--------|--------------|---------|
| `-y` | metadata YAML. **Required.** | — |
| `-bids_root` | Output BIDS root. **Required.** | — |
| `-df` | Downsampling **factor**, one of `1, 2, 4, 6, 8`. | `8` |
| `-channels` | Channels to convert, e.g. `0` or `0,1`. | `0,1` |
| `-patch_size` | Patch size (px) used to read the CZI. | `6144` |

## Understanding the options

- **`-df` (downsampling factor, not an exponent).** Here the number *is* the
  factor: `-df 8` means factor 8. This differs from the NIfTI converter, where
  `-df 8` means factor 256 (there the number is an exponent).

- **`-channels`.** A CZI can hold several fluorescence channels. Give the ones
  you want, comma-separated. Each channel produces its own OME-TIF.

- **`-patch_size`.** The whole slide is too big to read at once, so it is read
  in square patches of this size, directly at the reduced resolution.

## Output

For each channel, one OME-TIF and its JSON sidecar:

```text
sub-<subject>/ses-<session>/micr/
  sub-<subject>_ses-<session>_sample-slide01_stain-C0_FLUO.ome.tif
  sub-<subject>_ses-<session>_sample-slide01_stain-C0_FLUO.json
```

The extension is `.ome.tif` (BIDS microscopy does not allow `.ome.tiff`). The
JSON sidecar carries `PixelSize` / `PixelSizeUnits`, required by the BIDS
microscopy validator, kept consistent with the OME `PhysicalSize` written in
the image itself.