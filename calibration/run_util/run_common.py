import json
import logging
import os
import subprocess
from concurrent.futures import Future
from datetime import datetime, timezone
from typing import Callable

from createInput import create_input
from django.conf import settings
from django.db import transaction
from rest_framework.response import Response

from calibration.enums import StatusEnum, ValidationType, SlurmStatusEnum
from calibration.enums_vanilla import JobType
from calibration.models import CalibrationRun, ValidationRun, Iteration, ForecastRun
from calibration.models.base_run import BaseRun
from calibration.models.forecast_forcing_download_run import ForecastForcingDownloadRun
from calibration.util.file_util import get_single_file
from calibration.util.git_util import get_git_info_internal
from calibration.util.ngen_locations import get_calibration_input_file, get_validation_best_stdout_file, get_validation_control_stdout_file, \
    get_calibration_stdout_file, get_validation_best_input_file, get_validation_control_input_file, get_validation_iteration_stdout_file, \
    get_forecast_forcing_download_stdout_file, get_forecast_stdout_file, get_geopackage_dir_for_job, get_forecast_forcing_download_path, \
    get_forecast_dir, get_forecast_forcing_config_file, get_validation_iteration_git_info_file, get_forecast_download_git_info_file, \
    get_validation_special_git_info_file, get_calibration_git_info_file, get_forecast_git_info_file
from calibration.views import ngen_cal_input
from calibration.views.common import ResponseError, CerfException, create_validation_run_internal, get_job_description, create_ngen_logging_file
from calibration.views.end_of_job_processing import read_validation_output, read_calibration_output, read_forecast_output
from calibration.views.forecast_forcing_input import build_forecast_forcing_download_config
from cerfServer.settings import NgenEnvironmentEnum

logger = logging.getLogger(__name__)

# Job registry to store subprocess objects keyed by a tuple of (calibration_run_id, validation_run_id)
job_registry: dict[tuple[int, int], subprocess.Popen] = {}


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

    raise TypeError(f"Unsupported run type: {type(run).__name__}")


