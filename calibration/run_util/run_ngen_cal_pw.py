import logging
from urllib.parse import urljoin

import requests
from django.conf import settings
from rest_framework import status

from calibration.enums import StatusEnum, SlurmStatusEnum
from calibration.models import CalibrationRun, ValidationRun
from calibration.run_util.run_common import set_job_status, create_and_submit_validation_control, process_validation_output_and_maybe_create_best
from calibration.util.calibration_validators import SlurmSubmitJobResponse, GenericMessageResponseSerializer
from calibration.views.common import generate_custom_token, token_slurm_scope
from calibration.views.hydrofabric import validate_response_data
from calibration.views.read_output import read_calibration_output

logger = logging.getLogger(__name__)


def run_calibration_job_parallel_works(calibration_run: CalibrationRun, input_file, output_file):
    """
    Executes a calibration job via Slurm.
    with appropriate input and output file arguments, and registering a callback for job end.
    :param calibration_run: The CalibrationRun object representing the job run.
    :param input_file: Path to the input file.
    :param output_file: Path to the output file.
    """
    url = urljoin(settings.SLURM_URL, settings.SLURM_SUBMIT_CALIBRATION_JOB_ENDPOINT)
    payload = {
        'calibration_run_id': (None, calibration_run.id),
        'input_file': (None, input_file),
        'output_file': (None, output_file),
        'auth_token': (None, generate_custom_token(calibration_run.owner, token_slurm_scope))
    }

    logger.info(f'slurm submit-calibration-job payload: {payload}')
    response = requests.post(url, files=payload)
    handle_slurm_http_error(response, url, calibration_run.id)

    logger.info(f'Response from slurm for submit-calibration-job: {response.json()}')
    slurm_response = validate_response_data(SlurmSubmitJobResponse, response.json(),
                                            'Submit calibration job response data from Slurm is not in the expected format')

    calibration_run.slurm_job_id = slurm_response.get('slurm_job_id')
    calibration_run.ngen_commit_hash = slurm_response.get('ngen_commit_hash')
    calibration_run.ngen_cal_commit_hash = slurm_response.get('ngen_cal_commit_hash')
    calibration_run.save(update_fields=['slurm_job_id', 'ngen_commit_hash', 'ngen_cal_commit_hash'])
    logger.info(f"Calibration job submitted successfully! Slurm id: {calibration_run.slurm_job_id}")


def run_validation_job_parallel_works(validation_run: ValidationRun, input_file, output_file):
    """
    Executes a validation job via Slurm.
    with appropriate input and output file arguments, and registering a callback for job end.
    :param validation_run: The CalibrationRun object representing the job run.
    :param input_file: Path to the input file.
    :param output_file: Path to the output file.
    """
    url = urljoin(settings.SLURM_URL, settings.SLURM_SUBMIT_VALIDATION_JOB_ENDPOINT)
    payload = {
        'validation_run_id': (None, validation_run.id),
        'input_file': (None, input_file),
        'output_file': (None, output_file),
        'validation_type': (None, validation_run.validation_type),
        'worker_name': (None, validation_run.worker_name),
        'iteration': (None, validation_run.iteration_num),
        'auth_token': (None, generate_custom_token(validation_run.calibration_run.owner, token_slurm_scope))
    }

    logger.info(f'slurm submit-validation-job payload: {payload}')
    response = requests.post(url, files=payload)
    handle_slurm_http_error(response, url, validation_run.id)

    logger.info(f'Response from slurm for submit-validation-job: {response.json()}')
    slurm_response = validate_response_data(SlurmSubmitJobResponse, response.json(),
                                            'Submit validation job response data from Slurm is not in the expected format')

    validation_run.slurm_job_id = response.json().get('slurm_job_id')
    validation_run.ngen_commit_hash = slurm_response.get('ngen_commit_hash')
    validation_run.ngen_cal_commit_hash = slurm_response.get('ngen_cal_commit_hash')
    validation_run.save(update_fields=['slurm_job_id', 'ngen_commit_hash', 'ngen_cal_commit_hash'])
    logger.info(f"Validation job submitted successfully! Slurm id: {validation_run.slurm_job_id}")


