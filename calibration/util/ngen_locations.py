import os

from django.conf import settings

# Forcing,  obs and geopackage directories will be created as needed
forcing_dir = os.path.join(settings.NGEN_CAL_WORK_DIR, 'forcing')
observation_dir = os.path.join(settings.NGEN_CAL_WORK_DIR, 'observation')
geopackage_dir = os.path.join(settings.NGEN_CAL_WORK_DIR, 'geopackage')


CALIB_VALID_DIR = os.path.join(settings.NGEN_CAL_REPO_ROOT, 'python/runCalibValid')
NOAH_PARAMETER_DIR = os.path.join(settings.NGEN_CAL_WORK_DIR, 'bmi_config/Noah-OWP')
parquet_dir = os.path.join(settings.NGEN_CAL_WORK_DIR, 'parquet')


# TODO Need to update this
CAL_PLOTS_DIR = os.path.join(settings.NGEN_CAL_WORK_DIR, 'cal_plots')

dirs = [CALIB_VALID_DIR, NOAH_PARAMETER_DIR, parquet_dir]

NGEN_EXE = os.path.join(settings.NGEN_REPO_ROOT, 'cmake_build/ngen')
CFE_LIB = os.path.join(settings.NGEN_REPO_ROOT, 'extern/cfe/cmake_build/libcfebmi.so')
SLOTH_LIB = os.path.join(settings.NGEN_REPO_ROOT, 'extern/sloth/cmake_build/libslothmodel.so')
TOPMD_LIB = os.path.join(settings.NGEN_REPO_ROOT, 'extern/topmodel/cmake_build/libtopmodelbmi.so')
NOAH_LIB = os.path.join(settings.NGEN_REPO_ROOT, 'extern/noah-owp-modular/cmake_build/libsurfacebmi.so')
SFT_LIB = os.path.join(settings.NGEN_REPO_ROOT, 'extern/SoilFreezeThaw/cmake_build/libsftbmi.so')
SMP_LIB = os.path.join(settings.NGEN_REPO_ROOT, 'extern/SoilMoistureProfiles/cmake_build/libsmpbmi.so')
LASAM_LIB = os.path.join(settings.NGEN_REPO_ROOT, 'extern/LASAM/cmake_build/liblasambmi.so')

CALIBRATION_PY = os.path.join(CALIB_VALID_DIR, 'calibration.py')
VALIDATION_PY = os.path.join(CALIB_VALID_DIR, 'validation.py')
# create_input_dir = os.path.join(NGEN_CAL_VENV, 'lib/python3.11/site-packages/createInput')

files = [NGEN_EXE, CFE_LIB, SLOTH_LIB, TOPMD_LIB, NOAH_LIB, SFT_LIB, SMP_LIB, LASAM_LIB, CALIBRATION_PY, VALIDATION_PY]

