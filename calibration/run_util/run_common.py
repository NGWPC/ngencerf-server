import logging
import os
import subprocess
from concurrent.futures import Future
from datetime import datetime, timezone
from typing import Dict, Callable

from createInput import create_input
from django.conf import settings
from django.db import transaction
from rest_framework.response import Response

from calibration.enums import StatusEnum, ValidationType, SlurmStatusEnum
from calibration.models import CalibrationRun, ValidationRun, Iteration, ForecastRun
from calibration.models.base_run import BaseRun
from calibration.models.forecast_forcing_download_run import ForecastForcingDownloadRun
from calibration.util.ngen_locations import get_calibration_input_file, get_validation_best_stdout_file, get_validation_control_stdout_file, \
    get_calibration_stdout_file, get_validation_best_input_file, get_validation_control_input_file, get_validation_iteration_stdout_file
from calibration.views import ngen_cal_input
from calibration.views.common import ResponseError, CerfException, create_validation_run_internal, get_job_description
from calibration.views.end_of_job_processing import read_validation_output, read_calibration_output
from cerfServer.settings import NgenEnvironmentEnum

logger = logging.getLogger(__name__)

# Job registry to store subprocess objects keyed by a tuple of (calibration_run_id, validation_run_id)
job_registry: Dict[tuple[int, int], subprocess.Popen] = {}


def set_job_status(run: BaseRun, status: StatusEnum) -> None:
    """
    Update the status of a CalibrationRun, ValidationRun, or ForecastRun and clear the job registry if applicable.

    :param run: The CalibrationRun, ValidationRun, or ForecastRun object.
    :param status: The new status to set.
    """
    run.status = status.db_instance
    # Doesn't hurt to always update slurm_job_id, even though we only care in PW environment
    run.slurm_job_id = None
    run.save(update_fields=['status', 'slurm_job_id'])
    if settings.NGEN_ENVIRONMENT in [NgenEnvironmentEnum.LOCAL, NgenEnvironmentEnum.DOCKER]:
        key = get_job_registry_key(run)
        job_registry.pop(key, None)


def get_run_owner(run: BaseRun):
    """
    Retrieve the owner of a BaseRun object.

    :param run: The BaseRun object (CalibrationRun, ValidationRun, etc.).
    :return: The owner of the associated CalibrationRun or the run itself.
    :raises AttributeError: If the owner cannot be determined.
    """
    if hasattr(run, 'owner'):  # CalibrationRun case
        return run.owner
    elif hasattr(run, 'calibration_run'):  # ValidationRun, ForecastRun
        return run.calibration_run.owner
    elif hasattr(run, 'forecast_run') and hasattr(run.forecast_run, 'calibration_run'):  # ForecastForcingDownloadRun
        return run.forecast_run.calibration_run.owner
    raise AttributeError(f"Cannot determine owner for run of type {type(run).__name__}")


def execute_job(run: BaseRun, input_file: str, output_file: str) -> None:
    """
    Execute a job based on the configured NGEN environment.

    :param run: The BaseRun object (CalibrationRun, ValidationRun, etc.).
    :param input_file: The input file path.
    :param output_file: The output file path.
    :raises CerfException: If the environment is unsupported.
    """
    if settings.NGEN_ENVIRONMENT in [NgenEnvironmentEnum.LOCAL, NgenEnvironmentEnum.DOCKER]:
        from calibration.run_util.run_ngen_cal_local import run_job_local
        run_job_local(run, input_file, output_file)
    elif settings.NGEN_ENVIRONMENT == NgenEnvironmentEnum.PARALLEL_WORKS:
        from calibration.run_util.run_ngen_cal_pw import submit_job_to_slurm
        # Resolve owner dynamically for the Slurm submission
        try:
            owner = get_run_owner(run)  # Use the utility function
        except AttributeError as e:
            raise CerfException(f"Error retrieving owner for run {run.id}: {str(e)}")
        submit_job_to_slurm(run, owner, input_file, output_file)
    else:
        raise CerfException(f"Unsupported environment: {settings.NGEN_ENVIRONMENT}")


def cancel_job_common(run: BaseRun) -> bool:
    """
    Cancel a job using the appropriate environment-specific logic.

    This function handles job cancellation for LOCAL, DOCKER, and PARALLEL_WORKS environments.

    :param run: The CalibrationRun, ValidationRun, or ForecastRun object.
    :return: True if the job was successfully canceled; False otherwise.
    """
    if settings.NGEN_ENVIRONMENT in [NgenEnvironmentEnum.LOCAL, NgenEnvironmentEnum.DOCKER]:
        from calibration.run_util.run_ngen_cal_local import cancel_local_job
        return cancel_local_job(run)
    elif settings.NGEN_ENVIRONMENT == NgenEnvironmentEnum.PARALLEL_WORKS:
        from calibration.run_util.run_ngen_cal_pw import cancel_slurm_job
        return cancel_slurm_job(run)
    else:
        logger.error(f"Unsupported environment: {settings.NGEN_ENVIRONMENT}")
        return False


