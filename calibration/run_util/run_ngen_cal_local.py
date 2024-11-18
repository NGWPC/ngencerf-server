import functools
import logging
import subprocess
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable, List

from django.conf import settings

from calibration.enums import StatusEnum, ValidationType
from calibration.models import CalibrationRun, ValidationRun
from calibration.run_util.run_common import set_job_status, job_registry, get_job_registry_key, create_and_submit_validation_control, \
    process_validation_output_and_maybe_create_best
from calibration.views.common import get_job_description
from calibration.views.read_output import read_calibration_output
from cerfServer.settings import NGEN_CAL_VENV, NGEN_ENVIRONMENT, NgenEnvironmentEnum, DOCKER_CMD

logger = logging.getLogger(__name__)

# Create a global thread pool that will be reused across multiple execute() calls
pool = ThreadPoolExecutor()


def run_job_local(run: CalibrationRun | ValidationRun, input_file: str, output_file: str, script_cmd: str,
                  callback_function: Callable[[CalibrationRun | ValidationRun, Future], None]) -> None:
    """
    Executes a local job by calling the shell script
    with appropriate input and output file arguments, and registering a callback for job end.

    :param run: The CalibrationRun or ValidationRun object representing the job run.
    :param input_file: Path to the input file.
    :param output_file: Path to the output file.
    :param script_cmd: The script cmd to run (e.g., 'calibration', 'validation', 'validation_iteration').
    :param callback_function: The callback function to invoke when the process completes.
    """
    # Construct the shell script path
    if NGEN_ENVIRONMENT == NgenEnvironmentEnum.LOCAL:
        spawn_command = [settings.RUN_NGEN_CAL_SCRIPT]
        extra = [output_file, NGEN_CAL_VENV]
    elif NGEN_ENVIRONMENT == NgenEnvironmentEnum.DOCKER:
        spawn_command = DOCKER_CMD.split()
        # Don't need venv for Docker
        extra = [output_file]
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
    Executes a local calibration job by preparing the required arguments and invoking the run_job_local function.

    :param calibration_run: The CalibrationRun object representing the job run.
    :param input_file: Path to the input file.
    :param output_file: Path to the output file.
    """
    run_job_local(calibration_run, input_file, output_file, "calibration", run_calibration_job_callback_local)


def run_validation_job_local(validation_run: ValidationRun, input_file: str, output_file: str) -> None:
    """
    Executes a local validation job by preparing the required arguments and invoking the run_job_local function.

    :param validation_run: The ValidationRun object representing the job run.
    :param input_file: Path to the input file.
    :param output_file: Path to the output file.
    """
    script_type = 'validation_iteration' if validation_run.validation_type == ValidationType.VALID_ITERATION.value else 'validation'
    run_job_local(validation_run, input_file, output_file, script_type, run_validation_job_callback_local)


def run_job_callback_common(run: CalibrationRun | ValidationRun, future: Future) -> bool:
    """
    Common logic for the callback function that gets executed when a job completes.

    :param run: The CalibrationRun or ValidationRun object representing the job run.
    :param future: The Future object representing the asynchronous job process.
    :return: A boolean indicating whether the job completed successfully.
    """
    job_description = get_job_description(run)

    logger.info(f'Job end callback received for {job_description}')
    run.run_end = datetime.now(timezone.utc)
    run.save(update_fields=['run_end'])

    try:
        if future.exception() is not None:
            logger.error(f"Exception occurred in {job_description}: {future.exception()}")
            set_job_status(run, StatusEnum.FAILED)
            return False

        exit_code = future.result()
        logger.info(
            f"{job_description} completed with exit code {exit_code}")
        if exit_code == -15:
            logger.info(f'{job_description} was cancelled')
            set_job_status(run, StatusEnum.CANCELLED)
            return False
        elif exit_code != 0:
            logger.error(
                f'{job_description} ending due to abnormal return code')
            set_job_status(run, StatusEnum.FAILED)
            return False
        return True
    except Exception as e:
        logger.exception(f"Error in callback for {job_description}: {str(e)}")
        set_job_status(run, StatusEnum.FAILED)
        return False


def run_calibration_job_callback_local(calibration_run: CalibrationRun, future: Future) -> None:
    """
    Callback function that gets executed when a calibration job completes.

    :param calibration_run: The CalibrationRun object representing the job run.
    :param future: The Future object representing the asynchronous job process.
    """
    if run_job_callback_common(calibration_run, future):
        read_calibration_output(calibration_run)
        set_job_status(calibration_run, StatusEnum.DONE)
        # Always submit a control run
        create_and_submit_validation_control(calibration_run)


def run_validation_job_callback_local(validation_run: ValidationRun, future: Future) -> None:
    """
    Callback function that gets executed when a validation job completes.

    :param validation_run: The ValidationRun object representing the job run.
    :param future: The Future object representing the asynchronous job process.
    """
    if run_job_callback_common(validation_run, future):
        process_validation_output_and_maybe_create_best(validation_run)


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


def cancel_local_job(run: CalibrationRun | ValidationRun):
    """
    Terminates a job with the given calibration_run_id by killing the associated process.
    :param run: The CalibrationRun to terminate.
    """
    job_description = get_job_description(run)

    logger.info(f"Cancelling {job_description}")

    key = get_job_registry_key(run)
    process = job_registry.get(key)

    if process:
        process.terminate()  # Gracefully terminates the process

        logger.info(f"{job_description} has been terminated.")
        return True
    else:
        logger.warning(f"No running job found for {job_description}")
        return False