def set_job_status(run: BaseRun, status: StatusEnum) -> None:
    """
    Update the status of a CalibrationRun, ValidationRun, or ForecastRun and clear the job registry if applicable.

    This function updates the `status` field of the job, clears the `slurm_job_id`,
    and removes the job from the global job registry for LOCAL or DOCKER environments.

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

    Determines the owner of the job from its `CalibrationRun`, `ValidationRun`,
    or `ForecastRun` relationship.

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


def validate_cmd_args(cmd_line_args: dict[str, str], stdout_file: str) -> None:
    """
    Validates the command-line arguments and output file paths for LOCAL and DOCKER environments.

    This function ensures that all arguments passed to subprocess-based commands are valid types
    (str, bytes, or os.PathLike) and not None. It raises a TypeError if any invalid argument type
    is encountered, or a ValueError if any argument value is None.

    :param cmd_line_args: A dictionary of command-line arguments where the keys are argument names
                          and the values are their corresponding values.
    :param stdout_file: The path to the file where the job's stdout will be written.
                        It must be a valid path-like object.
    :raises TypeError: If any argument or the stdout file is not a valid type.
    :raises ValueError: If any argument value is None.
    """

    # Define allowed types for clarity
    allowed_types = (str, bytes, os.PathLike)

    # Validate each argument in the command-line arguments dictionary
    for key, value in cmd_line_args.items():
        if value is None:
            logger.error(f"Argument '{key}' is None, which is not allowed.")
            raise ValueError(f"Command-line argument '{key}' cannot be None.")

        # Check if the value is one of the allowed types
        if not isinstance(value, allowed_types):
            # Log the invalid argument with valid type information
            logger.error(
                f"Invalid argument for '{key}': {value} (type: {type(value)}). "
                f"Expected one of {allowed_types}."
            )
            # Raise a TypeError with details about the invalid argument
            raise TypeError(
                f"Invalid argument for '{key}': {value} (type: {type(value)}). "
                f"Expected one of {allowed_types}."
            )

    # Validate the stdout file path to ensure it's a valid type
    if not isinstance(stdout_file, allowed_types):
        # Log the invalid stdout file path with valid type information
        logger.error(
            f"Invalid stdout_file: {stdout_file} (type: {type(stdout_file)}). "
            f"Expected one of {allowed_types}."
        )
        # Raise a TypeError with details about the invalid stdout file path
        raise TypeError(
            f"Invalid stdout_file: {stdout_file} (type: {type(stdout_file)}). "
            f"Expected one of {allowed_types}."
        )


def execute_job(run: BaseRun, cmd_line_args: dict[str, str], stdout_file: str, simulate: bool = False) -> None:
    """
    Execute a job based on the configured NGEN environment.

    This function dynamically calls the appropriate job execution function
    based on the environment (LOCAL, DOCKER, or PARALLEL_WORKS).

    :param run: The BaseRun object (CalibrationRun, ValidationRun, etc.).
    :param cmd_line_args: A dictionary of command-line arguments for the job.
    :param stdout_file: The path to the file where the job's stdout will be written.
    :param simulate: For LOCAL or DOCKER jobs, if True, simulates successful execution without running a real job.
    :raises CerfException: If the environment is unsupported.
    """
    if settings.NGEN_ENVIRONMENT in [NgenEnvironmentEnum.LOCAL, NgenEnvironmentEnum.DOCKER]:
        # Validate for LOCAL and DOCKER environments
        validate_cmd_args(cmd_line_args, stdout_file)

        from calibration.run_util.run_ngen_cal_local import run_job_local
        run_job_local(run, cmd_line_args, stdout_file, simulate=simulate)
    elif settings.NGEN_ENVIRONMENT == NgenEnvironmentEnum.PARALLEL_WORKS:
        from calibration.run_util.run_ngen_cal_pw import submit_job_to_slurm
        # Resolve owner dynamically for the Slurm submission
        try:
            owner = get_run_owner(run)  # Use the utility function
        except AttributeError as e:
            raise CerfException(f"Error retrieving owner for run {run.id}: {str(e)}")
        submit_job_to_slurm(run, owner, cmd_line_args, stdout_file)
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
    :raises CerfException: If the input file does not exist.
    """
    input_file = get_calibration_input_file(calibration_run)
    if not os.path.exists(input_file):
        raise CerfException(
            f"Input file '{input_file}' does not exist for Calibration Job {calibration_run.id}, user: {calibration_run.owner.username}"
        )

    stdout_file = get_calibration_stdout_file(calibration_run)

    execute_job(
        calibration_run,
        {'input_file': input_file, 'nprocs': str(calibration_run.mpi_nprocs)},
        stdout_file,
        simulate=settings.SIMULATE_FLAGS.get(JobType.CALIBRATION, False)
    )


def run_validation_job(validation_run: ValidationRun) -> None:
    """
    Start a validation job by determining input and output file paths.

    This function is intended to be passed as an argument to `submit_job`
    and not called directly.

    :param validation_run: The ValidationRun object representing the job.
    :raises CerfException: If the input file does not exist.
    """
    if validation_run.validation_type == ValidationType.VALID_BEST.value:
        input_file = get_validation_best_input_file(validation_run.calibration_run)
        stdout_file = get_validation_best_stdout_file(validation_run.calibration_run)
    elif validation_run.validation_type == ValidationType.VALID_CONTROL.value:
        input_file = get_validation_control_input_file(validation_run.calibration_run)
        stdout_file = get_validation_control_stdout_file(validation_run.calibration_run)
    else:
        # Regular validation
        input_file = get_calibration_input_file(validation_run.calibration_run)
        stdout_file = get_validation_iteration_stdout_file(validation_run.calibration_run, validation_run.worker_name, validation_run.iteration_num)

    if not os.path.exists(input_file):
        raise CerfException(
            f"Input file '{input_file}' does not exist for Validation Job {validation_run.id}, "
            f"user: {validation_run.calibration_run.owner.username}, type: {validation_run.validation_type}"
        )

    cmd_line_args = {'input_file': input_file}
    if validation_run.validation_type == ValidationType.VALID_ITERATION.value:
        # For running local, we need to leave these out
        cmd_line_args['worker_name'] = validation_run.worker_name
        cmd_line_args['iteration_num'] = str(validation_run.iteration_num)
    cmd_line_args['nprocs'] = str(validation_run.calibration_run.mpi_nprocs)
    execute_job(
        validation_run,
        cmd_line_args,
        stdout_file,
        simulate=settings.SIMULATE_FLAGS.get(JobType.VALIDATION, False)
    )


