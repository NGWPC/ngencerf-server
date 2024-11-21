import logging
import os
import subprocess
from datetime import datetime, timezone
from typing import Dict, Callable

from createInput import create_input
from django.conf import settings
from django.db import transaction

from calibration.enums import StatusEnum, ValidationType
from calibration.models import CalibrationRun, ValidationRun, Iteration, ForecastRun
from calibration.util.ngen_locations import get_calibration_input_file, get_validation_best_stdout_file, get_validation_control_stdout_file, \
    get_calibration_stdout_file, get_validation_best_input_file, get_validation_control_input_file, get_validation_iteration_stdout_file
from calibration.views import ngen_cal_input
from calibration.views.common import ResponseError, CerfException, create_validation_run_internal
from calibration.views.read_output import read_validation_output
from cerfServer.settings import NgenEnvironmentEnum

logger = logging.getLogger(__name__)

# Job registry to store subprocess objects keyed by a tuple of (calibration_run_id, validation_run_id)
job_registry: Dict[tuple[int, int], subprocess.Popen] = {}


def set_job_status(run: CalibrationRun | ValidationRun, status: StatusEnum) -> None:
    """
    Update the status of a CalibrationRun or ValidationRun and clear the job registry if applicable.

    :param run: The CalibrationRun or ValidationRun object.
    :param status: The new status to set.
    """
    run.status = status.db_instance
    # Doesn't hurt to always update slurm_job_id, even though we only care in PW environment
    run.slurm_job_id = None
    run.save(update_fields=['status', 'slurm_job_id'])
    if settings.NGEN_ENVIRONMENT in [NgenEnvironmentEnum.LOCAL, NgenEnvironmentEnum.DOCKER]:
        key = get_job_registry_key(run)
        job_registry.pop(key, None)


def execute_job(run: CalibrationRun | ValidationRun | ForecastRun, input_file: str, output_file: str, job_type: str) -> None:
    """
    Execute a job based on the configured NGEN environment.

    :param run: The CalibrationRun or ValidationRun object.
    :param input_file: The input file path.
    :param output_file: The output file path.
    :param job_type: Type of the job ("calibration" or "validation").
    :raises CerfException: If the environment is unsupported.
    """
    if settings.NGEN_ENVIRONMENT in [NgenEnvironmentEnum.LOCAL, NgenEnvironmentEnum.DOCKER]:
        if job_type == "calibration":
            from calibration.run_util.run_ngen_cal_local import run_calibration_job_local
            run_calibration_job_local(run, input_file, output_file)
        elif job_type == "validation":
            from calibration.run_util.run_ngen_cal_local import run_validation_job_local
            run_validation_job_local(run, input_file, output_file)
        else:
            # Forecast run
            pass
    elif settings.NGEN_ENVIRONMENT == NgenEnvironmentEnum.PARALLEL_WORKS:
        if job_type == "calibration":
            from calibration.run_util.run_ngen_cal_pw import run_calibration_job_parallel_works
            run_calibration_job_parallel_works(run, run.owner, input_file, output_file)
        elif job_type == "validation":
            from calibration.run_util.run_ngen_cal_pw import run_validation_job_parallel_works
            run_validation_job_parallel_works(run, run.calibration_run.owner, input_file, output_file)
        else:
            # Forecast run
            pass
    else:
        raise CerfException(f"Unsupported environment: {settings.NGEN_ENVIRONMENT}")


def cancel_job_common(run: CalibrationRun | ValidationRun | ForecastRun) -> bool:
    """
    Cancel a job using the appropriate environment-specific logic.

    :param run: The CalibrationRun or ValidationRun object.
    """
    from calibration.run_util.run_ngen_cal_local import cancel_local_job
    from calibration.run_util.run_ngen_cal_pw import cancel_slurm_job
    if settings.NGEN_ENVIRONMENT in [NgenEnvironmentEnum.LOCAL, NgenEnvironmentEnum.DOCKER]:
        return cancel_local_job(run)
    else:
        return cancel_slurm_job(run)


def run_calibration_job(calibration_run: CalibrationRun) -> None:
    """
    Start a calibration job by determining input and output file paths
    and delegating the job to either a local or Docker execution environment.

    This callable is intended to be used as an input to submit_job

    :param calibration_run: The CalibrationRun object representing the job.
    """
    input_file = get_calibration_input_file(calibration_run)
    if not os.path.exists(input_file):
        raise CerfException(
            f"Input file '{input_file}' does not exist for Calibration Job {calibration_run.id}, user: {calibration_run.owner.username}")

    output_file = get_calibration_stdout_file(calibration_run)

    execute_job(calibration_run, input_file, output_file, job_type="calibration")


