import logging
from pathlib import Path

from django.conf import settings

from calibration.models import CalibrationRun
from cerfServer.settings import NGEN_ENVIRONMENT

logger = logging.getLogger(__name__)

CALIB_VALID_DIR = str(Path(settings.NGEN_CAL_REPO_ROOT) / 'python/runCalibValid')

static_dirs = [
    NWM_RETROSPECTIVE_DIR := str(Path(settings.NGEN_STATIC_DIR) / 'nwm_retrospective'),
    NOAH_PARAMETER_DIR := str(Path(settings.NGEN_STATIC_DIR) / 'bmi_config/Noah-OWP'),
    PARQUET_DIR := str(Path(settings.NGEN_STATIC_DIR) / 'parquet')
]

files = [
    NGEN_EXE := str(Path(settings.NGEN_REPO_ROOT) / 'cmake_build/ngen'),
    CFE_LIB := str(Path(settings.NGEN_REPO_ROOT) / 'extern/cfe/cmake_build/libcfebmi.so'),
    SLOTH_LIB := str(Path(settings.NGEN_REPO_ROOT) / 'extern/sloth/cmake_build/libslothmodel.so'),
    TOPMD_LIB := str(Path(settings.NGEN_REPO_ROOT) / 'extern/topmodel/cmake_build/libtopmodelbmi.so'),
    NOAH_LIB := str(Path(settings.NGEN_REPO_ROOT) / 'extern/noah-owp-modular/cmake_build/libsurfacebmi.so'),
    SFT_LIB := str(Path(settings.NGEN_REPO_ROOT) / 'extern/SoilFreezeThaw/cmake_build/libsftbmi.so'),
    SMP_LIB := str(Path(settings.NGEN_REPO_ROOT) / 'extern/SoilMoistureProfiles/cmake_build/libsmpbmi.so'),
    LASAM_LIB := str(Path(settings.NGEN_REPO_ROOT) / 'extern/LASAM/cmake_build/liblasambmi.so'),
    # TODO This path is not correct
    PET_LIB := str(Path(settings.NGEN_REPO_ROOT) / 'extern/pet/cmake_build/libpetbmi.so'),
    SNOW17_LIB := str(Path(settings.NGEN_REPO_ROOT) / 'extern/snow17/cmake_build/libsnow17bmi.so'),
    SAC_LIB := str(Path(settings.NGEN_REPO_ROOT) / 'extern/sac-sma/cmake_build/libsacbmi.so'),

    CALIBRATION_PY := str(Path(CALIB_VALID_DIR) / 'calibration.py'),
    VALIDATION_PY := str(Path(CALIB_VALID_DIR) / 'validation.py')
]


def check_files():
    # If we are running locally,then ngen and ngen-cal files must be on our machine
    simulate = getattr(settings, 'NGEN_CAL_SIMULATE', False)
    if NGEN_ENVIRONMENT == NGEN_ENVIRONMENT.LOCAL and not simulate:
        for file in files:
            if not Path(file).is_file():
                logger.warning(f'{file} does not exist')

        for directory in static_dirs:
            if not Path(directory).is_dir():
                logger.warning(f'{directory} does not exist')
            else:
                if not any(Path(directory).iterdir()):
                    logger.warning(f'{directory} is empty')


# Construct the directory where the Input/Output is
def get_gage_dir(run: CalibrationRun) -> str | bytes:
    return str(Path(
        run.job_data_dir) / f'{run.objective_function.name.lower()}_{run.optimization.name.lower()}' / run.user_formulation_name / run.gage.gage_id)


def get_realization_file_path(run: CalibrationRun) -> str:
    return str(Path(get_gage_dir(run)) / f'{run.gage.gage_id}_realization_config_bmi_calib.json')


def get_forcing_filename_pattern() -> str:
    return r"^cat-\d+\.csv$"


# Job-specific forcing directory
def get_forcing_dir_for_job(run: CalibrationRun) -> str:
    return str(Path(run.job_data_dir) / 'forcing')


