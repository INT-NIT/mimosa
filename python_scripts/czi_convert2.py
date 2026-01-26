import os
from pylibCZIrw import czi as pyczi # lecture des .czi 
import json # souvent pour la lecture des metadonnées s
from matplotlib import pyplot as plt
import matplotlib.cm as cm
import numpy as np
#from PIL import Image
import tifffile as tf
import nibabel as nib
from skimage import img_as_ubyte
import xml.etree.ElementTree as ET
from alive_progress import alive_bar # barre de progression jolie en console 

#This function returns the largest multiple of the number a smaller than b
def multiple(a, b):
    m = 0
    n = a + 1
    while n < b:
        if n % a == 0:
            m = n
        n = n + 1

    return m

def get_nb_channels(czidoc):
    metadata_dict = czidoc.metadata
    Channel_size=int(metadata_dict["ImageDocument"]["Metadata"]["Information"]["Image"]["SizeC"])
    print(Channel_size)
    # in case we didnt find any channel which is illogic we should verify ( maybe by mistake from the microscope )
    if Channel_size == 0:
        while True:
            try:
                _ = czidoc.read(roi=(0,0,10,10), plane={'C': Channel_size})
                Channel_size += 1
            except Exception:
                break
        print(f"Number of channels confirmed : {Channel_size}")
    return Channel_size


def czi2bitmap(pathin, czifilename, pathout, patch_factor, downsampling_factor, full_patch_w_h,ouput_format):
    # patch_factor = facteur de combinaison des petits carrées (patchs)
    # full_patch_w_h = taille de base d'un patch avant réduction
    czifile_scenes = os.path.join(pathin, czifilename) 

    with pyczi.open_czi(czifile_scenes) as czidoc:
        scenes_bounding_rectangle = czidoc.scenes_bounding_rectangle 
        print("Rectangles de scènes:", scenes_bounding_rectangle)   
        nb_channels=get_nb_channels(czidoc)
        for i in range(0, len(scenes_bounding_rectangle)): 
            #with alive_bar(len(scenes_bounding_rectangle),force_tty=True) as bar:
            print("ROI Scene",i)
            # calculation of the reduced patch size
            downsampled_patch_w_h = int(full_patch_w_h / downsampling_factor)
            print(i, scenes_bounding_rectangle[i]) 
            # calculation of the necessary number of patchs 
            nb_patch_w = int((scenes_bounding_rectangle[i].w) / (full_patch_w_h * patch_factor)) # patch factor => 0.5 means on fais 2 fois plus de patchs quand par exemple on veut eviter les zones vides entre deux patchs quand on veut une lecture plus précise 
            nb_patch_h = int((scenes_bounding_rectangle[i].h) / (full_patch_w_h * patch_factor))
            # final reduced mosaic size of the scene  
            mosaic_image_width = round(float(scenes_bounding_rectangle[i].w) / (downsampling_factor) + 0.5) # 0.5 astuce d'arrondi pour qu'on perd pas de pixel 
            mosaic_image_height = round(float(scenes_bounding_rectangle[i].h) / (downsampling_factor) + 0.5)
            # create empty mosaics for each channel
            mosaic_image={}
            for c in range(nb_channels):
                mosaic_image[c] = np.zeros((int(mosaic_image_height), int(mosaic_image_width)), dtype='uint16')
            # reduced patch size in pixels 
            mosaic_image_patch_size_w = int(downsampled_patch_w_h * patch_factor)
            mosaic_image_patch_size_h = int(downsampled_patch_w_h * patch_factor)

            with alive_bar((nb_patch_w+1)*(nb_patch_h+1),force_tty=True) as bar:
                # +1 is used to cover the right and bottom edge of the stage
                for x in range(0, nb_patch_w + 1): 
                    for y in range(0, nb_patch_h + 1):

                       # the normal size of a patch  
                        patch_width = patch_factor * full_patch_w_h # si on a patch_factor = 0.5 ca veut on divise encore un patch en deux patchs (facteur de recouvrement d'un patch)
                        patch_height = patch_factor * full_patch_w_h
                        # is used to correct the size of the last patch to fit exactly at the end of the scene
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
                        # roi here is a patch itself 
                        # pylibCZIrw wait "int" values in order to represent a real one pixel and not a flloat , "max" for the last patch can cause problem in case it has null or negative value 
                        x0 = int(scenes_bounding_rectangle[i].x + patch_factor * full_patch_w_h * x)
                        y0 = int(scenes_bounding_rectangle[i].y + patch_factor * full_patch_w_h * y)
                        w0 = int(max(1, patch_width))
                        h0 = int(max(1, patch_height))
                        my_roi_patched = (x0, y0, w0, h0)


                        for c in range(nb_channels):
                            # reads the my_roi_patched region for channel c
                            ch = czidoc.read(roi=my_roi_patched, plane={'C': c})
                            # perform the resolution , skipping for exemple 4 pixels in the roi  
                            ch_res = ch[::downsampling_factor, ::downsampling_factor]
                            # placing the patch in the mosaic image of a given channel 
                            mosaic_image[c][
                            y * mosaic_image_patch_size_h:y * mosaic_image_patch_size_h + ch_res[..., 0].shape[0],
                            x * mosaic_image_patch_size_w:x * mosaic_image_patch_size_w + ch_res[..., 0].shape[1]] = ch_res[..., 0]
                        bar() 

                # Remove .czi → to construct the output filenames.
                cziname = os.path.splitext(czifilename)[0]
                for c in range(nb_channels):
                    if (ouput_format=="tiff"):
                        #old method using PIL (replaced by tifffile)
                        filename = pathout + "/" + cziname + "_ds" + str(downsampling_factor) + "_S" + str(i).zfill(2) + "_C"+str(c)+".tiff"
                        #imC0 = Image.fromarray((mosaic_image_C0).astype(np.uint16))
                        #imC0.save(filename)
                        tf.imwrite(filename, mosaic_image[c],imagej=True)
                    if (ouput_format == "nii"):
                        #for nii, we need to swap x,y axis (X -> L/R and y-> S/I or A/P)  do check
                        filename = pathout + "/" + cziname + "_ds" + str(downsampling_factor) + "_S" + str(i).zfill(2) + "_C"+str(c)+".nii.gz"
                        array_img = nib.Nifti1Image(np.swapaxes(mosaic_image[c], 0, 1), np.eye(4))
                        nib.save(array_img, filename)