def run_forecast_forcing_download_job(forecast_forcing_download_run: ForecastForcingDownloadRun) -> None:
    """
    Start a forecast forcing download job by determining input and output file paths.

    This function is intended to be passed as an argument to `submit_job`
    and not called directly.

    :param forecast_forcing_download_run: The ForecastForcingDownloadRun object representing the job.
    """
    build_forecast_forcing_download_config(forecast_forcing_download_run)

    gpkg_file = get_single_file(get_geopackage_dir_for_job(forecast_forcing_download_run.forecast_run.calibration_run))
    cycle_name = forecast_forcing_download_run.forecast_run.cycle.internal_name
    config_file = get_forecast_forcing_config_file(forecast_forcing_download_run.forecast_run)
    forcing_dir = get_forecast_forcing_download_path(forecast_forcing_download_run.forecast_run)
    os.makedirs(forcing_dir, exist_ok=True)
    stdout_file = get_forecast_forcing_download_stdout_file(forecast_forcing_download_run.forecast_run)

    execute_job(
        forecast_forcing_download_run,
        {
            'cycle_name': cycle_name,
            'gpkg_file': gpkg_file,
            'config_file': config_file,
            'forcing_dir': forcing_dir
        },
        stdout_file,
        simulate=settings.SIMULATE_FLAGS.get(JobType.FORECAST_FORCING_DOWNLOAD, False)
    )


def run_forecast_job(forecast_run: ForecastRun) -> None:
    """
    Start a forecast job by determining input and output file paths.

    This function is intended to be passed as an argument to `submit_job`
    and not called directly.

    :param forecast_run: The ForecastRun object representing the job.
    """
    forcing_dir = get_forecast_forcing_download_path(forecast_run)
    validation_best_input = get_validation_best_input_file(forecast_run.calibration_run)
    forecast_dir = os.path.basename(get_forecast_dir(forecast_run))
    stdout_file = get_forecast_stdout_file(forecast_run)

    execute_job(
        forecast_run,
        {
            'forcing_dir': forcing_dir,
            'validation_best_input': validation_best_input,
            'forecast_dir': forecast_dir
        },
        stdout_file,
        simulate=settings.SIMULATE_FLAGS.get(JobType.FORECAST, False)
    )


def submit_job(run: BaseRun, config_file=None, logging_config=None) -> Response | None:
    """
    Submit a job after setting initial status and submission date.

    The specific job execution function is determined based on the job type
    and executed accordingly.

    Handles special preparation logic for calibration jobs internally
    before delegating execution to the appropriate job function.

    :param run: The BaseRun object (CalibrationRun, ValidationRun, etc.) to submit.
    :param config_file: Optional configuration file for CalibrationRun preparation.
    :param logging_config: Optional logging configuration for CalibrationRun preparation.
    :return: A DRF Response instance if there is an issue; otherwise, None on success.
    """
    # Special handling for calibration jobs
    if isinstance(run, CalibrationRun):
        create_ngen_logging_file(run, logging_config)
        response = prepare_calibration_job(run, config_file)
        if response:
            return response

    try:
        with transaction.atomic():
            # Set submission date and status
            run.submit_date = datetime.now(timezone.utc)
            run.status = StatusEnum.RUNNING.db_instance
            run.save(update_fields=['submit_date', 'status'])

        # Determine the appropriate job execution function
        if isinstance(run, CalibrationRun):
            create_git_info(get_calibration_git_info_file(run))
            run_calibration_job(run)
        elif isinstance(run, ValidationRun):
            if (run.validation_type != ValidationType.VALID_ITERATION.value):
                create_git_info(get_validation_special_git_info_file(run))
            else:
                create_git_info(get_validation_iteration_git_info_file(run, run.worker_name, run.iteration_num))

            run_validation_job(run)
        elif isinstance(run, ForecastForcingDownloadRun):
            create_git_info(get_forecast_download_git_info_file(run))

            run_forecast_forcing_download_job(run)
        elif isinstance(run, ForecastRun):
            create_git_info(get_forecast_git_info_file(run))

            run_forecast_job(run)
        else:
            raise CerfException(f"Unsupported run type: {type(run).__name__}")
    except Exception as e:
        # Handle failures by marking the job as FAILED
        run.__class__.objects.filter(id=run.id).update(status=StatusEnum.FAILED.db_instance)
        logger.exception(f'Exception submitting {get_job_description(run)} - {str(e)}')
        raise  # Re-raise the exception

    logger.info(f"{get_job_description(run)} successfully submitted.")
    return None


