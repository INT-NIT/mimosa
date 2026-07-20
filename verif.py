import nibabel as nib
import numpy as np


PATH_FINE = (
    "/Users/hananeboudlal/Desktop/sub-Una_ses-01_sample-slide1_chunk-67_stain-C0_res-6x_desc-downsampled_FLUO.nii.gz"
)

PATH_COARSE = (
    "/Users/hananeboudlal/Desktop/sub-Una_ses-01_sample-slide1_chunk-67_stain-C0_res-8x_desc-downsampled_FLUO.nii.gz"
)

FINE_EXPONENT = 6
COARSE_EXPONENT = 8


def load_2d_nifti(path):
    image = nib.load(path)
    data = np.squeeze(np.asanyarray(image.dataobj))

    if data.ndim != 2:
        raise ValueError(
            f"L'image {path} n'est pas 2D après squeeze : "
            f"shape={data.shape}"
        )

    return image, data


def voxel_sizes_from_affine(affine):
    return np.linalg.norm(affine[:3, :3], axis=0)


def main():
    if COARSE_EXPONENT <= FINE_EXPONENT:
        raise ValueError(
            "COARSE_EXPONENT doit être supérieur à FINE_EXPONENT."
        )

    relative_factor = 2 ** (
        COARSE_EXPONENT - FINE_EXPONENT
    )

    fine_img, fine_data = load_2d_nifti(PATH_FINE)
    coarse_img, coarse_data = load_2d_nifti(PATH_COARSE)

    print("\n========== INFORMATIONS ==========")
    print(f"Image fine : df{FINE_EXPONENT}")
    print(f"Image grossière : df{COARSE_EXPONENT}")
    print(f"Facteur relatif attendu : {relative_factor}")

    print("\nShape fine :", fine_data.shape)
    print("Shape grossière :", coarse_data.shape)

    expected_coarse = fine_data[
        ::relative_factor,
        ::relative_factor,
    ]

    print("Shape grossière attendue :", expected_coarse.shape)
    print(
        "Shapes exactement identiques :",
        expected_coarse.shape == coarse_data.shape,
    )

    common_x = min(
        expected_coarse.shape[0],
        coarse_data.shape[0],
    )
    common_y = min(
        expected_coarse.shape[1],
        coarse_data.shape[1],
    )

    expected_common = expected_coarse[:common_x, :common_y]
    actual_common = coarse_data[:common_x, :common_y]

    difference = (
        actual_common.astype(np.float64)
        - expected_common.astype(np.float64)
    )

    absolute_difference = np.abs(difference)
    different_mask = actual_common != expected_common

    print("\n========== COMPARAISON DES PIXELS ==========")
    print(
        "Pixels exactement identiques :",
        np.array_equal(actual_common, expected_common),
    )
    print(
        "Différence maximale :",
        float(np.max(absolute_difference)),
    )
    print(
        "Différence moyenne :",
        float(np.mean(absolute_difference)),
    )
    print(
        "Différence médiane :",
        float(np.median(absolute_difference)),
    )
    print(
        "Pourcentage de pixels différents :",
        float(100.0 * np.mean(different_mask)),
    )

    fine_affine = fine_img.affine
    coarse_affine = coarse_img.affine

    fine_origin = fine_affine[:3, 3]
    coarse_origin = coarse_affine[:3, 3]

    fine_spacing = voxel_sizes_from_affine(fine_affine)
    coarse_spacing = voxel_sizes_from_affine(coarse_affine)

    spacing_ratio = np.divide(
        coarse_spacing,
        fine_spacing,
        out=np.full_like(coarse_spacing, np.nan),
        where=fine_spacing != 0,
    )

    print("\n========== COMPARAISON GÉOMÉTRIQUE ==========")
    print("Origine fine :", fine_origin)
    print("Origine grossière :", coarse_origin)
    print(
        "Origines identiques :",
        np.allclose(
            fine_origin,
            coarse_origin,
            atol=1e-6,
        ),
    )

    print("Spacing fin :", fine_spacing)
    print("Spacing grossier :", coarse_spacing)
    print("Rapport des spacings :", spacing_ratio)
    print("Rapport XY attendu :", relative_factor)
    print(
        "Rapport XY correct :",
        np.allclose(
            spacing_ratio[:2],
            relative_factor,
            rtol=1e-5,
            atol=1e-6,
        ),
    )

    print("\nAffine fine :")
    print(fine_affine)

    print("\nAffine grossière :")
    print(coarse_affine)

    print("\n========== CONCLUSION ==========")

    same_pixels = np.array_equal(
        actual_common,
        expected_common,
    )
    same_shapes = expected_coarse.shape == coarse_data.shape
    same_origins = np.allclose(
        fine_origin,
        coarse_origin,
        atol=1e-6,
    )
    correct_spacing = np.allclose(
        spacing_ratio[:2],
        relative_factor,
        rtol=1e-5,
        atol=1e-6,
    )

    if same_pixels and same_shapes:
        print(
            "OK : l'image grossière est une décimation exacte "
            "de l'image fine."
        )
        print(
            "Il n'y a aucune interpolation supplémentaire "
            "entre ces deux résolutions."
        )
    elif same_pixels:
        print(
            "Les pixels communs sont identiques, mais les shapes "
            "ne correspondent pas exactement."
        )
        print(
            "Il faut vérifier la règle d'arrondi utilisée pour "
            "la taille de sortie."
        )
    else:
        print(
            "Les pixels ne sont pas identiques : les deux images "
            "ne sont pas une décimation exacte l'une de l'autre."
        )

    if not same_origins:
        print(
            "ATTENTION : les origines physiques sont différentes."
        )

    if not correct_spacing:
        print(
            "ATTENTION : le rapport des résolutions physiques "
            "ne correspond pas au facteur attendu."
        )


if __name__ == "__main__":
    main()