# Job-specific observation directory
def get_observational_dir_for_job(run: CalibrationRun) -> str:
    return str(Path(run.job_data_dir) / 'observation')


def get_observational_filename(run: CalibrationRun):
    return f'{run.gage.gage_id}_hourly_discharge.csv'


# Job-specific observation file
def get_observational_file_for_job(run: CalibrationRun) -> str:
    return str(Path(get_observational_dir_for_job(run)) / get_observational_filename(run)) if run.gage else None


# TODO This is temporary while we are allowing uploading of Geopackage files
# Job-specific geopackage directory
def get_geopackage_dir_for_job(run: CalibrationRun) -> str:
    return str(Path(run.job_data_dir) / 'geopackage')


def get_geopackage_filename(run: CalibrationRun) -> str:
    return f'gauge_{run.gage.gage_id}.gpkg'


def get_geopackage_file_for_job(run: CalibrationRun) -> str:
    return str(Path(get_geopackage_dir_for_job(run)) / get_geopackage_filename(run)) if run.gage else None


def get_input_dir(run: CalibrationRun) -> str:
    return str(Path(get_gage_dir(run)) / 'Input')


def get_output_dir(run: CalibrationRun) -> str:
    return str(Path(get_gage_dir(run)) / 'Output')


def get_output_calibration_run_dir(run: CalibrationRun) -> str:
    return str(Path(get_output_dir(run)) / 'Calibration_Run')


def get_output_validation_run_dir(run: CalibrationRun) -> str:
    return str(Path(get_output_dir(run)) / 'Validation_Run')


def get_worker_path(run: CalibrationRun, worker_name) -> str:
    return str(Path(get_output_calibration_run_dir(run)) / worker_name)


def get_metrics_iteration_csv(run: CalibrationRun) -> str:
    return f'{run.gage.gage_id}_metrics_iteration.csv'


def get_metrics_iteration_file(run: CalibrationRun, worker_name) -> str:
    return str(Path(get_worker_path(run, worker_name)) / get_metrics_iteration_csv(run))


def get_metrics_iteration_file_from_worker_dir(run: CalibrationRun, worker_dir) -> str:
    return str(Path(worker_dir) / get_metrics_iteration_csv(run))


def get_params_iteration_file(run: CalibrationRun, worker_name) -> str:
    return str(Path(get_worker_path(run, worker_name)) / f'{run.gage.gage_id}_params_iteration.csv')


def get_objective_log_best_file(run: CalibrationRun, worker_name) -> str:
    return str(Path(get_worker_path(run, worker_name)) / f'{run.gage.gage_id}_objective_log.txt')


def get_calibration_stdout_file(run: CalibrationRun) -> str:
    return str(Path(get_output_calibration_run_dir(run)) / 'ngen-cal_calibration_stdout.log')


def get_global_best_params_file(run: CalibrationRun) -> str:
    return str(Path(get_output_calibration_run_dir(run)) / f'{run.gage.gage_id}_global_best_params.csv')


def get_validation_control_stdout_file(run: CalibrationRun) -> str:
    return str(Path(get_output_validation_run_dir(run)) / 'ngen-cal_validation_control_stdout.log')


def get_validation_best_stdout_file(run: CalibrationRun) -> str:
    return str(Path(get_output_validation_run_dir(run)) / 'ngen-cal_validation_best_stdout.log')


def get_calibration_input_file(run: CalibrationRun) -> str:
    return str(Path(get_input_dir(run)) / f'{run.gage.gage_id}_config_calib.yaml')


def get_validation_control_input_file(run: CalibrationRun) -> str:
    return str(Path(get_output_validation_run_dir(run)) / f'{run.gage.gage_id}_config_valid_control.yaml')


def get_validation_best_input_file(run: CalibrationRun) -> str:
    return str(Path(get_output_validation_run_dir(run)) / f'{run.gage.gage_id}_config_valid_best.yaml')
