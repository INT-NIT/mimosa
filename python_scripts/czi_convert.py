import os
from pylibCZIrw import czi as pyczi
import json
from matplotlib import pyplot as plt
import matplotlib.cm as cm
import numpy as np
from PIL import Image
import nibabel as nib
from skimage import img_as_ubyte

from alive_progress import alive_bar

#This function returns the largest multiple of the number a smaller than b
def multiple(a, b):
    m = 0
    n = a + 1
    while n < b:
        if n % a == 0:
            m = n
        n = n + 1

    return m

def czi2bitmap(pathin, czifilename, pathout, patch_factor, downsampling_factor, full_patch_w_h,ouput_format):
    czifile_scenes = os.path.join(pathin, czifilename)

    with pyczi.open_czi(czifile_scenes) as czidoc:
        scenes_bounding_rectangle = czidoc.scenes_bounding_rectangle

        for i in range(0, len(scenes_bounding_rectangle)):

            #with alive_bar(len(scenes_bounding_rectangle),force_tty=True) as bar:
            print("ROI Scene",i)

            downsampled_patch_w_h = int(full_patch_w_h / downsampling_factor)

            print(i, scenes_bounding_rectangle[i])

            nb_patch_w = int((scenes_bounding_rectangle[i].w) / (full_patch_w_h * patch_factor))
            nb_patch_h = int((scenes_bounding_rectangle[i].h) / (full_patch_w_h * patch_factor))
            mosaic_image_width = round(float(scenes_bounding_rectangle[i].w) / (downsampling_factor) + 0.5)
            mosaic_image_height = round(float(scenes_bounding_rectangle[i].h) / (downsampling_factor) + 0.5)

            mosaic_image_C0 = np.zeros((int(mosaic_image_height), int(mosaic_image_width)), dtype='uint16')
            mosaic_image_C1 = np.zeros((int(mosaic_image_height), int(mosaic_image_width)), dtype='uint16')
            mosaic_image_patch_size_w = int(downsampled_patch_w_h * patch_factor)
            mosaic_image_patch_size_h = int(downsampled_patch_w_h * patch_factor)

            with alive_bar((nb_patch_w+1)*(nb_patch_h+1),force_tty=True) as bar:

                for x in range(0, nb_patch_w + 1):
                    for y in range(0, nb_patch_h + 1):

                        mosaic_image_patch_size_h_res = mosaic_image_patch_size_h
                        mosaic_image_patch_size_w_res = mosaic_image_patch_size_w
                        patch_width = patch_factor * full_patch_w_h
                        patch_height = patch_factor * full_patch_w_h

                        if (y == nb_patch_h):
                            patch_height = scenes_bounding_rectangle[i].h - (patch_factor * full_patch_w_h * y)
                        if (x == nb_patch_w):
                            patch_width = scenes_bounding_rectangle[i].w - (patch_factor * full_patch_w_h * x)

                        if ((y == nb_patch_h and x == nb_patch_w)):
                            print(f'last corner size={patch_width}/{patch_height} - patch={downsampled_patch_w_h}')

                            #to overcome the bug in the czidoc.read function, find the largest multiple of 8,
                            # less than the largest value between the width and height of the last upper corner patch."
                            max_value=max(patch_width,patch_height)
                            max_mul8_value=multiple(8,max_value)

                            if (max_value==patch_width):patch_width=max_mul8_value
                            else:patch_height = max_mul8_value

                        my_roi_patched = (scenes_bounding_rectangle[i].x + patch_factor * full_patch_w_h * x,
                                          scenes_bounding_rectangle[i].y + patch_factor * full_patch_w_h * y,
                                          patch_width, patch_height)

                        # mosaic Chanel 0 (Anatomical image)
                        ch0 = czidoc.read(roi=my_roi_patched, plane={'C': 0})
                        ch0_res = ch0[::downsampling_factor, ::downsampling_factor]
                        mosaic_image_C0[
                        y * mosaic_image_patch_size_h:y * mosaic_image_patch_size_h + ch0_res[..., 0].shape[0],
                        x * mosaic_image_patch_size_w:x * mosaic_image_patch_size_w + ch0_res[..., 0].shape[1]] = ch0_res[..., 0]

                        # mosaic Chanel 1 (Fluorescence image)
                        ch1 = czidoc.read(roi=my_roi_patched, plane={'C': 1})
                        ch1_res = ch1[::downsampling_factor, ::downsampling_factor]
                        mosaic_image_C1[
                        y * mosaic_image_patch_size_h:y * mosaic_image_patch_size_h + ch1_res[..., 0].shape[0],
                        x * mosaic_image_patch_size_w:x * mosaic_image_patch_size_w + ch1_res[..., 0].shape[1]] = ch1_res[..., 0]

                        bar()

                cziname = os.path.splitext(czifilename)[0]

                if (ouput_format=="tiff"):
                    filename = pathout + "/" + cziname + "_ds" + str(downsampling_factor) + "_S" + str(i).zfill(2) + "_C0.tiff"
                    imC0 = Image.fromarray((mosaic_image_C0).astype(np.uint16))
                    imC0.save(filename)
                    filename = pathout + "/" + cziname + "_ds" + str(downsampling_factor) + "_S" + str(i).zfill(2) + "_C1.tiff"
                    imC1 = Image.fromarray((mosaic_image_C1).astype(np.uint16))
                    imC1.save(filename)

                if (ouput_format == "nii"):
                    #for nii, we need to swap x,y axis (X -> L/R and y-> S/I or A/P)  do check
                    filename = pathout + "/" + cziname + "_ds" + str(downsampling_factor) + "_S" + str(i).zfill(2) + "_C0.nii.gz"
                    array_img = nib.Nifti1Image(np.swapaxes(mosaic_image_C0, 0, 1), np.eye(4))
                    nib.save(array_img, filename)
                    filename = pathout + "/" + cziname + "_ds" + str(downsampling_factor) + "_S" + str(i).zfill(2) + "_C1.nii.gz"
                    array_img = nib.Nifti1Image(np.swapaxes(mosaic_image_C1, 0, 1), np.eye(4))
                    nib.save(array_img, filename)


