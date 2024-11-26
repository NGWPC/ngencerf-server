import functools
import logging
import subprocess
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, List

from django.conf import settings

from calibration.enums import StatusEnum, ValidationType
from calibration.models import CalibrationRun, ValidationRun, ForecastRun
from calibration.models.forecast_forcing_download_run import ForecastForcingDownloadRun
from calibration.run_util.run_common import set_job_status, job_registry, get_job_registry_key, run_generic_job_callback, \
    finalize_calibration_after_callback, \
    finalize_validation_after_callback, finalize_forecast_after_callback, finalize_forecast_forcing_download_after_callback
from calibration.views.common import get_job_description
from cerfServer.settings import NGEN_CAL_VENV, NGEN_ENVIRONMENT, NgenEnvironmentEnum, DOCKER_CMD

logger = logging.getLogger(__name__)

# Create a global thread pool that will be reused across multiple execute() calls
pool: ThreadPoolExecutor = ThreadPoolExecutor()


def run_job_local(run: CalibrationRun | ValidationRun | ForecastRun | ForecastForcingDownloadRun, input_file: str, output_file: str, script_cmd: str,
                  callback_function: Callable[[CalibrationRun | ValidationRun | ForecastRun | ForecastForcingDownloadRun, Future], None]) -> None:
    """
    Executes a local job by calling the shell script with appropriate input and output file arguments,
    and registers a callback for job completion.

    :param run: The CalibrationRun, ValidationRun, or ForecastRun object representing the job run.
    :param input_file: Path to the input file.
    :param output_file: Path to the output file.
    :param script_cmd: The script command to execute (e.g., 'calibration', 'validation').
    :param callback_function: The callback function to invoke when the process completes.
    """
    # Construct the shell script path based on the execution environment
    if NGEN_ENVIRONMENT == NgenEnvironmentEnum.LOCAL:
        spawn_command = [settings.RUN_NGEN_CAL_SCRIPT]
        extra = [output_file, NGEN_CAL_VENV]
    elif NGEN_ENVIRONMENT == NgenEnvironmentEnum.DOCKER:
        spawn_command = DOCKER_CMD.split()
        extra = [output_file]  # Venv not required for Docker
    else:
        spawn_command = []
        extra = []

    # Prepare the argument list to pass to the shell script
    args_to_run = [input_file]
    if isinstance(run, ValidationRun) and run.validation_type == ValidationType.VALID_ITERATION.value:
        args_to_run += [run.worker_name, str(run.iteration_num)]

    args = spawn_command + [script_cmd] + args_to_run + extra

    # Bind the callback function for job
    job_callback = functools.partial(callback_function, run)

    # Execute the job
    logger.info(f'Running command: {args}')
    execute_job(run, args, callback_function=job_callback)


def run_calibration_job_local(calibration_run: CalibrationRun, input_file: str, output_file: str) -> None:
    """
    Executes a local calibration job by invoking run_job_local with appropriate arguments.

    :param calibration_run: The CalibrationRun object representing the job run.
    :param input_file: Path to the input file.
    :param output_file: Path to the output file.
    """
    run_job_local(calibration_run, input_file, output_file, "calibration", run_calibration_job_callback_local)


def run_validation_job_local(validation_run: ValidationRun, input_file: str, output_file: str) -> None:
    """
    Executes a local validation job by invoking run_job_local with appropriate arguments.

    :param validation_run: The ValidationRun object representing the validation job.
    :param input_file: Path to the input file.
    :param output_file: Path to the output file.
    """
    script_type = 'validation_iteration' if validation_run.validation_type == ValidationType.VALID_ITERATION.value else 'validation'
    run_job_local(validation_run, input_file, output_file, script_type, run_validation_job_callback_local)


def run_forecast_job_local(forecast_run: ForecastRun, input_file: str, output_file: str) -> None:
    """
    Executes a local forecast job by invoking run_job_local with appropriate arguments.

    :param forecast_run: The ForecastRun object representing the job run.
    :param input_file: Path to the input file.
    :param output_file: Path to the output file.
    """
    run_job_local(forecast_run, input_file, output_file, 'forecast', run_forecast_job_callback_local)


def run_forecast_forcing_download_job_local(forecast_forcing_download_run: ForecastForcingDownloadRun, input_file: str, output_file: str) -> None:
    """
    Executes a local forecast job by invoking run_job_local with appropriate arguments.

    :param forecast_forcing_download_run: The ForecastRun object representing the job run.
    :param input_file: Path to the input file.
    :param output_file: Path to the output file.
    """
    run_job_local(forecast_forcing_download_run, input_file, output_file, 'forecast_forcing', run_forecast_forcing_download_job_callback_local)


