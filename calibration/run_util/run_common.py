import subprocess
from enum import auto, Enum
from pathlib import Path
from typing import Optional, Dict

from calibration.enums import StatusEnum
from calibration.models import CalibrationRun
from calibration.util.ngen_locations import get_calibration_input_file, get_validation_best_stdout_file, get_validation_control_stdout_file, \
    get_calibration_stdout_file, get_validation_best_input_file, get_validation_control_input_file
from calibration.views.common import CerfException
from calibration.views.read_output import read_output
from cerfServer import settings


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

# Store future and process objects by job id
job_registry: Dict[int, subprocess.Popen] = {}


# TODO Need 2 versions of this, or an argument
def set_job_status(run: CalibrationRun, status: StatusEnum):
    """Set the status for the CalibrationRun and save it."""
    run.status = StatusEnum.from_enum(status)
    run.save(update_fields=['status'])
    job_registry.pop(run.id, None)


def proceed_to_next_stage(run: CalibrationRun, current_stage: JobStage, do_validation: bool):
    """Handle the logic to proceed to the next stage of the job."""
    process_id = Path(run.job_data_dir).name
    transition_manager = JobStageTransitionManager(validation_enabled=do_validation)
    next_stage = transition_manager.get_next_stage(current_stage)

    if next_stage:
        print(f'Job {process_id} proceeding to stage {next_stage}')
        run_job(run, next_stage)
    else:
        print(f'Job {process_id} complete. No further stages.')
        set_job_status(run, StatusEnum.DONE)

        read_output(run)


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
    match settings.NGEN_ENVIRONMENT:
        case settings.NGEN_ENVIRONMENT.LOCAL:
            from calibration.run_util.run_ngen_cal import run_local
            run_local(run, cmd, input_file, output_file)
        case settings.NGEN_ENVIRONMENT.PARALLEL_WORKS:
            from calibration.run_util.run_ngen_cal_docker import run_parallel_works
            run_parallel_works(run, cmd, input_file, output_file)