def create_git_info(git_info_file: str) -> None:
    logger.info(f"Writing git info to {git_info_file}")
    git_info_data = get_git_info_internal()
    os.makedirs(os.path.dirname(git_info_file), exist_ok=True)
    with open(git_info_file, 'w') as f:
        f.write(json.dumps(git_info_data, indent=4))


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
        logger.exception(f'Exception during create_input - {str(e)}')
        raise CerfException(f'Exception during create_input - {str(e)}') from e

    logger.info(f'Return from create_input for Calibration Job {calibration_run.id}')
    return None


def create_and_submit_validation_control(calibration_run: CalibrationRun) -> None:
    """
    Create a validation run of type VALID_CONTROL and submit it.

    :param calibration_run: The CalibrationRun object for which the validation control run is created.
    """
    validation_run = create_validation_run_internal(calibration_run, None, validation_type=ValidationType.VALID_CONTROL)
    submit_job(validation_run)


def process_validation_output_and_maybe_create_best(validation_run: ValidationRun, failed_so_far: bool) -> None:
    """
    Process the validation output and create a new VALID_BEST run if the validation type is VALID_CONTROL.

    :param validation_run: The ValidationRun object representing the job run.
    :param failed_so_far: Indicates whether the job has failed up to this point.
    - True if the job encountered a failure.
    - False if the job has completed successfully so far.
    """
    job_description = get_job_description(validation_run)

    try:
        # Process the validation output
        read_validation_output(validation_run, failed_so_far)
        if not failed_so_far:
            set_job_status(validation_run, StatusEnum.DONE)
    except Exception as e:
        # Catch the exception and mark the job as FAILED
        logger.exception(f"Error processing validation output for {job_description}: {str(e)}")
        set_job_status(validation_run, StatusEnum.FAILED)
        return  # Stop further processing if the job failed

    if not failed_so_far:
        # If we just ran Validation Control, see if we want to run Validation Best
        if validation_run.validation_type == ValidationType.VALID_CONTROL.value:
            if validation_run.calibration_run.automatic_validation:
                best_validation_run = create_validation_run_internal(
                    validation_run.calibration_run, None, validation_type=ValidationType.VALID_BEST
                )
                # Set the iteration containing the best values before we run it
                iteration = Iteration.objects.filter(calibration_run=validation_run.calibration_run, best_params=True).get()
                best_validation_run.iteration = iteration
                best_validation_run.save(update_fields=['iteration'])
                submit_job(best_validation_run)