def run_validation_job(validation_run: ValidationRun) -> None:
    """
    Start a validation job by determining input and output file paths
    and delegating the job to either a local or Docker execution environment.

    This callable is intended to be used as an input to submit_job


    :param validation_run: The ValidationRun object representing the job.
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
            f"Input file '{input_file}' does not exist for Validation Job {validation_run.id}, user: {validation_run.calibration_run.owner.username}, type: {validation_run.validation_type}")

    execute_job(validation_run, input_file, output_file, job_type="validation")


def run_forecast_job(forecast_run: ForecastRun) -> None:
    """
    Start a forecast job by determining input and output file paths
    and delegating the job to either a local or Docker execution environment.

    This callable is intended to be used as an input to submit_job


    :param forecast_run: The ForecastRun object representing the job.
    """

    # execute_job(forecast_run, input_file, output_file, job_type="forecast")
    pass


def submit_job(run: CalibrationRun | ValidationRun | ForecastRun, job_execution_fn: Callable[[CalibrationRun | ValidationRun | ForecastRun], None]) -> None:
    """
    Submit a job after setting initial status and submission date.

    :param run: The CalibrationRun or ValidationRun object.
    :param job_execution_fn: The function to execute the job.
    """
    with transaction.atomic():
        run.submit_date = datetime.now(timezone.utc)
        run.status = StatusEnum.RUNNING.db_instance
        run.save(update_fields=['submit_date', 'status'])

        job_execution_fn(run)


def submit_calibration_job(calibration_run: CalibrationRun, config_file=None):
    # If config is passed, then don't need to validate
    if not config_file:
        messages, config_file = ngen_cal_input.ready_to_run(calibration_run, build=True)

        if messages:
            return ResponseError(f'Calibration Job {calibration_run.id} is not ready', validation_errors=messages)

    try:
        logger.info(f'Running create_input for Calibration Job {calibration_run.id}')
        create_input(config_file)
    except Exception as e:
        CalibrationRun.objects.filter(id=calibration_run.id).update(status=StatusEnum.FAILED.db_instance)
        logger.exception(f'Exception from create_input - {str(e)}')
        return ResponseError(f'Exception from create_input - {str(e)}')

    logger.info(f'Return from create_input for Calibration Job {calibration_run.id}')

    submit_job(calibration_run, job_execution_fn=run_calibration_job)

    return None


def submit_validation_job(validation_run: ValidationRun):
    submit_job(validation_run, job_execution_fn=run_validation_job)

    return None


def submit_forecast_job(forecast_run: ForecastRun) -> None:
    """
    Submit a forecast job for execution.

    :param forecast_run: The ForecastRun object to submit.
    """

    # TODO Forecast jobs work slightly differently from other jobs.
    # If it's a new job, we submit a request to the forcing server first with it's own callback.
    # After we get the data from the forcing server, we call submit_job similar to the other jobs
    if not forecast_run.have_forcing_data:
        # get forcing data
        # I think we need another status.  And need to figure out how to deal with submit data
        forecast_run.submit_date = datetime.now(timezone.utc)
        forecast_run.status = StatusEnum.RUNNING.db_instance
        forecast_run.save(update_fields=['submit_date', 'status'])
    else:
        submit_job(forecast_run, job_execution_fn=run_forecast_job)

    return None


def get_job_registry_key(run: CalibrationRun | ValidationRun | ForecastRun) -> tuple[int, int]:
    """
    Generate a unique key for the job registry based on run type.

    The first element is always the calibration run ID.
    The second element is the specific run ID or -1 for CalibrationRun.

    :param run: The CalibrationRun, ValidationRun, or ForecastRun object.
    :return: A tuple (calibration_run_id, specific_run_id).
    """
    if isinstance(run, CalibrationRun):
        return run.id, -1
    elif isinstance(run, ValidationRun) or isinstance(run, ForecastRun):
        return run.calibration_run.id, run.id




def create_and_submit_validation_control(calibration_run: CalibrationRun) -> None:
    """
    Create a validation run of type VALID_CONTROL and submit it.

    :param calibration_run: The CalibrationRun object for which the validation control run is created.
    """
    validation_run = create_validation_run_internal(calibration_run, None, validation_type=ValidationType.VALID_CONTROL)
    submit_validation_job(validation_run)


def process_validation_output_and_maybe_create_best(validation_run: ValidationRun) -> None:
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
            best_validation_run = create_validation_run_internal(validation_run.calibration_run, None,
                                                                 validation_type=ValidationType.VALID_BEST)
            # Set the iteration containing the best values before we run it
            iteration = Iteration.objects.filter(calibration_run=validation_run.calibration_run, best_params=True).get()
            best_validation_run.iteration = iteration
            best_validation_run.save(update_fields=['iteration'])
            submit_validation_job(best_validation_run)


def submit_job_execution(
        run: CalibrationRun | ValidationRun,
        input_file: str,
        output_file: str,
        job_type: str,
        submit_fn: Callable[[CalibrationRun | ValidationRun, str, str, str], None]
) -> None:
    """
    Common job execution logic for submitting calibration and validation jobs.
    Handles both local and Slurm-based job execution.

    :param run: The CalibrationRun or ValidationRun object to execute.
    :param input_file: The input file path for the job.
    :param output_file: The output file path for the job.
    :param job_type: The type of job ("calibration" or "validation").
    :param submit_fn: The function that handles the submission logic for the specific environment.
    :raises CerfException: If the environment is unsupported.
    """
    if settings.NGEN_ENVIRONMENT in [NgenEnvironmentEnum.LOCAL, NgenEnvironmentEnum.DOCKER]:
        if job_type == "calibration":
            submit_fn(run, input_file, output_file, "local_calibration")
        else:
            submit_fn(run, input_file, output_file, "local_validation")
    elif settings.NGEN_ENVIRONMENT == NgenEnvironmentEnum.PARALLEL_WORKS:
        if job_type == "calibration":
            submit_fn(run, input_file, output_file, "slurm_calibration")
        else:
            submit_fn(run, input_file, output_file, "slurm_validation")
    else:
        raise CerfException(f"Unsupported environment: {settings.NGEN_ENVIRONMENT}")
