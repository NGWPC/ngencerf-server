import functools
import os
import subprocess
from concurrent.futures import Future, ThreadPoolExecutor
from enum import auto, Enum
from typing import Optional, Dict

from calibration.enums import StatusEnum
from calibration.models import CalibrationRun
from calibration.util.ngen_locations import CALIBRATION_PY, VALIDATION_PY, get_calibration_input_file, \
    get_calibration_stdout_file, get_validation_control_stdout_file, get_validation_best_input_file, get_validation_control_input_file, \
    get_validation_best_stdout_file
from calibration.views.common import CerfException
from cerfServer import settings
from cerfServer.settings import NGEN_CAL_VENV

# Store future and process objects by job id
job_registry: Dict[int, subprocess.Popen] = {}


class JobStage(Enum):
    """
     Enum representing the stages of a job.
     """
    CALIBRATION = auto()
    VALIDATION_CONTROL = auto()
    VALIDATION_BEST = auto()


class JobStageTransitionManager:
    """
     Manages transitions between job stages, controlling whether validation stages are included or not. It determines the next stage
     for a job based on the current stage and whether validation is enabled.
     """

    def __init__(self, validation_enabled: bool):
        """
        Initialize the JobStageTransitionManager with validation rules.
        :param validation_enabled: Boolean flag indicating if validation stages should be included.
        """
        self.validation_enabled = validation_enabled
        self._initialize_transitions()

    def _initialize_transitions(self):
        """
        Internal method to initialize the job stage transitions with or without validation stages.
        """
        self._transitions_no_validation = {
            JobStage.CALIBRATION: None  # End of the state machine
        }

        self._transitions_with_validation = {
            JobStage.CALIBRATION: JobStage.VALIDATION_CONTROL,
            JobStage.VALIDATION_CONTROL: JobStage.VALIDATION_BEST,
            JobStage.VALIDATION_BEST: None  # End of the state machine
        }

    def get_next_stage(self, current_stage: JobStage) -> Optional[JobStage]:
        """
        Determine the next stage based on the current stage and whether validation is enabled.
        :param current_stage: The current job stage.
        :return: The next job stage, or None if it's the final stage.
        """
        transitions = (self._transitions_with_validation
                       if self.validation_enabled else self._transitions_no_validation)

        return transitions.get(current_stage)


# Map the cmd values to the corresponding functions
file_funcs = {
    JobStage.CALIBRATION: (get_calibration_input_file, get_calibration_stdout_file),
    JobStage.VALIDATION_CONTROL: (get_validation_control_input_file, get_validation_control_stdout_file),
    JobStage.VALIDATION_BEST: (get_validation_best_input_file, get_validation_best_stdout_file)
}


def run_job(run: CalibrationRun, cmd: JobStage):
    """
    Start the execution of a job at a specific stage by retrieving the input/output file paths
    and delegating the job to either a local or Docker execution environment.
    :param run: The CalibrationRun object representing the job run.
    :param cmd: The current job stage.
    """
    # Retrieve the input and output file functions as a tuple from the dictionary
    file_funcs_tuple = file_funcs.get(cmd)

    if file_funcs_tuple is None:
        raise CerfException(f"Unsupported command: {cmd}")

    # Unpack and call the functions to get input/output file paths
    input_file_func, output_file_func = file_funcs_tuple
    input_file = input_file_func(run)
    output_file = output_file_func(run)

    run.status = StatusEnum.from_enum(StatusEnum.RUNNING)

    # Run the job locally or in Docker (Docker is currently unsupported)
    match settings.RUN_TYPE:
        case settings.RUN_TYPE.LOCAL:
            run_local(run, cmd, input_file, output_file)
        case settings.RUN_TYPE.DOCKER:
            raise Exception('Docker not supported')


