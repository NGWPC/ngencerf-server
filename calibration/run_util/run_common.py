import logging
import os
import subprocess
from datetime import datetime, timezone
from typing import Dict

from createInput import create_input
from django.conf import settings
from django.db import transaction

from calibration.enums import StatusEnum, ValidationType
from calibration.models import CalibrationRun, ValidationRun, Iteration
from calibration.util.ngen_locations import get_calibration_input_file, get_validation_best_stdout_file, get_validation_control_stdout_file, \
    get_calibration_stdout_file, get_validation_best_input_file, get_validation_control_input_file, get_validation_iteration_stdout_file
from calibration.views import ngen_cal_input
from calibration.views.common import ResponseError, CerfException, create_validation_run_internal
from calibration.views.read_output import read_validation_output
from cerfServer.settings import EnvironmentEnum

logger = logging.getLogger(__name__)

# Store future and process objects by job id
# Need to change this to a compound key.  Either calibration_id or calibration_id#validation_id
job_registry: Dict[tuple[int, int | None], subprocess.Popen] = {}


def set_job_status(run: CalibrationRun | ValidationRun, status: StatusEnum):
    """Set the status for the CalibrationRun and save it."""
    run.status = StatusEnum.from_enum(status)
    # Doesn't hurt to always update slurm_job_id, even though we only care in PW environment
    run.slurm_job_id = None
    run.save(update_fields=['status', 'slurm_job_id'])
    if settings.NGEN_ENVIRONMENT == EnvironmentEnum.LOCAL:
        key = get_job_registry_key(run)
        job_registry.pop(key, None)


def execute_job(run, input_file, output_file, job_type="calibration"):
    if settings.NGEN_ENVIRONMENT == EnvironmentEnum.LOCAL:
        if job_type == "calibration":
            from calibration.run_util.run_ngen_cal_local import run_calibration_job_local
            run_calibration_job_local(run, input_file, output_file)
        else:
            from calibration.run_util.run_ngen_cal_local import run_validation_job_local
            run_validation_job_local(run, input_file, output_file)
    elif settings.NGEN_ENVIRONMENT == EnvironmentEnum.PARALLEL_WORKS:
        if job_type == "calibration":
            from calibration.run_util.run_ngen_cal_pw import run_calibration_job_parallel_works
            run_calibration_job_parallel_works(run, input_file, output_file)
        else:
            from calibration.run_util.run_ngen_cal_pw import run_validation_job_parallel_works
            run_validation_job_parallel_works(run, input_file, output_file)
    else:
        raise CerfException(f"Unsupported environment: {settings.NGEN_ENVIRONMENT}")


def run_calibration_job(calibration_run: CalibrationRun):
    """
    Start the execution of a calibration job by retrieving the input/output file paths
    and delegating the job to either a local or Docker execution environment.
    :param calibration_run: The CalibrationRun object representing the job run.
    """
    input_file = get_calibration_input_file(calibration_run)
    if not os.path.exists(input_file):
        raise CerfException(
            f"Input file '{input_file}' does not exist for Calibration Run {calibration_run.id}, user: {calibration_run.owner.username}")

    output_file = get_calibration_stdout_file(calibration_run)

    execute_job(calibration_run, input_file, output_file, job_type="calibration")


def run_validation_job(validation_run: ValidationRun):
    """
    Start the execution of a validation job
    and delegating the job to either a local or Docker execution environment.
    :param validation_run: The ValidationRun object representing the job run.
    """
    if validation_run.validation_type == ValidationType.VALID_BEST.value:
        input_file = get_validation_best_input_file(validation_run.calibration_run)
        output_file = get_validation_best_stdout_file(validation_run.calibration_run)
    elif validation_run.validation_type == ValidationType.VALID_CONTROL.value:
        input_file = get_validation_control_input_file(validation_run.calibration_run)
        output_file = get_validation_control_stdout_file(validation_run.calibration_run)
    else:
        # Regular validation
        input_file = get_calibration_input_file(validation_run.calibration_run)
        output_file = get_validation_iteration_stdout_file(validation_run.calibration_run, validation_run.worker_name, validation_run.iteration_num)

    if not os.path.exists(input_file):
        raise CerfException(
            f"Input file '{input_file}' does not exist for Validation Run {validation_run.id}, user: {validation_run.calibration_run.owner.username}, type: {validation_run.validation_type}")

    execute_job(validation_run, input_file, output_file, job_type="validation")


