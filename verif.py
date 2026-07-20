import nibabel as nib
import numpy as np

img4 = nib.load("/Users/hananeboudlal/Desktop/sub-Una_ses-01_sample-slide1_chunk-69_stain-C0_res-4x_desc-downsampled_FLUO.nii.gz")
img8 = nib.load("/Users/hananeboudlal/Desktop/sub-Una_ses-01_sample-slide1_chunk-69_stain-C0_res-8x_desc-downsampled_FLUO.nii.gz")

data4 = np.squeeze(np.asanyarray(img4.dataobj))
data8 = np.squeeze(np.asanyarray(img8.dataobj))

print("Shape 4x :", data4.shape)
print("Shape 8x :", data8.shape)

expected8 = data4[::16, ::16]

nx = min(expected8.shape[0], data8.shape[0])
ny = min(expected8.shape[1], data8.shape[1])

expected8 = expected8[:nx, :ny]
actual8 = data8[:nx, :ny]

difference = (
    actual8.astype(np.float64)
    - expected8.astype(np.float64)
)

print("Shape attendue :", expected8.shape)
print("Shape réelle :", actual8.shape)

print(
    "Pixels exactement identiques :",
    np.array_equal(actual8, expected8),
)

print(
    "Différence maximale :",
    np.max(np.abs(difference)),
)

print(
    "Différence moyenne :",
    np.mean(np.abs(difference)),
)

print(
    "Pourcentage de pixels différents :",
    100.0 * np.mean(actual8 != expected8),
)