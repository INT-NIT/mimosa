# -*- coding: utf-8 -*-

"""
Test simple de conversion CZI -> OME-TIFF.

Utilisation :
    python test_czi_to_ome.py chemin/vers/fichier.czi

Exemple :
    python test_czi_to_ome.py 700_onDish_DNA-Bodipy_10x.czi
"""

import os
import sys

import numpy as np
import tifffile
from dateutil import parser

from pylibCZIrw import czi as pyczi

from ome_types import model
from ome_types.model.simple_types import PixelType, UnitsLength

from czitools.utils import misc
from czitools.metadata_tools.channel import CziChannelInfo
from czitools.metadata_tools.dimension import CziDimensions
from czitools.read_tools import read_tools


def pixel_type_to_ome(string):
    """
    Convertit le type pixel Zeiss/CZI vers un type OME.
    """

    if string == "Gray8":
        return PixelType.UINT8.value

    if string == "Gray16":
        return PixelType.UINT16.value

    if string == "Gray32Float":
        return PixelType.FLOAT.value

    raise ValueError(f"Pixel type non supporté : {string}")


def unit_converter(string):
    """
    Convertit une unité texte vers une unité OME.
    """

    if string in ["µm", "um", "micron", "micrometer"]:
        return UnitsLength.MICROMETER.value

    raise ValueError(f"Unité non supportée : {string}")


def pxl_type(pixel_types: dict):
    """
    Déduit le dtype numpy à partir des types pixels du CZI.
    """

    dtype_map = {
        8: np.uint8,
        16: np.uint16,
        32: np.float32,
        64: np.float64,
    }

    biggest = 8

    for value in pixel_types.values():
        value = str(value).lower()

        for bit_depth in [64, 32, 16, 8]:
            if str(bit_depth) in value:
                biggest = max(biggest, bit_depth)
                break

    return dtype_map.get(biggest, np.uint8)


def dict_crawler(
    dictionary: dict,
    search_key: str,
    case_insensitive: bool = False,
    partial_search: bool = False,
) -> list:
    """
    Cherche récursivement une clé dans un dictionnaire.
    Pas indispensable pour le test, mais gardé depuis ton script initial.
    """

    def search(d, key, path):
        if isinstance(d, dict):
            for k, v in d.items():
                new_path = path + [k]

                match = (
                    (case_insensitive and str(k).lower() == key.lower())
                    or (partial_search and key.lower() in str(k).lower())
                    or (k == key)
                )

                if match:
                    yield new_path, v

                if isinstance(v, (dict, list)):
                    yield from search(v, key, new_path)

        elif isinstance(d, list):
            for index, item in enumerate(d):
                new_path = path + [index]
                yield from search(item, key, new_path)

    result = list(search(dictionary, search_key, []))
    return result if result else [([""], "")]


def read_czi(path: str, metadata: dict) -> np.ndarray:
    """
    Lecture simple d'un CZI en tableau numpy.
    Cette fonction n'est pas utilisée dans le main, mais gardée pour test.
    """

    with pyczi.open_czi(path) as czidoc:
        shape = (
            metadata.get("Image Size S", 1),
            metadata.get("Image Size T", 1),
            metadata.get("Image Size Z", 1),
            metadata.get("Image Size C", 1),
            metadata.get("Image Size Y", 1),
            metadata.get("Image Size X", 1),
        )

        img = np.zeros(shape, dtype=pxl_type(czidoc.pixel_types))

        for scene in range(shape[0]):
            for time in range(shape[1]):
                for z in range(shape[2]):
                    for c in range(shape[3]):
                        plane = czidoc.read(
                            plane={"C": c, "Z": z, "T": time},
                            scene=scene,
                        )
                        img[scene, time, z, c, :, :] = np.squeeze(plane)

    return np.squeeze(img)


