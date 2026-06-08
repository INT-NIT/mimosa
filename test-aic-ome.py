#!/usr/bin/env python3
"""
Convert CZI to OME-TIFF using aicsimageio + aicspylibczi.
Writes OME-XML metadata automatically.

Usage:
    python convert_czi_to_ometiff.py input.czi
    python convert_czi_to_ometiff.py input.czi output.ome.tiff
"""

import sys
from pathlib import Path


def convert_czi_to_ome_tiff(input_czi: str, output_ome_tiff: str | None = None) -> Path:
    from aicsimageio import AICSImage
    from aicsimageio.writers import OmeTiffWriter

    input_path = Path(input_czi)
    if not input_path.exists():
        raise FileNotFoundError(f"File not found: {input_path}")

    output_path = Path(output_ome_tiff) if output_ome_tiff else input_path.with_suffix(".ome.tiff")

    print(f"Reading: {input_path.name}")
    img = AICSImage(str(input_path))

    print(f"Shape:    {img.shape}")
    print(f"Dims:     {img.dims}")
    print(f"Physical pixel sizes: {img.physical_pixel_sizes}")

    data = img.get_image_data("TCZYX")

    print(f"Writing OME-TIFF: {output_path}")

    OmeTiffWriter.save(
        data=[data],
        uri=str(output_path),
        dim_order=["TCZYX"],
        channel_names=[img.channel_names] if img.channel_names else None,
        physical_pixel_sizes=[img.physical_pixel_sizes],
    )

    print(f"Done: {output_path}")
    return output_path


def validate_ome_tiff(path: str):
    import tifffile

    with tifffile.TiffFile(str(path)) as tf:
        print("\n--- Validation OME-TIFF ---")
        print(f"is_ome:       {tf.is_ome}")
        print(f"Pages:        {len(tf.pages)}")
        if tf.ome_metadata:
            print(f"OME-XML len:  {len(tf.ome_metadata)}")
            print("\nOME-XML preview (first 1000 chars):")
            print(tf.ome_metadata[:1000])
        else:
            print("No OME metadata found.")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python convert_czi_to_ometiff.py input.czi")
        print("  python convert_czi_to_ometiff.py input.czi output.ome.tiff")
        sys.exit(1)

    input_czi = sys.argv[1]
    output_ome_tiff = sys.argv[2] if len(sys.argv) >= 3 else None

    output_path = convert_czi_to_ome_tiff(input_czi, output_ome_tiff)

    try:
        validate_ome_tiff(str(output_path))
    except ImportError:
        print("\ntifffile not installed — skipping validation.")
        print("Install with: pip install tifffile")


if __name__ == "__main__":
    main()