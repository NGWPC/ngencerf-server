import logging
import os
from typing import Literal

from django.conf import settings

from calibration.enums import ValidationType
from calibration.models import CalibrationRun
from cerfServer.settings import NGEN_ENVIRONMENT

logger = logging.getLogger(__name__)

CALIB_VALID_DIR = os.path.join(settings.NGEN_CAL_REPO_ROOT, 'python', 'runCalibValid')

static_dirs = [
    NWM_RETROSPECTIVE_DIR := os.path.join(settings.NGEN_STATIC_DIR, 'nwm_retrospective'),
    NOAH_PARAMETER_DIR := os.path.join(settings.NGEN_STATIC_DIR, 'bmi_config', 'Noah-OWP'),
    PARQUET_DIR := os.path.join(settings.NGEN_STATIC_DIR, 'parquet')
]

files = [
    NGEN_EXE := os.path.join(settings.NGEN_REPO_ROOT, 'cmake_build', 'ngen'),
    CFE_LIB := os.path.join(settings.NGEN_REPO_ROOT, 'extern', 'cfe', 'cmake_build', 'libcfebmi.so'),
    SLOTH_LIB := os.path.join(settings.NGEN_REPO_ROOT, 'extern', 'sloth', 'cmake_build', 'libslothmodel.so'),
    TOPMD_LIB := os.path.join(settings.NGEN_REPO_ROOT, 'extern', 'topmodel', 'cmake_build', 'libtopmodelbmi.so'),
    NOAH_LIB := os.path.join(settings.NGEN_REPO_ROOT, 'extern', 'noah-owp-modular', 'cmake_build', 'libsurfacebmi.so'),
    SFT_LIB := os.path.join(settings.NGEN_REPO_ROOT, 'extern', 'SoilFreezeThaw', 'cmake_build', 'libsftbmi.so'),
    SMP_LIB := os.path.join(settings.NGEN_REPO_ROOT, 'extern', 'SoilMoistureProfiles', 'cmake_build', 'libsmpbmi.so'),
    LASAM_LIB := os.path.join(settings.NGEN_REPO_ROOT, 'extern', 'LASAM', 'cmake_build', 'liblasambmi.so'),
    PET_LIB := os.path.join(settings.NGEN_REPO_ROOT, 'extern', 'evapotranspiration', 'evapotranspiration', 'cmake_build', 'libpetbmi.so'),
    SNOW17_LIB := os.path.join(settings.NGEN_REPO_ROOT, 'extern', 'snow17', 'cmake_build', 'libsnow17bmi.so'),
    SAC_LIB := os.path.join(settings.NGEN_REPO_ROOT, 'extern', 'sac-sma', 'cmake_build', 'libsacbmi.so')
]


def check_files():
    # If we are running locally,then ngen and ngen-cal files must be on our machine
    if NGEN_ENVIRONMENT == NGEN_ENVIRONMENT.LOCAL:
        for file in files:
            if not os.path.isfile(file):
                logger.warning(f'{file} does not exist')

        for directory in static_dirs:
            if not os.path.isdir(directory):
                logger.warning(f'{directory} does not exist')
            elif not os.listdir(directory):
                logger.warning(f'{directory} is empty')


# Construct the directory where the Input/Output is
def get_gage_dir(run: CalibrationRun) -> str:
    return os.path.join(
        run.job_data_dir,
        f"{run.objective_function.name.lower()}_{run.optimization.name.lower()}",
        run.user_formulation_name,
        run.gage.gage_id
    )


def get_realization_file_path(run: CalibrationRun) -> str:
    return os.path.join(get_gage_dir(run), f"{run.gage.gage_id}_realization_config_bmi_calib.json")


def get_forcing_filename_pattern() -> str:
    return r"^cat-\d+\.csv$"


# Job-specific forcing directory
def get_forcing_dir_for_job(run: CalibrationRun) -> str:
    return os.path.join(run.job_data_dir, 'forcing')


# Job-specific observation directory
def get_observational_dir_for_job(run: CalibrationRun) -> str:
    return os.path.join(run.job_data_dir, 'observation')