def run_calibration_job_callback_slurm(calibration_run: CalibrationRun, slurm_status: SlurmStatusEnum):
    """
    Callback function that gets executed when a calibration job completes.
    :param calibration_run: The CalibrationRun object representing the job run.
    :param slurm_status: Whether the job succeeded or failed, as an Enum
    """
    logger.info(
        f'Job end callback received for Calibration Job {calibration_run.id}/{calibration_run.owner.username}  with status {slurm_status}')

    if slurm_status == SlurmStatusEnum.CANCELED:
        logger.error(f'Calibration job {calibration_run.id}/{calibration_run.owner.username} was cancelled')
        set_job_status(calibration_run, StatusEnum.CANCELLED)
    elif slurm_status == SlurmStatusEnum.FAILED:
        logger.error(f'Calibration job {calibration_run.id}/{calibration_run.owner.username} ending due to abnormal return code')
        set_job_status(calibration_run, StatusEnum.FAILED)
    else:
        read_calibration_output(calibration_run)
        # Always submit a control run
        create_and_submit_validation_control(calibration_run)


def run_validation_job_callback_slurm(validation_run: ValidationRun, slurm_status: SlurmStatusEnum):
    """
    Callback function that gets executed when a validation job completes.
    :param validation_run: The ValidationRun object representing the job run.
    :param slurm_status: Whether the job succeeded or failed, as an Enum
    """
    logger.info(
        f'Job end callback received for Validation Job {validation_run.id}, Calibration Job {validation_run.calibration_run.id}/{validation_run.calibration_run.owner.username}, validation_type: {validation_run.validation_type}, with status {slurm_status}')

    if slurm_status == SlurmStatusEnum.CANCELED:
        logger.error(f'Validation Job {validation_run.id}, Calibration Job {validation_run.calibration_run.id}/{validation_run.calibration_run.owner.username} was cancelled')
        set_job_status(validation_run, StatusEnum.CANCELLED)
    elif slurm_status == SlurmStatusEnum.FAILED:
        logger.error(f'Validation Job {validation_run.id}, Calibration Job {validation_run.calibration_run.id}/{validation_run.calibration_run.owner.username} ending due to abnormal return code')
        set_job_status(validation_run, StatusEnum.FAILED)
    else:
        process_validation_output_and_maybe_create_best(validation_run)


def cancel_slurm_job(run: CalibrationRun | ValidationRun):
    """
     Terminates a job with the given calibration_run_id by sending a request to slurm.
     :param run: The CalibrationRun to terminate.
     """
    logger.info(f"Cancelling slurm job {run.slurm_job_id} for {'Calibration' if isinstance(run, CalibrationRun) else 'Validation'}  Run {run.id}")

    url = urljoin(settings.SLURM_URL, settings.SLURM_CANCEL_JOB_ENDPOINT)
    payload = {
        'slurm_job_id': (None, run.slurm_job_id)
    }

    logger.info(f'slurm cancel-job payload: {payload}')
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

    logger.info(f"{'Calibration' if isinstance(run, CalibrationRun) else 'Validation'} job {payload['slurm_job_id']} cancelled successfully")
    if isinstance(run, CalibrationRun):
        run_calibration_job_callback_slurm(run, SlurmStatusEnum.CANCELED)
    else:
        run_validation_job_callback_slurm(run, SlurmStatusEnum.CANCELED)

    return True


class SlurmJobException(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def handle_slurm_http_error(response, url, job_id):
    """
    Handle HTTP errors for Slurm job submissions or cancellations, and log detailed error messages.
    :param response: The HTTP response object from the Slurm API call.
    :param url: The URL that was called.
    :param job_id: The calibration or validation run ID.
    """
    # Initialize variables to store status code and response text
    status_code = None
    response_text = None

    try:
        # Capture status code and response text before raising an exception
        status_code = response.status_code
        response_text = response.text

        # Check if the response is HTML (likely an error page)
        content_type = response.headers.get('Content-Type', '')
        if 'text/html' in content_type:
            logger.warning(f"Received HTML response from {url} for job {job_id} - truncating output")
            response_text = response_text[:500] + '... (truncated)'
            raise SlurmJobException(f"Call to {url} for job {job_id} returned HTML. Response text: {response_text}", status_code)

        # Raise an exception if the HTTP request failed
        response.raise_for_status()

    except requests.exceptions.HTTPError as e:
        message = f"Call to {url} failed with {status_code}. Response text: {response_text if response_text else 'No response received'}"
        logger.error(message)
        print(f"HTTP Error {status_code}: {response_text if response_text else 'No response received'}")
        raise SlurmJobException(message, status_code) from e

    except requests.exceptions.RequestException as e:
        # Handle connection errors or timeouts
        message = f"Call to {url} for job {job_id} failed to connect or timed out."
        logger.error(message)
        print(f"Request Error: {message}")
        raise SlurmJobException(message) from e
