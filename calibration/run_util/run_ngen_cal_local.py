import functools
import logging
import subprocess
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from django.conf import settings

from calibration.enums import StatusEnum, ValidationType
from calibration.models import CalibrationRun, ValidationRun
from calibration.run_util.run_common import set_job_status, job_registry, get_job_registry_key, create_and_submit_validation_control, \
    process_validation_output_and_maybe_create_best
from calibration.util.ngen_locations import CALIBRATION_PY, VALIDATION_PY, VALIDATION_ITERATION_PY
from calibration.views.read_output import read_calibration_output
from cerfServer.settings import NGEN_CAL_VENV

logger = logging.getLogger(__name__)


def run_calibration_job_local(calibration_run: CalibrationRun, input_file, output_file):
    """
    Executes a local calibration job by calling the shell script
    with appropriate input and output file arguments, and registering a callback for job end.
    :param calibration_run: The CalibrationRun object representing the job run.
    :param input_file: Path to the input file.
    :param output_file: Path to the output file.
    """
    simulate = getattr(settings, 'NGEN_CAL_SIMULATE', False)
    cal_or_valid_script = str(Path(settings.BASE_DIR) / 'calibration' / 'run_util' / 'ngen_cal_simulation.py') if simulate else CALIBRATION_PY

    shell_script = str(Path(settings.BASE_DIR) / 'calibration' / 'run_util' / 'run_ngen_cal.sh')

    # Prepare the argument list to pass to the shell script
    args_to_calibrate_or_validate = [input_file]
    args = [shell_script, NGEN_CAL_VENV, output_file, cal_or_valid_script] + args_to_calibrate_or_validate

    # Bind the callback function for job
    job_callback = functools.partial(run_calibration_job_callback_local, calibration_run)

    execute_calibration_job(calibration_run, args, callback_function=job_callback)


def run_validation_job_local(validation_run: ValidationRun, input_file, output_file):
    """
    Executes a local validation by calling the shell script
    with appropriate input and output file arguments, and registering a callback for job end.
    run_best is a special case which runs validation.py with the 'best' input file created by calibration
    If run_base is false, we call validation_iteration.py to run a validation using a specific iteration
    :param validation_run: The ValidationRun object representing the job run.
    :param input_file: Path to the input file.
    :param output_file: Path to the output file.
    """
    simulate = getattr(settings, 'NGEN_CAL_SIMULATE', False)

    validation_script = VALIDATION_ITERATION_PY if validation_run.validation_type == ValidationType.VALID_ITERATION else VALIDATION_PY

    validation_script = str(Path(settings.BASE_DIR) / 'calibration' / 'run_util' / 'ngen_cal_simulation.py') if simulate else validation_script

    shell_script = str(Path(settings.BASE_DIR) / 'calibration' / 'run_util' / 'run_ngen_cal.sh')

    # Prepare the argument list to pass to the shell script
    args_to_validate = [input_file, validation_run.worker_name,
                        str(validation_run.iteration_num)] if validation_run.validation_type == ValidationType.VALID_ITERATION else [input_file]
    args = [shell_script, NGEN_CAL_VENV, output_file, validation_script] + args_to_validate

    # Bind the callback function for the job
    job_callback = functools.partial(run_validation_job_callback_local, validation_run)

    execute_validation_job(validation_run, args, callback_function=job_callback)


def run_calibration_job_callback_local(calibration_run: CalibrationRun, future: Future):
    """
    Callback function that gets executed when a job completes.
    :param calibration_run: The CalibrationRun object representing the job run.
    :param future: The Future object representing the asynchronous job process.
    """
    logger.info(f'Job end callback received for Calibration Job {calibration_run.id}/{calibration_run.owner.username}')

    try:
        if future.exception() is not None:
            logger.error(f"Exception occurred in Calibration Job {calibration_run.id}/{calibration_run.owner.username}: {future.exception()}")
            set_job_status(calibration_run, StatusEnum.FAILED)
            return

        exit_code = future.result()
        logger.info(f"Calibration Job {calibration_run.id}/{calibration_run.owner.username}, completed with exit code {exit_code}")
        if exit_code == -15:
            logger.info(f'Calibration Job {calibration_run.id} was cancelled')
            set_job_status(calibration_run, StatusEnum.CANCELLED)

        elif exit_code != 0:
            logger.error(f'Calibration Job {calibration_run.id}/{calibration_run.owner.username} ending due to abnormal return code')
            set_job_status(calibration_run, StatusEnum.FAILED)
        else:
            read_calibration_output(calibration_run)
            set_job_status(calibration_run, StatusEnum.DONE)
            # Always submit a control run
            create_and_submit_validation_control(calibration_run)
    except Exception as e:
        logger.exception(f"Error in callback for Calibration Job {calibration_run.id}: {str(e)}")
        set_job_status(calibration_run, StatusEnum.FAILED)


