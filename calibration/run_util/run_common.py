import logging
import subprocess
from pathlib import Path
from typing import Optional, Dict

from django.conf import settings

from calibration.enums import StatusEnum, JobStage
from calibration.models import CalibrationRun, ValidationRun
from calibration.util.ngen_locations import get_calibration_input_file, get_validation_best_stdout_file, get_validation_control_stdout_file, \
    get_calibration_stdout_file, get_validation_best_input_file, get_validation_control_input_file, get_validation_iteration_input_file, \
    get_validation_iteration_stdout_file
from calibration.views.common import CerfException
from calibration.views.read_output import read_calibration_output
from cerfServer.settings import EnvironmentEnum

logger = logging.getLogger(__name__)


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
        Internal method to initialize the job stage transitions with or without validation_best stages.
        """
        self._transitions_no_validation = {
            JobStage.CALIBRATION: None,
            JobStage.VALIDATION_CONTROL: None  # End of the state machine

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
calibration_file_funcs = {
    JobStage.CALIBRATION: (get_calibration_input_file, get_calibration_stdout_file),
    JobStage.VALIDATION_CONTROL: (get_validation_control_input_file, get_validation_control_stdout_file),
    JobStage.VALIDATION_BEST: (get_validation_best_input_file, get_validation_best_stdout_file),
}

validation_file_funcs = get_validation_iteration_input_file, get_validation_iteration_stdout_file

# Store future and process objects by job id
# Need to change this to a compound key.  Either calibration_id or calibration_id#validation_id
job_registry: Dict[int, subprocess.Popen] = {}


def set_job_status(run: CalibrationRun | ValidationRun, status: StatusEnum):
    """Set the status for the CalibrationRun and save it."""
    run.status = StatusEnum.from_enum(status)
    # Doesn't hurt to always update slurm_job_id, even though we only care in PW environment
    run.slurm_job_id = None
    run.save(update_fields=['status', 'slurm_job_id'])
    if settings.NGEN_ENVIRONMENT == EnvironmentEnum.LOCAL:
        job_registry.pop(run.id, None)


def proceed_to_next_stage(calibration_run: CalibrationRun, current_stage: JobStage):
    """
    Handle the logic to proceed to the next stage of the job.
    Only a CalibrationRun has multiple states (calibration, validation control and optionally, validation best
    :param calibration_run: CalibrationRun
    :param current_stage: current stage
    """
    try:
        logger.info(f'Calling read_output for stage {current_stage}')
        read_calibration_output(calibration_run, current_stage)
    except CerfException as e:
        logger.error(f'Exception while running read_output for job {calibration_run.id} in stage {current_stage} - {str(e)}')
        raise

    process_id = Path(calibration_run.job_data_dir).name
    transition_manager = JobStageTransitionManager(validation_enabled=calibration_run.automatic_validation)
    next_stage = transition_manager.get_next_stage(current_stage)

    if next_stage:
        logger.info(f'Job {process_id} proceeding to stage {next_stage}')
        run_calibration_job(calibration_run, next_stage)
    else:
        logger.info(f'Job {process_id} complete. No further stages.')
        set_job_status(calibration_run, StatusEnum.DONE)


def run_calibration_job(calibration_run: CalibrationRun, stage: JobStage):
    """
    Start the execution of a calibration job at a specific stage by retrieving the input/output file paths
    and delegating the job to either a local or Docker execution environment.
    :param calibration_run: The CalibrationRun object representing the job run.
    :param stage: The current job stage.
    """
    # Retrieve the input and output file functions as a tuple from the dictionary
    file_funcs_tuple = calibration_file_funcs.get(stage)

    if file_funcs_tuple is None:
        raise CerfException(f"Unsupported stage: {stage}")

    # Unpack and call the functions to get input/output file paths
    input_file_func, output_file_func = file_funcs_tuple
    input_file = input_file_func(calibration_run)
    output_file = output_file_func(calibration_run)

    # Run the job locally or in Docker
    match settings.NGEN_ENVIRONMENT:
        case settings.NGEN_ENVIRONMENT.LOCAL:
            from calibration.run_util.run_ngen_cal_local import run_calibration_job_local
            run_calibration_job_local(calibration_run, stage, input_file, output_file)
        case settings.NGEN_ENVIRONMENT.PARALLEL_WORKS:
            from calibration.run_util.run_ngen_cal_pw import run_calibration_job_parallel_works
            run_calibration_job_parallel_works(calibration_run, stage, input_file, output_file)


def run_validation_job(validation_run: ValidationRun, worker_name: str, iteration: int):
    """
    Start the execution of a validation job
    and delegating the job to either a local or Docker execution environment.
    :param validation_run: The ValidationRun object representing the job run.
    :param worker_name: Worker name which contains the parameters we want to use
    :param iteration: Iteration which contains the parameters we want to use
    """

    # Unpack and call the functions to get input/output file paths
    input_file_func, output_file_func = validation_file_funcs
    input_file = input_file_func(validation_run.calibration_run, worker_name, iteration)
    output_file = output_file_func(validation_run.calibration_run, worker_name, iteration)

    # Run the job locally or in Docker
    match settings.NGEN_ENVIRONMENT:
        case settings.NGEN_ENVIRONMENT.LOCAL:
            from calibration.run_util.run_ngen_cal_local import run_validation_job_local
            run_validation_job_local(validation_run, input_file, output_file, worker_name, iteration)
        case settings.NGEN_ENVIRONMENT.PARALLEL_WORKS:
            from calibration.run_util.run_ngen_cal_pw import run_validation_job_parallel_works
            run_validation_job_parallel_works(validation_run, input_file, output_file, worker_name, iteration)


def cancel_job_common(run_id):
    from calibration.run_util.run_ngen_cal_local import cancel_local_job
    from calibration.run_util.run_ngen_cal_pw import cancel_slurm_job
    if settings.NGEN_ENVIRONMENT == EnvironmentEnum.LOCAL:
        return cancel_local_job(run_id)
    else:
        return cancel_slurm_job(run_id)