def cancel_job_common(run_id):
    from calibration.run_util.run_ngen_cal_local import cancel_local_job
    from calibration.run_util.run_ngen_cal_pw import cancel_slurm_job
    if settings.NGEN_ENVIRONMENT == EnvironmentEnum.LOCAL:
        return cancel_local_job(run_id)
    else:
        return cancel_slurm_job(run_id)


def submit_job(run: CalibrationRun | ValidationRun, job_execution_fn):
    """
    Handle the common submission process for both calibration and validation jobs.
    :param run: The CalibrationRun or ValidationRun object.
    :param job_execution_fn: The function responsible for executing the job.
    """
    with transaction.atomic():
        run.run_date = datetime.now(timezone.utc)
        run.status = StatusEnum.from_enum(StatusEnum.RUNNING)
        run.save(update_fields=['run_date', 'status'])

        job_execution_fn(run)

    return None


def submit_calibration_job(calibration_run: CalibrationRun, config_file=None):
    # If config is passed, then don't need to validate
    if not config_file:
        messages, config_file = ngen_cal_input.ready_to_run(calibration_run, build=True)

        if messages:
            return ResponseError(f'Calibration Run {calibration_run.id} is not ready', validation_errors=messages)

    try:
        logger.info(f'Running create_input for Calibration Run {calibration_run.id}')
        create_input(config_file)
    except Exception as e:
        logger.exception(f'Exception from create_input - {str(e)}')
        return ResponseError(f'Exception from create_input - {str(e)}')

    logger.info(f'Return from create_input for Calibration Run {calibration_run.id}')

    submit_job(calibration_run, job_execution_fn=run_calibration_job)

    return None


def submit_validation_job(validation_run: ValidationRun):
    submit_job(validation_run,  job_execution_fn=run_validation_job)

    return None


def get_job_registry_key(run: CalibrationRun | ValidationRun):
    """
    Generate a key for the job registry using calibration_run_id and validation_run_id.
    :param run: The CalibrationRun or ValidationRun object.
    :return: A tuple representing the job key.
    """
    calibration_run_id = run.id if isinstance(run, CalibrationRun) else run.calibration_run.id
    validation_run_id = run.id if isinstance(run, ValidationRun) else None
    return calibration_run_id, validation_run_id


def create_and_submit_validation_control(calibration_run: CalibrationRun):
    """
    Create a validation run of type VALID_CONTROL and submit it.
    :param calibration_run: The CalibrationRun object.
    """
    validation_run = create_validation_run_internal(calibration_run, None, validation_type=ValidationType.VALID_CONTROL)
    submit_validation_job(validation_run)


def process_validation_output_and_maybe_create_best(validation_run: ValidationRun):
    """
    Process the validation output and create a new VALID_BEST run if the validation type is VALID_CONTROL.
    :param validation_run: The ValidationRun object representing the job run.
    """
    # Process the validation output
    read_validation_output(validation_run)
    set_job_status(validation_run, StatusEnum.DONE)

    # If we just ran Validation Control, see if we want to run Validation Best
    if validation_run.validation_type == ValidationType.VALID_CONTROL.value:
        if validation_run.calibration_run.automatic_validation:
            new_validation_run = create_validation_run_internal(validation_run.calibration_run, None,
                                                                validation_type=ValidationType.VALID_BEST)
            # Set the iteration containing the best values before we run it
            iteration = Iteration.objects.filter(calibration_run=validation_run.calibration_run, best_params=True).get()
            validation_run.iteration = iteration
            validation_run.save(update_fields=['iteration'])
            submit_validation_job(new_validation_run)


def submit_job_execution(run, input_file, output_file, job_type, submit_fn):
    """
    Common job execution logic for submitting calibration and validation jobs.
    Handles both local and Slurm-based job execution.

    :param run: The CalibrationRun or ValidationRun object.
    :param input_file: The input file path.
    :param output_file: The output file path.
    :param job_type: The type of job ("calibration" or "validation").
    :param submit_fn: The function that will handle environment-specific submission logic.
    """
    if settings.NGEN_ENVIRONMENT == EnvironmentEnum.LOCAL:
        if job_type == "calibration":
            submit_fn(run, input_file, output_file, "local_calibration")
        else:
            submit_fn(run, input_file, output_file, "local_validation")
    elif settings.NGEN_ENVIRONMENT == EnvironmentEnum.PARALLEL_WORKS:
        if job_type == "calibration":
            submit_fn(run, input_file, output_file, "slurm_calibration")
        else:
            submit_fn(run, input_file, output_file, "slurm_validation")
    else:
        raise CerfException(f"Unsupported environment: {settings.NGEN_ENVIRONMENT}")
