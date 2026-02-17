import sys 
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
sys.path.append(os.path.abspath("BIDS"))
import bids_manager as bm 

#This function returns the largest multiple of the number a smaller than b
def multiple(a, b):
    m = 0
    n = a + 1
    while n < b:
        if n % a == 0:
            m = n
        n = n + 1

    return m

def get_channels_info(czidoc):
    """Retourne un dict {index: nom_canal} depuis les métadonnées CZI"""
    metadata = czidoc.metadata
    channels_dict = {}
    
    # D'abord essayer de récupérer le nombre de canaux
    try:
        nb_channels = int(metadata["ImageDocument"]["Metadata"]["Information"]["Image"]["SizeC"])
    except:
        nb_channels = 0
    
    # Vérifier avec lecture si besoin
    if nb_channels == 0:
        while True:
            try:
                _ = czidoc.read(roi=(0,0,10,10), plane={'C': nb_channels})
                nb_channels += 1
            except Exception:
                break
        print(f"Nombre de canaux confirme: {nb_channels}")
    
    # Chercher les noms des canaux
    def find_channels(data):
        if isinstance(data, dict):
            if "Channel" in data or "Channels" in data:
                channel_data = data.get("Channel") or data.get("Channels")
                if isinstance(channel_data, list):
                    return channel_data
                elif isinstance(channel_data, dict):
                    return [channel_data]
            for v in data.values():
                result = find_channels(v)
                if result:
                    return result
        elif isinstance(data, list):
            for item in data:
                result = find_channels(item)
                if result:
                    return result
        return None
    
    channels = find_channels(metadata)
    
    if channels:
        for i, ch in enumerate(channels):
            name = ch.get("@Name") or ch.get("Name") or f"C{i}"
            dye = ch.get("DyeId") or ch.get("@DyeId") or ch.get("Dye") or name
            channels_dict[i] = str(dye)
    else:
        # Fallback: juste les indices
        for i in range(nb_channels):
            channels_dict[i] = f"C{i}"
    
    return channels_dict


def czi2bitmapHPC(pathin, czifilename, pathout, downsampling_factor, ouput_format, 
                  layout=None, bids_info=None, bids_root_path=None):    
    czifile_scenes = os.path.join(pathin, czifilename)
    bids_infos_per_channel = {} 
    with pyczi.open_czi(czifile_scenes) as czidoc:
        scenes_bounding_rectangle = czidoc.scenes_bounding_rectangle
        channels_info = get_channels_info(czidoc)  # {0: 'DAPI', 1: 'GFP', ...}
        nb_channels = len(channels_info)
        nb_scenes = len(scenes_bounding_rectangle) 

        for i in range(0, nb_scenes):
            zoom_factor = float(1.0 / downsampling_factor)
            
            with alive_bar(nb_scenes, force_tty=True, title=f"Scene {i}") as bar:
                my_real_roi = (
                    scenes_bounding_rectangle[i][0], scenes_bounding_rectangle[i][1], 
                    scenes_bounding_rectangle[i][2], scenes_bounding_rectangle[i][3]
                )

                channel_images = {}
                for c in range(nb_channels):
                    channel_images[c] = czidoc.read(roi=my_real_roi, plane={'C':c}, scene=i, zoom=zoom_factor)

                cziname = os.path.splitext(czifilename)[0]
                
                for c in range(nb_channels):
                    channel_images[c] = czidoc.read(roi=my_real_roi, plane={'C':c}, scene=i, zoom=zoom_factor)

                cziname = os.path.splitext(czifilename)[0]
                
                for c in range(nb_channels):
                    ext = ".tiff" if ouput_format == "tiff" else ".nii.gz"
                    
                    filename = os.path.join(pathout, f"{cziname}_ds{downsampling_factor}_S{str(i).zfill(2)}_C{c}{ext}")
                    
                    if (ouput_format == "tiff"):
                        tf.imwrite(filename, channel_images[c], imagej=True)
                    else:
                        array_img = nib.Nifti1Image(np.swapaxes(channel_images[c], 0, 1), np.eye(4))
                        nib.save(array_img, filename)

                    if layout and bids_info and bids_root_path:
                        channel_bids_info = bm.get_bids_info(
                            layout, 
                            bids_info, 
                            bids_root_path, 
                            channel_name=channels_info[c]
                        )
                        
                        if c not in bids_infos_per_channel:
                            bids_infos_per_channel[c] = channel_bids_info
                        
                        bids_folder, bids_root = bm.get_channel_path(channel_bids_info, channel_name=channels_info[c])
                        
                        alias_filename = f"{bids_root}_chunk-{i:02d}{ext}"
                        alias_path = os.path.join(bids_folder, alias_filename)
                        
                        if not os.path.exists(alias_path):
                            os.link(os.path.abspath(filename), alias_path)
                            print(f"  -> Lien BIDS: {alias_filename}")
                        
                        if ouput_format == "nii":
                            deriv_folder, deriv_root = bm.get_derivative_path(
                                channel_bids_info,
                                channel_name=channels_info[c],
                                resolution=f"ds{downsampling_factor}"
                            )
                            
                            deriv_filename = f"{deriv_root}.nii.gz"
                            deriv_path = os.path.join(deriv_folder, deriv_filename)
                            
                            if not os.path.exists(deriv_path):
                                os.link(os.path.abspath(filename), deriv_path)
                                print(f"  -> Lien derivatives: {deriv_filename}")
                bar()
      
    return channels_info, nb_scenes, bids_infos_per_channel  
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
