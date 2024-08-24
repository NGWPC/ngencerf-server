import os

from django.conf import settings

from calibration.models import CalibrationRun

# Forcing,  obs and geopackage directories will be created as needed
forcing_from_hydrofabric_dir = os.path.join(settings.NGEN_CAL_WORK_DIR, 'forcing_from_hydrofabric')
observation_from_hydrofabric_dir = os.path.join(settings.NGEN_CAL_WORK_DIR, 'observation_from_hydrofabric')
geopackage_dir = os.path.join(settings.NGEN_CAL_WORK_DIR, 'geopackage')

dirs = [CALIB_VALID_DIR := os.path.join(settings.NGEN_CAL_REPO_ROOT, 'python/runCalibValid'),
        NOAH_PARAMETER_DIR := os.path.join(settings.NGEN_CAL_WORK_DIR, 'bmi_config/Noah-OWP'),
        PARQUET_DIR := os.path.join(settings.NGEN_CAL_WORK_DIR, 'parquet')]

# TODO Need to update this
CAL_PLOTS_DIR = os.path.join(settings.NGEN_CAL_WORK_DIR, 'cal_plots')

files = [NGEN_EXE := os.path.join(settings.NGEN_REPO_ROOT, 'cmake_build/ngen'),
         CFE_LIB := os.path.join(settings.NGEN_REPO_ROOT, 'extern/cfe/cmake_build/libcfebmi.so'),
         SLOTH_LIB := os.path.join(settings.NGEN_REPO_ROOT, 'extern/sloth/cmake_build/libslothmodel.so'),
         TOPMD_LIB := os.path.join(settings.NGEN_REPO_ROOT, 'extern/topmodel/cmake_build/libtopmodelbmi.so'),
         NOAH_LIB := os.path.join(settings.NGEN_REPO_ROOT, 'extern/noah-owp-modular/cmake_build/libsurfacebmi.so'),
         SFT_LIB := os.path.join(settings.NGEN_REPO_ROOT, 'extern/SoilFreezeThaw/cmake_build/libsftbmi.so'),
         SMP_LIB := os.path.join(settings.NGEN_REPO_ROOT, 'extern/SoilMoistureProfiles/cmake_build/libsmpbmi.so'),
         LASAM_LIB := os.path.join(settings.NGEN_REPO_ROOT, 'extern/LASAM/cmake_build/liblasambmi.so'),

         CALIBRATION_PY := os.path.join(CALIB_VALID_DIR, 'calibration.py'),
         VALIDATION_PY := os.path.join(CALIB_VALID_DIR, 'validation.py')]


def get_main_dir(run: CalibrationRun) -> str:
    return os.path.join(settings.NGEN_CAL_RUN_DIR, f'{run.id}_{run.owner}')


# Job-specific observation directory
def get_observation_directory(run: CalibrationRun) -> str:
    return os.path.join(get_main_dir(run), 'observation')


# Job-specific forcing directory
def get_forcing_directory(run: CalibrationRun) -> str:
    return os.path.join(get_main_dir(run), 'forcing', run.gage.gage_id)