def check_local_status(run: CalibrationRun | ValidationRun | ForecastRun, future: Future) -> bool:
    """
    Checks the status of a locally executed job and updates its status accordingly.

    :param run: The job object (CalibrationRun, ValidationRun, or ForecastRun) being monitored.
    :param future: The Future object representing the asynchronous process.
    :return: True if the job completed successfully, False otherwise.
    """
    try:
        if future.exception() is not None:
            logger.error(f"Exception occurred in {get_job_description(run)}: {future.exception()}")
            set_job_status(run, StatusEnum.FAILED)
            return False

        exit_code = future.result()
        if exit_code == -15:
            logger.info(f"{get_job_description(run)} was cancelled")
            set_job_status(run, StatusEnum.CANCELLED)
            return False
        elif exit_code != 0:
            logger.error(f"{get_job_description(run)} ending due to abnormal return code")
            set_job_status(run, StatusEnum.FAILED)
            return False
        return True
    except Exception as e:
        logger.exception(f"Error in callback for {get_job_description(run)}: {str(e)}")
        set_job_status(run, StatusEnum.FAILED)
        return False


# Local callbacks
# These callbacks are used to handle job completion events for Calibration, Validation, and Forecast jobs
# executed in a local environment. They wrap the `run_generic_job_callback` function, providing
# environment-specific status checks (`check_local_status`) and job-specific finalization functions.

# Handles the completion of a calibration job in the local environment.
# - Uses `check_local_status` to validate the job's exit code.
# - Executes `finalize_calibration` to read job output, mark the job as DONE, and possibly create validation runs.
run_calibration_job_callback_local = functools.partial(
    run_generic_job_callback, job_callback_func=check_local_status, finalize_func=finalize_calibration_after_callback
)

# Handles the completion of a validation job in the local environment.
# - Uses `check_local_status` to validate the job's exit code.
# - Executes `finalize_validation` to process validation results and potentially mark the best validation run.
run_validation_job_callback_local = functools.partial(
    run_generic_job_callback, job_callback_func=check_local_status, finalize_func=finalize_validation_after_callback
)

# Handles the completion of a forecast job in the local environment.
# - Uses `check_local_status` to validate the job's exit code.
# - Executes `finalize_forecast` to finalize the forecast job and mark it as DONE.
run_forecast_job_callback_local = functools.partial(
    run_generic_job_callback, job_callback_func=check_local_status, finalize_func=finalize_forecast_after_callback
)

# Handles the completion of a forecast job in the local environment.
# - Uses `check_local_status` to validate the job's exit code.
# - Executes `finalize_forecast` to finalize the forecast job and mark it as DONE.
run_forecast_forcing_download_job_callback_local = functools.partial(
    run_generic_job_callback, job_callback_func=check_local_status, finalize_func=finalize_forecast_forcing_download_after_callback
)


def execute_job(run: CalibrationRun | ValidationRun, args: List[str], callback_function: Callable[[Future], None]) -> None:
    """
    Spawn a process to run the run-ngen-cal.sh script which will call the appropriate Python script (Calibration or Validation).

    This function handles process execution and registers the callback for when the process completes.

    :param run: The CalibrationRun or ValidationRun object representing the job run.
    :param args: The argument list to pass to the shell script.
    :param callback_function: The callback function to invoke when the process completes.
    """
    job_description = get_job_description(run)

    logger.info(f"Spawning process: {job_description} with {args}")

    try:
        # Start the subprocess with the provided arguments
        process = subprocess.Popen(args)

        # Submit the process to the thread pool executor
        future = pool.submit(process.wait)

        # Register the job for future reference
        job_registry[get_job_registry_key(run)] = process

        # Add a callback to be invoked when the process completes
        future.add_done_callback(callback_function)
    except Exception as e:
        logger.error(f"Failed to execute command: {str(e)}")
        raise
    logger.info(
        f'{job_description} is running in the background')


def cancel_local_job(run: CalibrationRun | ValidationRun | ForecastRun) -> bool:
    """
    Cancel a running local job by terminating the associated process.

    :param run: The CalibrationRun, ValidationRun, or ForecastRun object to cancel.
    :return: True if the job was successfully terminated, False otherwise.
    """
    job_description = get_job_description(run)

    logger.info(f"Cancelling {job_description}")

    if isinstance(run, ForecastRun):
        # Special handling.  If we are downloading the forcing data, then we need to send a cancel request to the Forcing server
        pass

    key = get_job_registry_key(run)
    process = job_registry.get(key)

    if process:
        process.terminate()  # Gracefully terminates the process

        logger.info(f"{job_description} has been terminated.")
        return True
    else:
        logger.warning(f"No running job found for {job_description}")
        return False
