# Geometry: coordinate system and affine matrices

This page gathers all the geometry of the pipeline in one place: the slice
vocabulary, the physical-depth formula, and how the affine (SForm) matrix is
built at each step. The usage pages link here instead of repeating the math.

## Slice vocabulary and depth

- **SliceIndex** — the raw number that identifies a histological section (the
  chunk number read from the CZI filename or declared in the YAML). It is
  arbitrary and not necessarily contiguous.
- **SlicePosition** — the rank of that section in the complete, ordered brain
  stack (`0, 1, 2, ...`). This is what places the slice in depth.
- **NumberOfSlices** — the total number of positions in the **complete** brain.

The physical depth of a slice uses the centered stack coordinate:

```text
physical_z = (slice_position - (number_of_slices - 1) / 2) * slice_spacing
```

with `slice_spacing = original_thickness_um / 1000` (mm). This places the whole
stack around physical coordinate zero. Example with `number_of_slices = 4` and
`slice_spacing = 0.1 mm`:

```text
slice_position = 0 -> Z = -0.15 mm
slice_position = 1 -> Z = -0.05 mm
slice_position = 2 -> Z =  0.05 mm
slice_position = 3 -> Z =  0.15 mm
```

The geometric center is at `Z = 0`. With an even number of slices, zero lies
between the two central slices.

### Why NumberOfSlices must be the complete brain

Because the depth depends on `number_of_slices`, this total must always be the
one of the **complete** brain. If the complete brain has 200 sections and you
export only 10, those 10 must still be positioned with `number_of_slices = 200`,
not `10`, otherwise their depth is wrong.

This is why the slice positions are always computed from the **complete** slice
list declared in the YAML, and why you export a subset with `-only_slices`
(which keeps the full total) rather than by deleting slices from the YAML.

## 2D slice affine matrix

Each downsampled NIfTI slice receives a 4 x 4 affine matrix:

```text
[ pixel_spacing_x       0                  0              origin_x ]
[       0         pixel_spacing_y          0              origin_y ]
[       0               0            slice_spacing        origin_z ]
[       0               0                  0                  1     ]
```

### X and Y spacing

```text
pixel_spacing_x = exported_pixel_size_x_um / 1000
pixel_spacing_y = exported_pixel_size_y_um / 1000
```

(the division by 1000 converts micrometres to millimetres).

### X and Y origin

The X/Y origin centres the image on its **exported (downsampled) pixel grid**,
using the real (integer) pixel count of the downsampled image:

```text
origin_x = -(exported_width_px  - 1) / 2 * pixel_spacing_x
origin_y = -(exported_height_px - 1) / 2 * pixel_spacing_y
```

Because the exported slices are forced to an **odd** size, a real pixel centre
lands exactly on 0 for every slice and every resolution. All slices — and all
resolutions — therefore share the same origin and overlay exactly, with no
per-slice sub-pixel drift (which native-grid centring would leave, because
`native / factor` is not an integer).

### Z position

```text
origin_z = (slice_position - (number_of_slices - 1) / 2) * slice_spacing
```

(see the depth formula above).

## Padding and the affine matrix

Padding adds zero-valued pixels around the image. The tissue must stay at the
same physical coordinates, so the origin is shifted by the pixels added before
the image:

```text
padded_origin_x = origin_x - padding_before_x * pixel_spacing_x
padded_origin_y = origin_y - padding_before_y * pixel_spacing_y
padded_origin_z = origin_z
```

In vector form:

```text
padded_origin = origin
              - padding_before_x * x_axis_vector
              - padding_before_y * y_axis_vector
```

where `x_axis_vector` and `y_axis_vector` are the first and second columns of
the affine. The Z origin does not change (padding is only in the image plane).
Because slices are exported odd and the target shape is also forced odd, the
symmetric padding is exact (no rounding), so raw, padded and volume all overlay,
and the different resolutions align with each other.

## 3D volume affine matrix

The volume matrix is built from the matrix of one padded slice used as a
reference (the available slice with the smallest chunk, i.e. the smallest
`SliceIndex`).

**Step 1 - start from the reference slice matrix.** It already holds the X/Y
spacing, the X/Y origin after padding, the stack spacing and the physical
position of that slice.

**Step 2 - move the origin to volume position 0.** The volume matrix must
describe `volume[:, :, 0]`, so the origin is moved backward by the reference
slice position:

```text
volume_origin = reference_slice_origin
              - reference_slice_position * stack_axis_vector
```

Along Z:

```text
volume_z_origin = reference_slice_z - reference_slice_position * slice_spacing
```

**Step 3 - why it is centered and independent of the reference.** The reference
slice already has the centered position
`reference_slice_z = (reference_slice_position - (number_of_slices - 1)/2) * slice_spacing`.
Substituting, the `reference_slice_position` terms cancel:

```text
volume_z_origin = -((number_of_slices - 1) / 2) * slice_spacing
```

So the volume always starts at stack position 0, whatever slice was the
reference.

**Step 4 - geometric center.** Plugging the center index
`(number_of_slices - 1) / 2` gives `center_z = 0`: the volume is centered on
zero along the stack axis.

## Reorientation of the 3D volume

`-reorient` applies the same axis operation to the voxel array **and** the
matrix. An axis permutation permutes the corresponding affine columns; a flip
changes the sign of that column and moves the origin to the old last voxel:

```text
new_volume_origin = old_volume_origin + old_axis_vector * (axis_size - 1)
```

This preserves the physical position of every voxel, using only permutations and
flips (no resampling). The result is written to both the SForm and the QForm.

> Note: at the 2D conversion step, `-reorient` rewrites only the SForm matrix,
> not the pixels. The actual voxel-array reorientation happens here, at stacking.