def run_validation_job_callback_local(validation_run: ValidationRun, future: Future):
    """
    Callback function that gets executed when validation job completes.
    :param validation_run: The CalibrationRun object representing the job run.
    :param future: The Future object representing the asynchronous job process.
    """
    # process_id = Path(validation_run.calibration_run.job_data_dir).name
    logger.info(
        f'Job end callback received for Validation Job {validation_run.id}/{validation_run.calibration_run.owner.username}, type: {validation_run.validation_type}')

    try:
        if future.exception() is not None:
            logger.error(
                f"Exception occurred in Validation Job {validation_run.id}/{validation_run.calibration_run.owner.username}: {future.exception()}")
            set_job_status(validation_run, StatusEnum.FAILED)
            return

        exit_code = future.result()
        logger.info(f"Validation Job {validation_run.id}/{validation_run.calibration_run.owner.username} completed with exit code {exit_code}")
        if exit_code == -15:
            logger.info(f'Validation Job {validation_run.id}/{validation_run.calibration_run.owner.username} was cancelled')
            set_job_status(validation_run, StatusEnum.CANCELLED)

        elif exit_code != 0:
            logger.error(f'Validation Job {validation_run.id}/{validation_run.calibration_run.owner.username} ending due to abnormal return code')
            set_job_status(validation_run, StatusEnum.FAILED)
        else:
            process_validation_output_and_maybe_create_best(validation_run)
    except Exception as e:
        logger.exception(f"Error in callback for Validation Job {validation_run.id}/{validation_run.calibration_run.owner.username}: {str(e)}")
        set_job_status(validation_run, StatusEnum.FAILED)


# Create a global thread pool that will be reused across multiple execute() calls
pool = ThreadPoolExecutor()


def execute_calibration_job(calibration_run: CalibrationRun, args, callback_function):
    """
    Spawn a process to run the run_ngen_cal.sh script which will call the appropriate Python script (Calibration or Validation).
    See https://stackoverflow.com/questions/28866651/python-concurrent-futures-using-subprocess-with-a-callback
    Also see https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.Future

    This function handles process execution and registers the callback for when the process completes.
    :param calibration_run: The CalibrationRun object representing the job run.
    :param args: The argument list to pass to the shell script.
    :param callback_function: The callback function to invoke when the process completes.
    """
    logger.info(f"Spawning process: Calibration Job {calibration_run.id}/{calibration_run.owner.username} with {args}")
    try:
        process = subprocess.Popen(args)
        future = pool.submit(process.wait)

        # Register job for future reference
        job_registry[get_job_registry_key(calibration_run)] = process

        future.add_done_callback(callback_function)
    except Exception as e:
        logger.error(f"Failed to execute command: {str(e)}")
        raise
    logger.info(f'Process Calibration Job {calibration_run.id}/{calibration_run.owner.username} is running in the background')


def execute_validation_job(validation_run: ValidationRun, args, callback_function):
    """
    Spawn a process to run the run_ngen_cal.sh script which will call the appropriate Python script (Calibration or Validation).
    See https://stackoverflow.com/questions/28866651/python-concurrent-futures-using-subprocess-with-a-callback
    Also see https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.Future

    This function handles process execution and registers the callback for when the process completes.
    :param validation_run: The CalibrationRun object representing the job run.
    :param args: The argument list to pass to the shell script.
    :param callback_function: The callback function to invoke when the process completes.
    """
    logger.info(f"Spawning process: Validation Job {validation_run.id}/{validation_run.calibration_run.owner.username} with {args}")
    try:
        process = subprocess.Popen(args)
        future = pool.submit(process.wait)

        # Register job for future reference
        job_registry[get_job_registry_key(validation_run)] = process

        future.add_done_callback(callback_function)
    except Exception as e:
        logger.error(f"Failed to execute command: {str(e)}")
        raise
    logger.info(
        f'Process Validation Job {validation_run.id}/{validation_run.calibration_run.owner.username}, type: {validation_run.validation_type} is running in the background')


def cancel_local_job(run: CalibrationRun | ValidationRun):
    """
    Terminates a job with the given calibration_run_id by killing the associated process.
    :param run: The CalibrationRun to terminate.
    """
    is_calibration = isinstance(run, CalibrationRun)

    run_id = run.id if is_calibration else run.calibration_run.id
    logger.info(f"Cancelling {'Calibration' if is_calibration else 'Validation'} Run {run_id}")

    key = get_job_registry_key(run)
    process = job_registry.get(key)

    if process:
        process.terminate()  # Gracefully terminates the process
        logger.info(f"Job {run.id} has been terminated.")
        return True
    else:
        logger.warning(f"No running job found for Calibration Run: {run.id}")
        return False