def czi2bitmapHPC(pathin, czifilename, pathout, downsampling_factor,ouput_format):
    czifile_scenes = os.path.join(pathin, czifilename)

    with pyczi.open_czi(czifile_scenes) as czidoc:
        scenes_bounding_rectangle = czidoc.scenes_bounding_rectangle

        for i in range(0, len(scenes_bounding_rectangle)):

            print("ROI Scene",i)

            zoom_factor = float (1.0 / downsampling_factor)

            print(i, scenes_bounding_rectangle[i])

            #mosaic_image_C0 = np.zeros((int(mosaic_image_height), int(mosaic_image_width)), dtype='uint16')
            #mosaic_image_C1 = np.zeros((int(mosaic_image_height), int(mosaic_image_width)), dtype='uint16')

            with alive_bar(len(scenes_bounding_rectangle),force_tty=True) as bar:

                print(i, scenes_bounding_rectangle[i])
                my_real_roi = (
                scenes_bounding_rectangle[i][0], scenes_bounding_rectangle[i][1], scenes_bounding_rectangle[i][2],
                scenes_bounding_rectangle[i][3])
                print(my_real_roi)
                ch0_downsampled = czidoc.read(roi=my_real_roi, plane={'C': 0}, scene=i, zoom=zoom_factor)
                ch1_downsampled = czidoc.read(roi=my_real_roi, plane={'C': 1}, scene=i, zoom=zoom_factor)

                #add # read a 2D image from a specific channel and scene

                cziname = os.path.splitext(czifilename)[0]

                if (ouput_format=="tiff"):
                    filename = pathout + "/" + cziname + "_ds" + str(downsampling_factor) + "_S" + str(i).zfill(2) + "_C0.tiff"
                    imC0 = Image.fromarray((ch0_downsampled).astype(np.uint16))
                    imC0.save(filename)
                    filename = pathout + "/" + cziname + "_ds" + str(downsampling_factor) + "_S" + str(i).zfill(2) + "_C1.tiff"
                    imC1 = Image.fromarray((ch1_downsampled).astype(np.uint16))
                    imC1.save(filename)

                if (ouput_format == "nii"):
                    #for nii, we need to swap x,y axis (X -> L/R and y-> S/I or A/P)  do check
                    filename = pathout + "/" + cziname + "_ds" + str(downsampling_factor) + "_S" + str(i).zfill(2) + "_C0.nii.gz"
                    array_img = nib.Nifti1Image(np.swapaxes(ch0_downsampled, 0, 1), np.eye(4))
                    nib.save(array_img, filename)
                    filename = pathout + "/" + cziname + "_ds" + str(downsampling_factor) + "_S" + str(i).zfill(2) + "_C1.nii.gz"
                    array_img = nib.Nifti1Image(np.swapaxes(ch1_downsampled, 0, 1), np.eye(4))
                    nib.save(array_img, filename)

                bar()