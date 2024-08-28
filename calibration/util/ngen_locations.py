import os

from django.conf import settings

from calibration.models import CalibrationRun

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


def get_geopackage_directory(run):
    return os.path.join(settings.NGEN_CAL_WORK_DIR, 'geopackage')


def get_geopackage_file(run):
    return os.path.join(settings.NGEN_CAL_WORK_DIR, 'geopackage', f'gauge_{run.gage.gage_id}.gpkg')


#
# def get_forcing_from_hydrofabric_dir(run):
#     return os.path.join(settings.NGEN_CAL_WORK_DIR, 'forcing_from_hydrofabric')
#
#
# def get_observation_from_hydrofabric_dir(run):
#     return os.path.join(settings.NGEN_CAL_WORK_DIR, 'observation_from_hydrofabric')
#
#
# def get_observation_from_hydrofabric_file(run):
#     return os.path.join(get_observation_from_hydrofabric_dir(run), f'{run.gage.gage_id}_hourly_discharge.csv')
#

def get_main_dir(run: CalibrationRun) -> str:
    return os.path.join(settings.NGEN_CAL_RUN_DIR, f'{run.id}_{run.owner}')


# Job-specific forcing directory
def get_forcing_dir(run: CalibrationRun) -> str:
    return os.path.join(get_main_dir(run), 'forcing')


# Job-specific observation directory
def get_observation_dir(run: CalibrationRun) -> str:
    return os.path.join(get_main_dir(run), 'observation')


# Job-specific observation file
def get_observation_file(run: CalibrationRun) -> str:
    return os.path.join(get_observation_dir(run), f'{run.gage.gage_id}_hourly_discharge.csv')
