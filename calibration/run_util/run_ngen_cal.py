import functools
import logging
import subprocess
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from calibration.enums import StatusEnum
from calibration.models import CalibrationRun
from calibration.util.ngen_locations import CALIBRATION_PY, VALIDATION_PY
from cerfServer import settings
from cerfServer.settings import NGEN_CAL_VENV
from calibration.run_util.run_common import JobStage, set_job_status, job_registry, proceed_to_next_stage

logger = logging.getLogger(__name__)


def run_local(run: CalibrationRun, stage: JobStage, input_file, output_file):
    """
    Executes a local job for either CALIBRATION or VALIDATION stages by calling the shell script
    with appropriate input and output file arguments, and registering a callback for job stage transitions.
    :param run: The CalibrationRun object representing the job run.
    :param stage: The current job stage.
    :param input_file: Path to the input file for the stage.
    :param output_file: Path to the output file for the stage.
    """
    simulate = getattr(settings, 'NGEN_CAL_SIMULATE', False)
    cal_or_valid_script = CALIBRATION_PY if stage == JobStage.CALIBRATION else VALIDATION_PY
    cal_or_valid_script = str(Path(settings.BASE_DIR) / 'calibration' / 'run_util' / 'ngen_cal_simulation.py') if simulate else cal_or_valid_script

    shell_script = str(Path(settings.BASE_DIR) / 'calibration' / 'run_util' / 'run_ngen_cal.sh')

    # Prepare the argument list to pass to the shell script
    args_to_calibrate_or_validate = [input_file]
    args = [shell_script, NGEN_CAL_VENV, output_file, cal_or_valid_script] + args_to_calibrate_or_validate

    # Bind the callback function for the job stage transition
    job_callback = functools.partial(run_job_callback_local, stage, run.automatic_validation, run)

    execute(run, stage, args, callback_function=job_callback)


def run_job_callback_local(current_stage: JobStage, do_validation: bool, run: CalibrationRun, future: Future):
    """
    Callback function that gets executed when a job stage completes. It handles job stage transitions, including
    moving to the next stage (if validation is enabled) or finishing the job.
    :param current_stage: The current job stage.
    :param do_validation: Boolean flag indicating if validation stages should follow.
    :param run: The CalibrationRun object representing the job run.
    :param future: The Future object representing the asynchronous job process.
    """
    process_id = Path(run.job_data_dir).name
    logger.info(f'Job {process_id} completed stage {current_stage}')

    try:
        if future.exception() is not None:
            logger.error(f"Exception occurred in process {process_id} at stage {current_stage.name}: {future.exception()}")
            set_job_status(run, StatusEnum.FAILED)
            return

        exit_code = future.result()
        logger.info(f"Process {process_id}, stage {current_stage.name}, completed with exit code {exit_code}")
        if exit_code == -15:
            logger.info(f'Job {process_id} was cancelled')
            set_job_status(run, StatusEnum.CANCELLED)

        elif exit_code != 0:
            logger.error(f'Job {process_id} ending due to abnormal return code')
            set_job_status(run, StatusEnum.FAILED)
        else:
            proceed_to_next_stage(run, current_stage, do_validation)
    except Exception as e:
        logger.error(f"Error in callback for process {process_id} at stage {current_stage.name}: {str(e)}")
        set_job_status(run, StatusEnum.FAILED)


# Create a global thread pool that will be reused across multiple execute() calls
pool = ThreadPoolExecutor()


def execute(run: CalibrationRun, current_stage, args, callback_function):
    """
    Spawn a process to run the run_ngen_cal.sh script which will call the appropriate Python script (Calibration or Validation).
    See https://stackoverflow.com/questions/28866651/python-concurrent-futures-using-subprocess-with-a-callback
    Also see https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.Future

    This function handles process execution and registers the callback for when the process completes.
    :param run: The CalibrationRun object representing the job run.
    :param current_stage: The current job stage.
    :param args: The argument list to pass to the shell script.
    :param callback_function: The callback function to invoke when the process completes.
    """
    process_id = Path(run.job_data_dir).name

    logger.info(f"Spawning process: {process_id} in stage {current_stage.name} with {args}")
    try:
        process = subprocess.Popen(args)
        future = pool.submit(process.wait)

        # Register job for future reference
        job_registry[run.id] = process

        future.add_done_callback(callback_function)
    except Exception as e:
        logger.error(f"Failed to execute command: {str(e)}")
        raise
    logger.info(f'Process {process_id} in stage {current_stage.name} is running in the background')


def cancel_local_job(run: CalibrationRun):
    """
    Terminates a job with the given calibration_run_id by killing the associated process.
    :param run: The CalibrationRun to terminate.
    """
    process = job_registry.get(run.id)

    if process:
        process.terminate()  # Gracefully terminates the process
        logger.info(f"Job {run.id} has been terminated.")
        return True
    else:
        logger.warning(f"No running job found for Calibration Run: {run.id}")
        return False