def czi2bitmapHPC(pathin, czifilename, pathout, downsampling_factor, ouput_format, bids_folder=None, bids_root=None):
    czifile_scenes = os.path.join(pathin, czifilename)

    with pyczi.open_czi(czifile_scenes) as czidoc:
        scenes_bounding_rectangle = czidoc.scenes_bounding_rectangle
        nb_channels = get_nb_channels(czidoc)
        
        for i in range(0, len(scenes_bounding_rectangle)):
            zoom_factor = float(1.0 / downsampling_factor)
            
            # Utilisation de la barre de progression pour les scènes
            with alive_bar(len(scenes_bounding_rectangle), force_tty=True, title=f"Scene {i}") as bar:
                my_real_roi = (
                    scenes_bounding_rectangle[i][0], scenes_bounding_rectangle[i][1], 
                    scenes_bounding_rectangle[i][2], scenes_bounding_rectangle[i][3]
                )

                channel_images = {}
                for c in range(nb_channels):
                    channel_images[c] = czidoc.read(roi=my_real_roi, plane={'C':c}, scene=i, zoom=zoom_factor)

                cziname = os.path.splitext(czifilename)[0]
                
                for c in range(nb_channels):
                    ext = ".tiff" if ouput_format == "tiff" else ".nii.gz"
                    
                    # 1. NOMMAGE HISTORIQUE (Fichier physique réel dans pathout)
                    filename = os.path.join(pathout, f"{cziname}_ds{downsampling_factor}_S{str(i).zfill(2)}_C{c}{ext}")
                    
                    if (ouput_format == "tiff"):
                        tf.imwrite(filename, channel_images[c], imagej=True)
                    else:
                        array_img = nib.Nifti1Image(np.swapaxes(channel_images[c], 0, 1), np.eye(4))
                        nib.save(array_img, filename)

                    # 2. ALIAS BIDS (Lien symbolique dans bids_folder)
                    if bids_folder and bids_root:
                        # Si tu as plusieurs canaux mais que tu ne veux qu'un alias BIDS global
                        # Attention: Si nb_channels > 1, le canal 1 écrasera le lien du canal 0 ici.
                        alias_filename = f"{bids_root}_chunk-{i:02d}_FLUO{ext}"
                        alias_path = os.path.join(bids_folder, alias_filename)
                        
                        if not os.path.exists(alias_path):
                            try:
                                os.link(os.path.abspath(filename), alias_path)
                            except OSError:
                                import shutil
                                shutil.copy2(os.path.abspath(filename), alias_path)
                            print(f"  -> Alias créé : {alias_filename}")
                bar()
"""
def main():
    pathin = "/DATA/mimosa/dataset/1-Fenouil-MTO10092101/"
    pathout = "/DATA/mimosa/renamed"
    czifilename ="MTO10092101_Cx_248-256.czi"
    patch_factor = 0.5
    downsampling_factor = 4
    full_patch_w_h = 1024
    ouput_format="nii" #or "nii"

    czi2bitmap(pathin, czifilename, pathout, patch_factor, downsampling_factor, full_patch_w_h,ouput_format)

if __name__ == "__main__":
    main()
"""