def get_info_metadata_from_czi(img_path: str, verbose: bool = True) -> dict:
    """
    Extrait des métadonnées importantes depuis un fichier CZI.
    """

    if not os.path.exists(img_path):
        raise FileNotFoundError(f"Fichier introuvable : {img_path}")

    with pyczi.open_czi(img_path) as czidoc:
        metadata = czidoc.metadata["ImageDocument"]["Metadata"]

    app_name = None
    app_version = None
    microscope = None
    acq_type = None
    lens_na = None
    lens_mag = None
    pre_processed = None
    comment = None
    description = None
    date_object = None

    app = metadata.get("Information", {}).get("Application", None)

    if app is None:
        print("Aucune information Application trouvée dans les métadonnées.")
        return None

    app_name = app.get("Name", None)
    app_version = app.get("Version", None)

    if verbose:
        print(f"Metadata made with {app_name} version {app_version}")

    information = metadata.get("Information", {})
    instrument = information.get("Instrument", {})
    microscopes = instrument.get("Microscopes", {})
    microscope_block = microscopes.get("Microscope", {})

    if isinstance(microscope_block, list):
        microscope_block = microscope_block[0] if microscope_block else {}

    if app_name and "ZEN" in app_name and app_version and app_version.startswith("3."):
        microscope = microscope_block.get("UserDefinedName", None)
        if microscope is None:
            microscope = microscope_block.get("@Name", None)
        if microscope is None:
            microscope = metadata.get("Scaling", {}).get("AutoScaling", {}).get("CameraName", None)

    elif app_name and "ZEN" in app_name and app_version and app_version.startswith("2.6"):
        microscope = microscope_block.get("@Name", None)

    elif app_name and "AIM" in app_name:
        microscope = microscope_block.get("System", None)

    if verbose:
        print(f"Image made on {microscope}")

    # Pixel size : valeurs converties en microns
    physical_pixel_sizes = {}

    distances = (
        metadata.get("Scaling", {})
        .get("Items", {})
        .get("Distance", [])
    )

    if isinstance(distances, dict):
        distances = [distances]

    for dim in distances:
        axis = dim.get("@Id")
        value = dim.get("Value")

        if axis is not None and value is not None:
            physical_pixel_sizes[axis] = round(float(value) * 1e6, 4)

    # Dimensions
    image_info = information.get("Image", {})
    size = {}

    for d, value in image_info.items():
        if "Size" in d:
            try:
                size[d] = int(value)
            except Exception:
                pass

    if verbose:
        print(f"Image with dimension {size} and pixel size of {physical_pixel_sizes}")

    # Acquisition type
    try:
        channels = image_info["Dimensions"]["Channels"]["Channel"]

        if isinstance(channels, list):
            first_channel = channels[0]
            acq_type = first_channel.get(
                "ChannelType",
                first_channel.get("AcquisitionMode", None),
            )

            if acq_type == "Unspecified":
                acq_type = first_channel.get("AcquisitionMode", None)

        elif isinstance(channels, dict):
            acq_type = channels.get("AcquisitionMode", None)

    except Exception:
        acq_type = None

    if verbose:
        print(f"Image acquired with a {acq_type} mode")

    # Objectif
    objective = instrument.get("Objectives", {}).get("Objective", {})

    if isinstance(objective, list):
        objective = objective[0] if objective else {}

    lens_na = objective.get("LensNA", None)
    if lens_na is not None:
        lens_na = round(float(lens_na), 2)

    lens_mag = objective.get("NominalMagnification", None)
    if lens_mag is not None:
        lens_mag = int(float(lens_mag))

    if verbose:
        print(f"Objective lens used has a magnification of {lens_mag} and a NA of {lens_na}")

    # Processing
    processing = information.get("Processing", None)
    if processing is not None:
        pre_processed = list(processing.keys())

    if verbose:
        print(f"Image preprocessed with {pre_processed}")

    # Infos document
    document = information.get("Document", {})

    comment = document.get("Comment", None)
    description = document.get("Description", None)

    creation_date = document.get("CreationDate", None)

    if creation_date is not None:
        date_object = parser.parse(creation_date)

    if verbose:
        print(
            "Image\n"
            f"    Comment: {comment},\n"
            f"    Description: {description},\n"
            f"    Creation date: {date_object}"
        )

    if verbose:
        print("_" * 25)

    mini_metadata = {
        "Microscope": microscope,
        "Lens Magnification": lens_mag,
        "Lens NA": lens_na,
        "Image type": acq_type,
        "Comment": comment,
        "Description": description,
        "Acquisition date": date_object.strftime("%Y-%m-%d %H:%M:%S")
        if date_object is not None
        else None,
    }

    # Ajout pixel size
    for axis, value in physical_pixel_sizes.items():
        mini_metadata[f"Physical pixel size {axis}"] = value

    # Ajout dimensions
    for axis, value in size.items():
        # Exemple : SizeX -> X
        mini_metadata[f"Image Size {axis[-1]}"] = value

    return mini_metadata


