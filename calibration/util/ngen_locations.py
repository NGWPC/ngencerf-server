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
         PET_LIB := os.path.join(settings.NGEN_REPO_ROOT, 'extern/pet/cmake_build/libpetbmi.so'),
         SNOW17_LIB := os.path.join(settings.NGEN_REPO_ROOT, 'extern/snow17/cmake_build/libsnow17bmi.so'),
         SAC_LIB := os.path.join(settings.NGEN_REPO_ROOT, 'extern/sac-sma/cmake_build/libsacbmi.so'),

         CALIBRATION_PY := os.path.join(CALIB_VALID_DIR, 'calibration.py'),
         VALIDATION_PY := os.path.join(CALIB_VALID_DIR, 'validation.py')]


# Construct the directory where the Input/Output is
def get_gage_dir(run: CalibrationRun) -> str | bytes:
    return os.path.join(run.job_data_dir,
                        f'{run.objective_function.name.lower()}_{run.optimization.name.lower()}',
                        run.ngen_formulation_name, run.gage.gage_id)


def get_realization_file(run: CalibrationRun) -> str:
    return os.path.join(get_gage_dir(run), f'{run.gage.gage_id}_realization_config_bmi_calib.json')


def get_forcing_filename_pattern():
    return r"^cat-\d+\.csv$"


# Job-specific forcing directory
def get_forcing_dir_for_job(run: CalibrationRun) -> str:
    return os.path.join(run.job_data_dir, 'forcing')


# Job-specific observation directory
def get_observational_dir_for_job(run: CalibrationRun) -> str:
    return os.path.join(run.job_data_dir, 'observation')


def get_observational_filename(run: CalibrationRun):
    return f'{run.gage.gage_id}_hourly_discharge.csv'


# Job-specific observation file
def get_observational_file_for_job(run: CalibrationRun) -> str:
    return os.path.join(get_observational_dir_for_job(run), get_observational_filename(run)) if run.gage else None


# TODO This is temporary while we are allowing uploading of Geopackage files
# Job-specific geopackage directory
def get_geopackage_dir_for_job(run: CalibrationRun) -> str:
    return os.path.join(run.job_data_dir, 'geopackage')


def get_geopackage_filename(run: CalibrationRun):
    return f'gauge_{run.gage.gage_id}.gpkg'


def get_geopackage_file_for_job(run: CalibrationRun) -> str:
    return os.path.join(get_geopackage_dir_for_job(run), get_geopackage_filename(run)) if run.gage else None


def get_input_dir(run: CalibrationRun) -> str:
    return os.path.join(get_gage_dir(run), 'Input')


def get_output_dir(run: CalibrationRun) -> str:
    return os.path.join(get_gage_dir(run), 'Output')


def get_output_calibration_run_dir(run: CalibrationRun) -> str:
    return os.path.join(get_output_dir(run), 'Calibration_Run')


def get_output_validation_run_dir(run: CalibrationRun) -> str:
    return os.path.join(get_output_dir(run), 'Validation_Run')


def get_worker_path(run: CalibrationRun, worker_name) -> str:
    return os.path.join(get_output_calibration_run_dir(run), worker_name)


def get_metrics_iteration_file(run: CalibrationRun, worker_name) -> str:
    return os.path.join(get_worker_path(run, worker_name), f'{run.gage.gage_id}_metrics_iteration.csv')


def get_params_iteration_file(run: CalibrationRun, worker_name) -> str:
    return os.path.join(get_worker_path(run, worker_name), f'{run.gage.gage_id}_params_iteration.csv')


def get_objective_log_best_file(run: CalibrationRun, worker_name) -> str:
    return os.path.join(get_worker_path(run, worker_name), f'{run.gage.gage_id}_objective_log.txt')


def get_calibration_stdout_file(run: CalibrationRun) -> str:
    return os.path.join(get_output_calibration_run_dir(run), 'ngen-cal_calibration_stdout.log')


def get_global_best_params_file(run: CalibrationRun) -> str:
    return os.path.join(get_output_calibration_run_dir(run), f'{run.gage.gage_id}_global_best_params.csv')


def get_validation_control_stdout_file(run: CalibrationRun) -> str:
    return os.path.join(get_output_validation_run_dir(run), 'ngen-cal_validation_control_stdout.log')


def get_validation_best_stdout_file(run: CalibrationRun) -> str:
    return os.path.join(get_output_validation_run_dir(run), 'ngen-cal_validation_best_stdout.log')


def get_calibration_input_file(run: CalibrationRun) -> str:
    return os.path.join(get_input_dir(run), f'{run.gage.gage_id}_config_calib.yaml')


def get_validation_control_input_file(run: CalibrationRun) -> str:
    return os.path.join(get_output_validation_run_dir(run), f'{run.gage.gage_id}_config_valid_control.yaml')


def get_validation_best_input_file(run: CalibrationRun) -> str:
    return os.path.join(get_output_validation_run_dir(run), f'{run.gage.gage_id}_config_valid_best.yaml')
