# The Mimosa Project
A set of tools for Multiscale Imaging for marMOset Software &amp; Analysis

# Description
The MIMOSA project aims to provide a multiscale, automated, versatile, and user-friendly tool for 3D reconstruction and cell quantification in the brain of the marmoset (<i>Callithrix jacchus</i>) using histological sections. Designed to meet the need for precise and accurate quantification in viral tracing experiments, MIMOSA facilitates efficient analysis.

The tool utilizes DAPI staining to register histological sections to MRI atlases of the marmoset brain, while fluorescent protein labeling enables neuron quantification in targeted areas. MIMOSA integrates Cellpose, allowing users to develop custom-trained models for neuron quantification. Additionally, it includes a built-in .czi-to-.tiff converter, enabling quick extraction of any pyramid level from .czi files into .tiff format.


# Installing for development

git clone https://github.com/INT-NIT/mimosa.git \
cd mimosa

### Create the conda environment by running

## for macosX( tested on macos Ventura 13.4.1):
conda env create -f install_env/Mac/environment_macosX_13.4.yml \
conda activate mimosa_dev \
pip install install_env/Mac/additionnal_package/pylibCZIrw-3.5.1-cp311-cp311-macosx_10_9_universal2.whl

## for Linux ( tested on Debian 12 bookworm):
conda env create -f install_env/Linux/requirements_Debian12.yml \
conda activate mimosa_dev 