def get_observational_filename(run: CalibrationRun) -> str:
    return f"{run.gage.gage_id}_hourly_discharge.csv"


# Job-specific observation file
def get_observational_file_for_job(run: CalibrationRun) -> str:
    return os.path.join(get_observational_dir_for_job(run), get_observational_filename(run)) if run.gage else None


# Job-specific geopackage directory
def get_geopackage_dir_for_job(run: CalibrationRun) -> str:
    return os.path.join(run.job_data_dir, 'geopackage')


def get_geopackage_filename(run: CalibrationRun) -> str:
    return f"gauge_{run.gage.gage_id}.gpkg"


def get_geopackage_file_for_job(run: CalibrationRun) -> str | None:
    return os.path.join(get_geopackage_dir_for_job(run), get_geopackage_filename(run)) if run.gage else None


def get_input_dir(run: CalibrationRun) -> str:
    return os.path.join(get_gage_dir(run), 'Input')


def get_output_dir(run: CalibrationRun) -> str:
    return os.path.join(get_gage_dir(run), 'Output')


def get_output_calibration_run_dir(run: CalibrationRun) -> str:
    return os.path.join(get_output_dir(run), 'Calibration_Run')


def get_output_validation_run_dir(run: CalibrationRun) -> str:
    return os.path.join(get_output_dir(run), 'Validation_Run')


def get_output_validation_plot_dir(run: CalibrationRun) -> str:
    return os.path.join(get_output_validation_run_dir(run), 'Plot_Valid')


def get_output_validation_iteration_plot_dir(run: CalibrationRun, iteration_num: int, worker_name: str) -> str:
    return os.path.join(get_output_validation_run_dir(run), f'Plot_Valid_{worker_name}_iter{iteration_num}')


def get_full_worker_filename(worker_name: str) -> str:
    return f"ngen_{worker_name}_worker"


def get_worker_path(run: CalibrationRun, worker_name: str) -> str:
    return os.path.join(get_output_calibration_run_dir(run), get_full_worker_filename(worker_name))


def get_metrics_iteration_csv(run: CalibrationRun) -> str:
    return f"{run.gage.gage_id}_metrics_iteration.csv"


def get_output_last_iteration_csv(run: CalibrationRun) -> str:
    return f"{run.gage.gage_id}_output_last_iteration.csv"


def get_output_last_iteration_file(run: CalibrationRun, worker_dir: str) -> str:
    return os.path.join(worker_dir, get_output_last_iteration_csv(run))


def get_output_best_iteration_csv(run: CalibrationRun) -> str:
    return f"{run.gage.gage_id}_output_best_iteration.csv"


def get_output_best_iteration_file(run: CalibrationRun, worker_dir: str) -> str:
    return os.path.join(worker_dir, get_output_best_iteration_csv(run))


def get_output_valid_control_csv(run: CalibrationRun) -> str:
    return f"{run.gage.gage_id}_output_valid_control.csv"


def get_output_valid_control_file(run: CalibrationRun) -> str:
    return os.path.join(get_output_validation_run_dir(run), get_output_valid_control_csv(run))


def get_output_valid_best_csv(run: CalibrationRun) -> str:
    return f"{run.gage.gage_id}_output_valid_best.csv"


def get_output_valid_best_file(run: CalibrationRun) -> str:
    return os.path.join(get_output_validation_run_dir(run), get_output_valid_best_csv(run))


def get_output_iteration_csv(run: CalibrationRun, iteration_num: int) -> str:
    return f"{run.gage.gage_id}_output_iteration_{iteration_num:04d}.csv"


def get_output_iteration_file(run: CalibrationRun, iteration_num: int, worker_dir: str) -> str:
    return os.path.join(worker_dir, 'Output_Iteration', get_output_iteration_csv(run, iteration_num))


def get_metrics_iteration_file(run: CalibrationRun, worker_name: str) -> str:
    return os.path.join(get_worker_path(run, worker_name), get_metrics_iteration_csv(run))


