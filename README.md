# the mimosa project
a set of tools for Multiscale Imaging for marMOset Software &amp; Analysis

# Installing for development

## for macosX( tested on macos Ventura 13.4.1):

git clone https://github.com/arnaudletroter/mimosa.git

cd mimosa

### Create the environment by running
conda env create -f install_env/Mac/environment_macosX_13.4.yml \
conda activate mimosa_dev \
pip install install_env/Mac/package/pylibCZIrw-3.5.1-cp311-cp311-macosx_10_9_universal2.whl

## for Linux ( tested on Debian 12 bookworm):
conda env create -f install_env/Linux/requirements_Debian12.yml \
conda activate mimosa_dev 