def run_calibration_job(calibration_run: CalibrationRun) -> None:
    """
    Start a calibration job by determining input and output file paths.

    This function is intended to be passed as an argument to `submit_job`
    and not called directly.

    :param calibration_run: The CalibrationRun object representing the job.
    """
    input_file = get_calibration_input_file(calibration_run)
    if not os.path.exists(input_file):
        raise CerfException(
            f"Input file '{input_file}' does not exist for Calibration Job {calibration_run.id}, user: {calibration_run.owner.username}")

    output_file = get_calibration_stdout_file(calibration_run)

    execute_job(calibration_run, input_file, output_file)


def run_validation_job(validation_run: ValidationRun) -> None:
    """
    Start a validation job by determining input and output file paths.

    This function is intended to be passed as an argument to `submit_job`
    and not called directly.

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

    execute_job(validation_run, input_file, output_file)


def run_forecast_job(forecast_run: ForecastRun) -> None:
    """
    Start a forecast job by determining input and output file paths.

    This function is intended to be passed as an argument to `submit_job`
    and not called directly.

    :param forecast_run: The ForecastRun object representing the job.
    """
    # input_file = get_calibration_input_file(calibration_run)
    # if not os.path.exists(input_file):
    #     raise CerfException(
    #         f"Input file '{input_file}' does not exist for Calibration Job {calibration_run.id}, user: {calibration_run.owner.username}")
    #
    # output_file = get_calibration_stdout_file(calibration_run)
    input_file = 'dummy'
    output_file = 'dummy'

    execute_job(forecast_run, input_file, output_file)


def run_forecast_forcing_download_job(forecast_forcing_download_run: ForecastForcingDownloadRun) -> None:
    """
    Start a forecast forcing download job by determining input and output file paths.

    This function is intended to be passed as an argument to `submit_job`
    and not called directly.

    :param forecast_forcing_download_run: The ForecastForcingDownloadRun object representing the job.
    """
    # input_file = get_calibration_input_file(calibration_run)
    # if not os.path.exists(input_file):
    #     raise CerfException(
    #         f"Input file '{input_file}' does not exist for Calibration Job {calibration_run.id}, user: {calibration_run.owner.username}")
    #
    # output_file = get_calibration_stdout_file(calibration_run)
    input_file = 'dummy'
    output_file = 'dummy'

    execute_job(forecast_forcing_download_run, input_file, output_file)


def submit_job(run: BaseRun, config_file=None) -> Response | None:
    """
    Submit a job after setting initial status and submission date.

    The specific job execution function is determined based on the job type
    and executed accordingly.

    Handles special preparation logic for calibration jobs internally
    before delegating execution to the appropriate job function.

    :param run: The BaseRun object (CalibrationRun, ValidationRun, etc.) to submit.
    :param config_file: Optional configuration file for CalibrationRun preparation.
    :return: A DRF Response instance if there is an issue; otherwise, None on success.
    """
    # Special handling for calibration jobs
    if isinstance(run, CalibrationRun):
        response = prepare_calibration_job(run, config_file)
        if response is not None:
            return response  # Return the error response early

    with transaction.atomic():
        # Set submission date and status
        run.submit_date = datetime.now(timezone.utc)
        run.status = StatusEnum.RUNNING.db_instance
        run.save(update_fields=['submit_date', 'status'])

        # Determine the appropriate job execution function
        if isinstance(run, CalibrationRun):
            run_calibration_job(run)
        elif isinstance(run, ValidationRun):
            run_validation_job(run)
        elif isinstance(run, ForecastRun):
            run_forecast_job(run)
        elif isinstance(run, ForecastForcingDownloadRun):
            run_forecast_forcing_download_job(run)
        else:
            raise CerfException(f"Unsupported run type: {type(run).__name__}")

    logger.info(f"{get_job_description(run)} successfully submitted.")


def prepare_calibration_job(calibration_run: CalibrationRun, config_file=None) -> Response | None:
    """
    Prepare input files and validate readiness for a calibration job.

    This function is called from `submit_job` to handle the special input
    preparation logic for calibration jobs.

    :param calibration_run: The CalibrationRun object to prepare.
    :param config_file: Optional configuration file to use instead of generating one.
    :return: A DRF Response instance if there is an issue; otherwise, None on success.
    """
    # If a config file is passed, validation can be skipped
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
    return None


def get_job_registry_key(run: BaseRun) -> tuple[int, int]:
    """
    Generate a unique key for the job registry based on run type.

    The first element is always the calibration run ID.
    The second element is the specific run ID or -1 for CalibrationRun.

    :param run: The CalibrationRun, ValidationRun, or ForecastRun object.
    :return: A tuple (calibration_run_id, specific_run_id).
    """
    if isinstance(run, CalibrationRun):
        return run.id, -1
    elif isinstance(run, (ValidationRun, ForecastRun)):
        return run.calibration_run.id, run.id
    elif isinstance(run, ForecastForcingDownloadRun):
        return run.forecast_run.calibration_run.id, run.forecast_run.id


def create_and_submit_validation_control(calibration_run: CalibrationRun) -> None:
    """
    Create a validation run of type VALID_CONTROL and submit it.

    :param calibration_run: The CalibrationRun object for which the validation control run is created.
    """
    validation_run = create_validation_run_internal(calibration_run, None, validation_type=ValidationType.VALID_CONTROL)
    submit_job(validation_run)


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
            submit_job(best_validation_run)


# TODO This appears to be unused.  Must have been an partial idea that was never completed
# def submit_job_execution(
#         run: CalibrationRun | ValidationRun,
#         input_file: str,
#         output_file: str,
#         job_type: JobType,
#         submit_fn: Callable[[CalibrationRun | ValidationRun, str, str, str], None]
# ) -> None:
#     """
#     Common job execution logic for submitting calibration and validation jobs.
#     Handles both local and Slurm-based job execution.
#
#     :param run: The CalibrationRun or ValidationRun object to execute.
#     :param input_file: The input file path for the job.
#     :param output_file: The output file path for the job.
#     :param job_type: The type of job ("calibration" or "validation").
#     :param submit_fn: The function that handles the submission logic for the specific environment.
#     :raises CerfException: If the environment is unsupported.
#     """
#     if settings.NGEN_ENVIRONMENT in [NgenEnvironmentEnum.LOCAL, NgenEnvironmentEnum.DOCKER]:
#         if job_type == JobType.CALIBRATION:
#             submit_fn(run, input_file, output_file, "local_calibration")
#         else:
#             submit_fn(run, input_file, output_file, "local_validation")
#     elif settings.NGEN_ENVIRONMENT == NgenEnvironmentEnum.PARALLEL_WORKS:
#         if job_type == JobType.CALIBRATION:
#             submit_fn(run, input_file, output_file, "slurm_calibration")
#         else:
#             submit_fn(run, input_file, output_file, "slurm_validation")
#     else:
#         raise CerfException(f"Unsupported environment: {settings.NGEN_ENVIRONMENT}")