def ome_extraction_mini(filepath: str, mini_metadata: dict) -> str:
    """
    Construit un XML OME minimal à partir du CZI et de ses métadonnées.
    """

    czi_dimensions = CziDimensions(filepath)

    print("SizeS:", czi_dimensions.SizeS)

    if czi_dimensions.SizeS is not None and czi_dimensions.SizeS > 1:
        print("Fichier multi-scènes détecté. Ce script de test ne gère pas encore SizeS > 1.")
        return ""

    with pyczi.open_czi(filepath) as czidoc:
        pixel_types = list(czidoc.pixel_types.values())

    if not pixel_types:
        raise ValueError("Impossible de récupérer le pixel type depuis le CZI.")

    # Planetable : juste pour debug
    try:
        planetable = misc.get_planetable(
            filepath,
            norm_time=True,
            pt_complete=True,
        )
    except Exception as exc:
        print("Planetable non récupérée :", exc)
        planetable = None

    print("Planetable:")
    print(planetable)

    # Création OME
    ome = model.OME()

    # Objectif
    obj_na = mini_metadata.get("Lens NA", None)
    obj_mag = mini_metadata.get("Lens Magnification", None)

    ome_objective = model.Objective(id="Objective:0")

    if obj_na is not None:
        ome_objective.lens_na = float(obj_na)

    if obj_mag is not None:
        ome_objective.nominal_magnification = float(obj_mag)

    ome.instruments = [
        model.Instrument(
            id="Instrument:0",
            objectives=[ome_objective],
        )
    ]

    # Channels
    czi_channels = CziChannelInfo(filepath)

    ome_channels = []

    dyes = czi_channels.dyes if czi_channels.dyes is not None else []
    colors = czi_channels.colors if czi_channels.colors is not None else []

    size_c = mini_metadata.get("Image Size C", 1)

    for ch_idx in range(size_c):
        fluor = dyes[ch_idx] if ch_idx < len(dyes) else None
        color = colors[ch_idx] if ch_idx < len(colors) else None

        ome_channel = model.Channel(
            id=f"Channel:{ch_idx}",
            samples_per_pixel=1,
            fluor=fluor,
            color=color,
        )

        ome_channels.append(ome_channel)

    # Valeurs par défaut si absent
    size_x = mini_metadata.get("Image Size X", 1)
    size_y = mini_metadata.get("Image Size Y", 1)
    size_z = mini_metadata.get("Image Size Z", 1)
    size_t = mini_metadata.get("Image Size T", 1)
    size_c = mini_metadata.get("Image Size C", 1)

    physical_size_x = mini_metadata.get("Physical pixel size X", None)
    physical_size_y = mini_metadata.get("Physical pixel size Y", None)
    physical_size_z = mini_metadata.get("Physical pixel size Z", None)

    pixels_kwargs = {
        "id": "Pixels:0",
        "dimension_order": model.Pixels_DimensionOrder.XYCZT,
        "big_endian": False,
        "interleaved": False,
        "type": pixel_type_to_ome(pixel_types[0]),
        "size_x": size_x,
        "size_y": size_y,
        "size_c": size_c,
        "size_z": size_z,
        "size_t": size_t,
        "channels": ome_channels,
    }

    if physical_size_x is not None:
        pixels_kwargs["physical_size_x"] = physical_size_x
        pixels_kwargs["physical_size_x_unit"] = unit_converter("µm")

    if physical_size_y is not None:
        pixels_kwargs["physical_size_y"] = physical_size_y
        pixels_kwargs["physical_size_y_unit"] = unit_converter("µm")

    if physical_size_z is not None and size_z > 1:
        pixels_kwargs["physical_size_z"] = physical_size_z
        pixels_kwargs["physical_size_z_unit"] = unit_converter("µm")

    pixels = model.Pixels(**pixels_kwargs)

    # Date
    acquisition_date_str = mini_metadata.get("Acquisition date", None)

    if acquisition_date_str is not None:
        acquisition_date = parser.parse(acquisition_date_str)
    else:
        acquisition_date = None

    image_kwargs = {
        "id": "Image:0",
        "name": os.path.basename(filepath),
        "pixels": pixels,
    }

    if acquisition_date is not None:
        image_kwargs["acquisition_date"] = acquisition_date

    image = model.Image(**image_kwargs)

    ome.images.append(image)

    # XML
    ome_xml = ome.to_xml()

    assert ome_xml.lstrip().startswith("<OME")

    ome_xml = ome_xml.encode("ascii", "xmlcharrefreplace").decode("ascii")

    for c in ome_xml:
        if ord(c) > 127:
            raise ValueError(f"Non-ASCII: {repr(c)} (U+{ord(c):04X})")

    print("_" * 20)
    print("OME XML generated successfully.")
    print("_" * 20)

    return ome_xml