def run_generic_job_callback(
        run: BaseRun,
        status: Future | SlurmStatusEnum,
        check_if_failed: Callable[[BaseRun, Future | SlurmStatusEnum], bool],
        finalize_func: Callable[[BaseRun, bool], None]
) -> None:
    """
    Generic callback function for handling job completion.

    :param run: The job object (CalibrationRun, ValidationRun, or ForecastRun) representing the job.
    :param status: The job's completion status. This can be:
        - A `Future` object (for Local environments)
        - A `SlurmStatusEnum` value (for Parallel Works environments)
    :param check_if_failed: Function to check job status based on the environment.
    :param finalize_func: Function to execute finalization logic specific to the job type.
    """
    job_description = get_job_description(run)
    logger.info(f"Job end callback received for {job_description} with status{status}")
    run.run_end = datetime.now(timezone.utc)
    run.save(update_fields=["run_end"])

    failed_so_far = check_if_failed(run, status)

    # Execute finalization logic
    finalize_func(run, failed_so_far)


def finalize_calibration_after_callback(run: CalibrationRun, failed_so_far: bool) -> None:
    """
    Finalizes a calibration job after it has completed.

    :param run: The CalibrationRun object representing the job.
    - Reads the output data generated by the calibration job and processes it.
    - Marks the calibration job as DONE in the database, indicating successful completion.
    - Creates and submits a validation control job to verify the calibration's results.
    :param failed_so_far: Indicates whether the job has failed up to this point.
    - True if the job encountered a failure.
    - False if the job has completed successfully so far.
    """
    job_description = get_job_description(run)

    try:
        # Process the calibration output
        read_calibration_output(run, failed_so_far)  # Process and store the output of the calibration job.
        if not failed_so_far:
            set_job_status(run, StatusEnum.DONE)  # Update the job's status to DONE in the database.
    except Exception as e:
        # Catch the exception and mark the job as FAILED
        logger.exception(f"Error processing calibration output for {job_description}: {str(e)}")
        set_job_status(run, StatusEnum.FAILED)
        return  # Stop further processing if the job failed

    if failed_so_far:
        return
    # If processing succeeded, continue with the next step
    try:
        create_and_submit_validation_control(run)  # Trigger the creation of validation jobs.
    except Exception as e:
        logger.exception(f"Error creating and submitting validation control run for {job_description}: {str(e)}")
        set_job_status(run, StatusEnum.FAILED)


def finalize_validation_after_callback(run: ValidationRun, failed_so_far: bool) -> None:
    """
    Finalizes a validation job after it has completed.

    :param run: The ValidationRun object representing the validation job.
    - Processes the output of the validation job and evaluates its results.
    - If applicable, creates a 'VALID_BEST' validation run.
    :param failed_so_far: Indicates whether the job has failed up to this point.
    - True if the job encountered a failure.
    - False if the job has completed successfully so far.
    """
    process_validation_output_and_maybe_create_best(run, failed_so_far)  # Process the validation results and handle best-run logic.


def finalize_forecast_forcing_download_after_callback(run: ForecastForcingDownloadRun, failed_so_far: bool) -> None:
    """
    Finalizes a forecast forcing download job after it has completed.

    :param run: The ForecastForcingDownloadRun object representing the job.
    - Processes the output of the forecast forcing download.
    - Marks the forecast forcing download job as DONE in the database.
    - Submits the associated forecast job.
    :param failed_so_far: Indicates whether the job has failed up to this point.
    - True if the job encountered a failure.
    - False if the job has completed successfully so far.
    """
    read_forecast_output(run, failed_so_far)
    if not failed_so_far:
        set_job_status(run, StatusEnum.DONE)  # Update the job's status to DONE in the database.
        # submit the forecast job with the forcing data
        submit_job(run.forecast_run)


def finalize_forecast_after_callback(run: ForecastRun, failed_so_far: bool) -> None:
    """
    Finalizes a forecast job after it has completed.

    :param run: The ForecastRun object representing the forecast job.
    - Processes the output of the forecast job.
    - Marks the forecast job as DONE in the database, indicating successful completion.
    :param failed_so_far: Indicates whether the job has failed up to this point.
    - True if the job encountered a failure.
    - False if the job has completed successfully so far.
    """
    read_forecast_output(run, failed_so_far)
    if failed_so_far:
        return
    set_job_status(run, StatusEnum.DONE)  # Update the job's status to DONE in the database.