def run_generic_job_callback(
        run: BaseRun,
        status: Future | SlurmStatusEnum,
        job_callback_func: Callable[[BaseRun, Future | SlurmStatusEnum], bool],
        finalize_func: Callable[[BaseRun], None]
) -> None:
    """
    Generic callback function for handling job completion.

    :param run: The job object (CalibrationRun, ValidationRun, or ForecastRun) representing the job.
    :param status: The job's completion status. This can be:
        - A `Future` object (for Local environments)
        - A `SlurmStatusEnum` value (for Parallel Works environments)
    :param job_callback_func: Function to check job status based on the environment.
    :param finalize_func: Function to execute finalization logic specific to the job type.
    """
    job_description = get_job_description(run)
    logger.info(f"Job end callback received for {job_description} with status {status}")
    run.run_end = datetime.now(timezone.utc)
    run.save(update_fields=["run_end"])

    if not job_callback_func(run, status):
        # Stop processing if the job status indicates failure or cancellation
        return

    # Execute finalization logic
    finalize_func(run)


def finalize_calibration_after_callback(run: CalibrationRun) -> None:
    """
    Finalizes a calibration job after it has completed.

    :param run: The CalibrationRun object representing the job.
    - Reads the output data generated by the calibration job and processes it.
    - Marks the calibration job as DONE in the database, indicating successful completion.
    - Creates and submits a validation control job to verify the calibration's results.
    """
    read_calibration_output(run)  # Process and store the output of the calibration job.
    set_job_status(run, StatusEnum.DONE)  # Update the job's status to DONE in the database.
    create_and_submit_validation_control(run)  # Trigger the creation of validation jobs.


def finalize_validation_after_callback(run: ValidationRun) -> None:
    """
    Finalizes a validation job after it has completed.

    :param run: The ValidationRun object representing the validation job.
    - Processes the output of the validation job to evaluate its results.
    - Identifies and marks the best validation run if applicable.
    """
    process_validation_output_and_maybe_create_best(run)  # Process the validation results and handle best-run logic.


def finalize_forecast_after_callback(run: ForecastRun) -> None:
    """
    Finalizes a forecast job after it has completed.

    :param run: The ForecastRun object representing the forecast job.
    - Marks the forecast job as DONE in the database, indicating successful completion.
    - Currently, this function does not involve additional processing beyond marking the status.
    """
    set_job_status(run, StatusEnum.DONE)  # Update the job's status to DONE in the database.


def finalize_forecast_forcing_download_after_callback(run: ForecastForcingDownloadRun) -> None:
    """
    Finalizes a forecast job after it has completed.

    :param run: The ForecastRun object representing the forecast job.
    - Marks the forecast job as DONE in the database, indicating successful completion.
    - Currently, this function does not involve additional processing beyond marking the status.
    """
    # Process output of forcing download
    set_job_status(run, StatusEnum.DONE)  # Update the job's status to DONE in the database.
    # submit the forecast job with the forcing data
    submit_job(run.forecast_run)
