import os

from django.conf import settings

# Forcing,  obs and geopackage directories will be created as needed
forcing_dir = os.path.join(settings.NGEN_CAL_WORK_DIR, 'forcing')
observation_dir = os.path.join(settings.NGEN_CAL_WORK_DIR, 'observation')
geopackage_dir = os.path.join(settings.NGEN_CAL_WORK_DIR, 'geopackage')


calib_valid_dir = os.path.join(settings.NGEN_CAL_REPO_ROOT, 'python/runCalibValid')
noah_parameter_dir = os.path.join(settings.NGEN_CAL_WORK_DIR, 'bmi_config/Noah-OWP')
parquet_dir = os.path.join(settings.NGEN_CAL_WORK_DIR, 'parquet')


# TODO Need to update this
CAL_PLOTS_DIR = os.path.join(settings.NGEN_CAL_WORK_DIR, 'cal_plots')

dirs = [calib_valid_dir, noah_parameter_dir, parquet_dir]

ngen_exe = os.path.join(settings.NGEN_REPO_ROOT, 'cmake_build/ngen')
cfe_lib = os.path.join(settings.NGEN_REPO_ROOT, 'extern/cfe/cmake_build/libcfebmi.so')
sloth_lib = os.path.join(settings.NGEN_REPO_ROOT, 'extern/sloth/cmake_build/libslothmodel.so')
topmd_lib = os.path.join(settings.NGEN_REPO_ROOT, 'extern/topmodel/cmake_build/libtopmodelbmi.so')
noah_lib = os.path.join(settings.NGEN_REPO_ROOT, 'extern/noah-owp-modular/cmake_build/libsurfacebmi.so')
sft_lib = os.path.join(settings.NGEN_REPO_ROOT, 'extern/SoilFreezeThaw/cmake_build/libsftbmi.so')
smp_lib = os.path.join(settings.NGEN_REPO_ROOT, 'extern/SoilMoistureProfiles/cmake_build/libsmpbmi.so')
lasam_lib = os.path.join(settings.NGEN_REPO_ROOT, 'extern/LASAM/cmake_build/liblasambmi.so')

calibration_py = os.path.join(calib_valid_dir, 'calibration.py')
validation_py = os.path.join(calib_valid_dir, 'validation.py')
# create_input_dir = os.path.join(NGEN_CAL_VENV, 'lib/python3.11/site-packages/createInput')

files = [ngen_exe, cfe_lib, sloth_lib, topmd_lib, noah_lib, sft_lib, smp_lib, lasam_lib, calibration_py, validation_py]

