import functools
import logging
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import status

from calibration.enums import StatusEnum, SlurmStatusEnum
from calibration.models import CalibrationRun, ValidationRun, ForecastRun
from calibration.models.base_run import BaseRun
from calibration.models.forecast_forcing_download_run import ForecastForcingDownloadRun
from calibration.run_util.run_common import set_job_status, run_generic_job_callback, finalize_calibration_after_callback, \
    finalize_validation_after_callback, finalize_forecast_after_callback, finalize_forecast_forcing_download_after_callback
from calibration.util.calibration_validators import SlurmSubmitJobResponse, GenericMessageResponseSerializer
from calibration.views.common import generate_custom_token, token_slurm_scope, get_job_description
from calibration.views.hydrofabric import validate_response_data

logger = logging.getLogger(__name__)

User = get_user_model()  # Dynamically fetch the custom user model


def submit_job_to_slurm(run: BaseRun, owner: User, input_file: str, output_file: str) -> None:
    """
    Submits a job to Slurm, determining the appropriate endpoint, payload, and handling HTTP responses.

    :param run: The CalibrationRun, ValidationRun, ForecastRun, or ForecastForcingDownloadRun object.
    :param owner: The owner (user instance) of the job, used to generate the auth token.
    :param input_file: Path to the input file for the job.
    :param output_file: Path to the output file for the job.
    """
    if isinstance(run, CalibrationRun):
        url_endpoint = settings.SLURM_SUBMIT_CALIBRATION_JOB_ENDPOINT
    elif isinstance(run, ValidationRun):
        url_endpoint = settings.SLURM_SUBMIT_VALIDATION_JOB_ENDPOINT
    elif isinstance(run, ForecastRun):
        url_endpoint = settings.SLURM_SUBMIT_FORECAST_JOB_ENDPOINT
    elif isinstance(run, ForecastForcingDownloadRun):
        url_endpoint = settings.SLURM_SUBMIT_FORECAST_FORCING_DOWNLOAD_JOB_ENDPOINT
    else:
        raise ValueError(f"Unsupported run type: {type(run).__name__}")

    url = urljoin(settings.SLURM_URL, url_endpoint)
    payload = {
        'input_file': (None, input_file),
        'output_file': (None, output_file),
        'auth_token': (None, generate_custom_token(owner, token_slurm_scope))
    }

    if isinstance(run, ValidationRun):
        payload.update({
            'validation_run_id': (None, run.id),
            'validation_type': (None, run.validation_type),
            'worker_name': (None, run.worker_name),
            'iteration': (None, run.iteration_num)
        })
    elif isinstance(run, CalibrationRun):
        payload.update({'calibration_run_id': (None, run.id)})
    elif isinstance(run, ForecastRun):
        payload.update({'forecast_run_id': (None, run.id)})
    elif isinstance(run, ForecastForcingDownloadRun):
        payload.update({'forecast_forcing_download_run_id': (None, run.id)})

    logger.info(f'Slurm submit-job payload to {url}: {payload}')
    response = requests.post(url, files=payload)
    handle_slurm_http_error(response, url, run.id)

    logger.info(f'Response from Slurm for submit job: {response.json()}')
    slurm_response = validate_response_data(
        SlurmSubmitJobResponse,
        response.json(),
        'Submit job response data from Slurm is not in the expected format',
    )

    run.slurm_job_id = slurm_response.get('slurm_job_id')
    run.ngen_commit_hash = slurm_response.get('ngen_commit_hash')
    run.ngen_cal_commit_hash = slurm_response.get('ngen_cal_commit_hash')
    run.save(update_fields=['slurm_job_id', 'ngen_commit_hash', 'ngen_cal_commit_hash'])
    logger.info(f"{get_job_description(run)} submitted successfully! Slurm id: {run.slurm_job_id}")


def check_pw_status(run: BaseRun, slurm_status: SlurmStatusEnum) -> bool:
    """
    Checks the status of a job executed in a Parallel Works environment and updates its status accordingly.

    :param run: The job object (CalibrationRun, ValidationRun, ForecastRun, etc.) being monitored.
    :param slurm_status: The SlurmStatusEnum indicating the job's completion status.
    :return: True if the job completed successfully, False otherwise.
    """
    if slurm_status == SlurmStatusEnum.CANCELED:
        logger.error(f"{get_job_description(run)} was cancelled")
        set_job_status(run, StatusEnum.CANCELLED)
        return False
    elif slurm_status == SlurmStatusEnum.FAILED:
        logger.error(f"{get_job_description(run)} ending due to abnormal return code {slurm_status}")
        set_job_status(run, StatusEnum.FAILED)
        return False
    return True