def get_cost_hist_file(run: CalibrationRun) -> str:
    return os.path.join(get_output_calibration_run_dir(run), f"{run.gage.gage_id}_cost_hist.csv")


def get_metrics_iteration_file_from_worker_dir(run: CalibrationRun, worker_dir: str) -> str:
    return os.path.join(worker_dir, get_metrics_iteration_csv(run))


def get_params_iteration_file(run: CalibrationRun, worker_name: str) -> str:
    return os.path.join(get_worker_path(run, worker_name), f"{run.gage.gage_id}_params_iteration.csv")


def get_objective_log_best_file(run: CalibrationRun, worker_name: str) -> str:
    return os.path.join(get_worker_path(run, worker_name), f"{run.gage.gage_id}_objective_log.txt")


def get_calibration_stdout_file(run: CalibrationRun) -> str:
    return os.path.join(get_output_calibration_run_dir(run), 'ngen-cal_calibration_stdout.log')


def get_calibration_performance_file(run: CalibrationRun) -> str:
    return os.path.join(get_output_calibration_run_dir(run), 'ngen-cal_calibration_performance.log')


def get_global_best_params_file(run: CalibrationRun) -> str:
    return os.path.join(get_output_calibration_run_dir(run), f"{run.gage.gage_id}_global_best_params.csv")


def get_calibration_input_file(run: CalibrationRun) -> str:
    return os.path.join(get_input_dir(run), f"{run.gage.gage_id}_config_calib.yaml")


def get_validation_best_input_file(run: CalibrationRun) -> str:
    return os.path.join(get_output_validation_run_dir(run), f"{run.gage.gage_id}_config_valid_best.yaml")


def get_validation_best_stdout_file(run: CalibrationRun) -> str:
    return os.path.join(get_output_validation_run_dir(run), 'ngen-cal_validation_best_stdout.log')


def get_validation_performance_file(run: CalibrationRun, worker_name: str, iteration_num: int) -> str:
    return os.path.join(get_output_validation_run_dir(run), f"ngen-cal_validation_{worker_name}_iter{iteration_num}_performance.log")


def get_validation_special_performance_file(run: CalibrationRun,
                                            validation_type: Literal[ValidationType.VALID_BEST, ValidationType.VALID_CONTROL]) -> str:
    validation_type_str = validation_type.value.split('_')[1].lower()
    return os.path.join(get_output_validation_run_dir(run), f"ngen-cal_validation_{validation_type_str}_performance.log")


def get_validation_metrics_valid_best_file(run: CalibrationRun) -> str:
    return os.path.join(get_output_validation_run_dir(run), f"{run.gage.gage_id}_metrics_valid_best.csv")


def get_validation_control_input_file(run: CalibrationRun) -> str:
    return os.path.join(get_output_validation_run_dir(run), f"{run.gage.gage_id}_config_valid_control.yaml")


def get_validation_control_stdout_file(run: CalibrationRun) -> str:
    return os.path.join(get_output_validation_run_dir(run), 'ngen-cal_validation_control_stdout.log')


def get_validation_metrics_valid_control_file(run: CalibrationRun) -> str:
    return os.path.join(get_output_validation_run_dir(run), f"{run.gage.gage_id}_metrics_valid_control.csv")


def get_validation_metrics_nwm_retrospective_file(run: CalibrationRun) -> str:
    return os.path.join(get_output_validation_run_dir(run), f"{run.gage.gage_id}_metrics_nwm_retro.csv")


def get_validation_iteration_stdout_file(run: CalibrationRun, worker_name: str, iteration_num: int) -> str:
    return os.path.join(get_worker_path(run, worker_name), f"ngen-cal_validation_{worker_name}_iter{iteration_num}_stdout.log")


def get_validation_metrics_valid_iteration_file(run: CalibrationRun, worker_name: str, iteration_num: int) -> str:
    return os.path.join(get_output_validation_run_dir(run), f"{run.gage.gage_id}_metrics_valid_{worker_name}_iter{iteration_num}.csv")