def run_local(run: CalibrationRun, stage: JobStage, input_file, output_file):
    """
    Executes a local job for either CALIBRATION or VALIDATION stages by calling the shell script
    with appropriate input and output file arguments, and registering a callback for job stage transitions.
    :param run: The CalibrationRun object representing the job run.
    :param stage: The current job stage.
    :param input_file: Path to the input file for the stage.
    :param output_file: Path to the output file for the stage.
    """
    cal_or_valid_script = CALIBRATION_PY if stage == JobStage.CALIBRATION else VALIDATION_PY
    cal_or_valid_script = os.path.join(settings.BASE_DIR, 'run_ngen_cal', 'hello_world.py') if settings.NGEN_CAL_SIMULATE else cal_or_valid_script

    shell_script = os.path.join(settings.BASE_DIR, 'run_ngen_cal', 'run_ngen_cal.sh')

    # Prepare the argument list to pass to the shell script
    args_to_calibrate_or_validate = [input_file]
    args = [shell_script, NGEN_CAL_VENV, output_file, cal_or_valid_script] + args_to_calibrate_or_validate

    # Bind the callback function for the job stage transition
    job_callback = functools.partial(job_stage_callback, stage, run.automatic_validation, run)

    execute(run, stage, args, callback_function=job_callback)


def run_docker(run: CalibrationRun, cmd, input_file):
    """
    Placeholder for Docker execution. Currently not supported.
    :param run: The CalibrationRun object.
    :param cmd: The job command.
    :param input_file: Input file path.
    """
    pass


def job_stage_callback(current_stage: JobStage, do_validation: bool, run: CalibrationRun, future: Future):
    """
    Callback function that gets executed when a job stage completes. It handles job stage transitions, including
    moving to the next stage (if validation is enabled) or finishing the job.
    :param current_stage: The current job stage.
    :param do_validation: Boolean flag indicating if validation stages should follow.
    :param run: The CalibrationRun object representing the job run.
    :param future: The Future object representing the asynchronous job process.
    """
    process_id = os.path.basename(run.job_data_dir)
    print(f'Job {process_id} completed stage {current_stage}')

    error = False
    cancelled = False
    try:
        if future.exception() is not None:
            print(f"Exception occurred in process {process_id} at stage {current_stage.name}: {future.exception()}")
        else:
            exit_code = future.result()
            print(f"Process {process_id}, stage {current_stage.name}, completed with exit code {exit_code}")
            error = exit_code != 0
            cancelled = exit_code == -15
    except Exception as e:
        print(f"Error in callback for process {process_id} at stage {current_stage.name}: {str(e)}")
        return

    # Remove the job from the job registry when it completes
    job_registry.pop(run.id, None)

    if cancelled:
        print(f'Job {process_id} was cancelled')
        return
    elif error:
        print(f'Job {process_id} ending due to abnormal return code')
        return

    # Create a transition manager for the current job, depending on whether validation is enabled
    transition_manager = JobStageTransitionManager(validation_enabled=do_validation)

    # Determine the next stage
    next_stage = transition_manager.get_next_stage(current_stage)

    if next_stage:
        print(f'Job {process_id} proceeding to stage {next_stage}')
        run_job(run, next_stage)
    else:
        print(f'Job {process_id} complete. No further stages.')


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
    process_id = os.path.basename(run.job_data_dir)

    print(f"Spawning process: {process_id} in stage {current_stage.name} with {args}")
    try:
        process = subprocess.Popen(args)
        future = pool.submit(process.wait)

        # Register job for future reference
        job_registry[run.id] = process

        future.add_done_callback(callback_function)
    except Exception as e:
        print(f"Failed to execute command: {str(e)}")
        raise
    print(f'Process {process_id} in stage {current_stage.name} is running in the background')


def terminate_job(calibration_run_id: int):
    """
    Terminates a job with the given calibration_run_id by killing the associated process.
    :param calibration_run_id: The id of the CalibrationRun to terminate.
    """
    process = job_registry.get(calibration_run_id)

    if process:
        process.terminate()  # Gracefully terminates the process
        print(f"Job {calibration_run_id} has been terminated.")
        return True
    else:
        print(f"No running job found for Calibration Run: {calibration_run_id}")
        return False


def force_kill_job(calibration_run_id: int):
    """
    Forcefully kills a job with the given calibration_run_id by sending a SIGKILL signal to the associated process.
    :param calibration_run_id: The id of the CalibrationRun to kill.
    """
    process = job_registry.get(calibration_run_id)

    if process:
        process.kill()  # Forcefully kills the process
        print(f"Job {calibration_run_id} has been forcefully killed.")
        return True
    else:
        print(f"No running job found for Calibration Run: {calibration_run_id}")
        return False