# Parallel Works callbacks
# These callbacks are used to handle job completion events for Calibration, Validation, and Forecast jobs
# in the Parallel Works (PW) environment. They wrap the `run_generic_job_callback` function,
# providing environment-specific status checks (`check_pw_status`) and job-specific finalization functions.

# Handles the completion of a calibration job in the PW environment.
# - Uses `check_pw_status` to check the Slurm job's status (e.g., CANCELED or FAILED).
# - Executes `finalize_calibration` to read job output, mark the job as DONE, and possibly create validation runs.
run_calibration_job_callback_pw = functools.partial(
    run_generic_job_callback, job_callback_func=check_pw_status, finalize_func=finalize_calibration_after_callback
)

# Handles the completion of a validation job in the PW environment.
# - Uses `check_pw_status` to validate the job's status.
# - Executes `finalize_validation` to process validation results and potentially mark the best validation run.
run_validation_job_callback_pw = functools.partial(
    run_generic_job_callback, job_callback_func=check_pw_status, finalize_func=finalize_validation_after_callback
)

# Handles the completion of a forecast job in the PW environment.
# - Uses `check_pw_status` to validate the job's status.
# - Executes `finalize_forecast` to finalize the forecast job and mark it as DONE.
run_forecast_job_callback_pw = functools.partial(
    run_generic_job_callback, job_callback_func=check_pw_status, finalize_func=finalize_forecast_after_callback
)

# Handles the completion of a forecast job in the PW environment.
# - Uses `check_pw_status` to validate the job's status.
# - Executes `finalize_forecast` to finalize the forecast job and mark it as DONE.
run_forecast_forcing_download_job_callback_pw = functools.partial(
    run_generic_job_callback, job_callback_func=check_pw_status, finalize_func=finalize_forecast_forcing_download_after_callback
)


def cancel_slurm_job(run: BaseRun) -> bool:
    """
    Terminates a Slurm job by sending a cancellation request for the provided run.

    :param run: The CalibrationRun, ValidationRun, ForecastRun, etc. object to terminate.
    :return: True if the job was successfully cancelled, False otherwise.
    """
    job_description = get_job_description(run)
    logger.info(f"Cancelling slurm job {run.slurm_job_id} for {job_description}")

    url = urljoin(settings.SLURM_URL, settings.SLURM_CANCEL_JOB_ENDPOINT)
    payload = {'slurm_job_id': (None, run.slurm_job_id)}

    logger.info(f'Slurm cancel-job payload to {url}: {payload}')
    response = requests.post(url, files=payload)
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        logger.error(f"Call to Slurm {url} failed with {response.status_code}.")
        logger.error(f"Failed to cancel job: {response.json().get('error')}, {str(e)}")
        if response.status_code == status.HTTP_404_NOT_FOUND:
            return False
        raise

    logger.info(f'Response from cancel slurm: {response.json()}')

    validate_response_data(GenericMessageResponseSerializer, response.json(),
                           'Cancel job response data from Slurm is not in the expected format')

    logger.info(f"{job_description} - {payload['slurm_job_id']} cancelled successfully")
    return True


class SlurmJobException(Exception):
    """
    Custom exception class for handling Slurm job-related errors.

    :param message: The error message describing the exception.
    :param status_code: Optional HTTP status code associated with the error.
    """

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def handle_slurm_http_error(response: requests.Response, url: str, job_id: int) -> None:
    """
    Handle HTTP errors for Slurm job submissions or cancellations, and log detailed error messages.

    :param response: The HTTP response object from the Slurm API call.
    :param url: The URL that was called.
    :param job_id: The calibration or validation run ID.
    """
    # Initialize variables to store status code and response text
    status_code = response.status_code
    response_text = response.text

    try:
        # Check if the response is HTML (likely an error page)
        content_type = response.headers.get('Content-Type', '')
        if 'text/html' in content_type:
            logger.warning(f"Received HTML response from {url} for job {job_id} - truncating output")
            response_text = response_text[:500] + '... (truncated)'
            raise SlurmJobException(f"Call to {url} for job {job_id} returned HTML. Response text: {response_text}", status_code)

        # Raise an exception if the HTTP request failed
        response.raise_for_status()

    except requests.exceptions.HTTPError as e:
        message = f"Call to {url} failed with {status_code}. Response text: {response_text or 'No response received'}"
        logger.error(message)
        raise SlurmJobException(message, status_code) from e

    except requests.exceptions.RequestException as e:
        # Handle connection errors or timeouts
        message = f"Call to {url} for job {job_id} failed to connect or timed out."
        logger.error(message)
        raise SlurmJobException(message) from e
