import os
from pylibCZIrw import czi as pyczi # lecture des .czi 



def czi2bitmap(pathin, czifilename):

    czifile_scenes = os.path.join(pathin, czifilename) # combine le nom du fichier et le dossier ou se trouve le fichier 

    with pyczi.open_czi(czifile_scenes) as czidoc: # ouverture fichier czi 
        scenes_bounding_rectangle = czidoc.scenes_bounding_rectangle # récuperer la taille et la position de chaque scene 
        print("Rectangles de scènes:", scenes_bounding_rectangle)   
def main():
    pathin = "/DATA/mimosa/dataset/1-Fenouil-MTO10092101/"
    czifilename ="MTO10092101_Cx_200-208.czi"

    czi2bitmap(pathin, czifilename)

if __name__ == "__main__":
    main()