def read_czi_as_tczyx(filepath: str):
    """
    Lit le CZI avec czitools et essaie de récupérer un tableau compatible OME-TIFF.

    Le script initial faisait :
        array = array[0]
        array = array.transpose('T', 'Z', 'C', 'Y', 'X')

    Ici, on garde cette logique mais on affiche la forme pour debug.
    """

    array, metadata = read_tools.read_6darray(filepath)

    print("Array returned by read_6darray:")
    print(array)

    try:
        print("Array dims:", array.dims)
    except Exception:
        pass

    print("Array shape:", array.shape)

    # Cas fréquent : dimensions du type S, T, Z, C, Y, X
    # On prend S=0 si une seule scène.
    try:
        if "S" in array.dims:
            array = array.isel(S=0)

        array = array.transpose("T", "Z", "C", "Y", "X")

        data = array.data

    except Exception as exc:
        print("Transpose avec dimensions nommées impossible :", exc)
        print("Fallback numpy simple.")

        data = np.asarray(array)

        # Fallback pour shape classique : S,T,Z,C,Y,X
        if data.ndim == 6:
            data = data[0]

        if data.ndim != 5:
            raise ValueError(
                f"Shape non supportée pour OME-TIFF. Shape obtenue : {data.shape}. "
                "Il faut adapter read_czi_as_tczyx()."
            )

    print("Final data shape for TIFF:", data.shape)

    return data


def validate_ome_tiff(output_name: str):
    """
    Vérifie rapidement que le TIFF contient bien une description OME.
    """

    from tifffile import TiffFile

    with TiffFile(output_name) as tf:
        print("\nValidation:")
        print("is_ome:", tf.is_ome)
        print(
            "desc starts with <OME>:",
            tf.pages[0].description.lstrip().startswith("<OME"),
        )
        print("ome len:", len(tf.ome_metadata) if tf.ome_metadata else None)
        print("n_pages:", len(tf.pages))


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("    python test_czi_to_ome.py fichier.czi")
        sys.exit(1)

    filename = sys.argv[1]

    if not os.path.exists(filename):
        print(f"Fichier introuvable : {filename}")
        sys.exit(1)

    output_name = os.path.splitext(os.path.basename(filename))[0] + ".ome.tiff"

    print("=" * 60)
    print("Testing CZI file:")
    print(filename)
    print("=" * 60)

    metadata = get_info_metadata_from_czi(filename, verbose=True)

    if metadata is None:
        print("Aucune métadonnée extraite.")
        sys.exit(1)

    print("\nExtracted mini metadata:")
    for key, value in metadata.items():
        print(f"{key}: {value}")

    print("\nGenerating OME XML...")
    ome_xml = ome_extraction_mini(filename, metadata)

    if not ome_xml:
        print("OME XML non généré.")
        sys.exit(1)

    print("\nReading CZI image data...")
    data = read_czi_as_tczyx(filename)

    print("\nWriting OME-TIFF...")
    tifffile.imwrite(
        output_name,
        data,
        bigtiff=True,
        compression="zlib",
        metadata=None,
        description=ome_xml,
        ome=False,
        imagej=False,
    )

    print(f"\nWritten: {output_name}")

    validate_ome_tiff(output_name)

    print("\nDone.")


if __name__ == "__main__":
    main()