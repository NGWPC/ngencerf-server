import logging
from urllib.parse import urljoin

import requests
from django.conf import settings
from rest_framework import status

from calibration.enums import StatusEnum, SlurmStatusEnum
from calibration.models import CalibrationRun, ValidationRun
from calibration.run_util.run_common import set_job_status, create_and_submit_validation_control, process_validation_output_and_maybe_create_best
from calibration.util.calibration_validators import SlurmSubmitJobResponse, GenericMessageResponseSerializer
from calibration.views.common import generate_custom_token, token_slurm_scope, get_job_description
from calibration.views.hydrofabric import validate_response_data
from calibration.views.read_output import read_calibration_output

logger = logging.getLogger(__name__)


def submit_job_to_slurm(url_endpoint, run: CalibrationRun | ValidationRun, owner, input_file, output_file):
    """
    Submits a job to Slurm.
    :param url_endpoint: Slurm URL endpoint for submission.
    :param run: The CalibrationRun or ValidationRun object.
    :param owner: The owner (User object) of the job, for generating the auth token.
    :param input_file: Path to the input file.
    :param output_file: Path to the output file.
    """
    url = urljoin(settings.SLURM_URL, url_endpoint)
    payload = {
        'input_file': (None, input_file),
        'output_file': (None, output_file),
        'auth_token': (None, generate_custom_token(owner, token_slurm_scope))
    }

    if isinstance(run, ValidationRun):
        print('validation_type', run.validation_type)
        payload.update({
            'validation_run_id': (None, run.id),
            'validation_type': (None, run.validation_type),
            'worker_name': (None, run.worker_name),
            'iteration': (None, run.iteration_num)
        })
    else:
        payload.update({'calibration_run_id': (None, run.id)})

    logger.info(f'urm: {payload}')
    response = requests.post(url, files=payload)
    handle_slurm_http_error(response, url, run.id)

    logger.info(f'Response from Slurm for submit job: {response.json()}')
    slurm_response = validate_response_data(SlurmSubmitJobResponse, response.json(),
                                            'Submit job response data from Slurm is not in the expected format')

    run.slurm_job_id = slurm_response.get('slurm_job_id')
    run.ngen_commit_hash = slurm_response.get('ngen_commit_hash')
    run.ngen_cal_commit_hash = slurm_response.get('ngen_cal_commit_hash')
    run.save(update_fields=['slurm_job_id', 'ngen_commit_hash', 'ngen_cal_commit_hash'])
    logger.info(f"{get_job_description(run)} submitted successfully! Slurm id: {run.slurm_job_id}")


def run_calibration_job_parallel_works(calibration_run: CalibrationRun, owner, input_file, output_file):
    submit_job_to_slurm(settings.SLURM_SUBMIT_CALIBRATION_JOB_ENDPOINT, calibration_run, owner, input_file, output_file)


def run_validation_job_parallel_works(validation_run: ValidationRun, owner, input_file, output_file):
    submit_job_to_slurm(settings.SLURM_SUBMIT_VALIDATION_JOB_ENDPOINT, validation_run, owner, input_file, output_file)


def run_job_callback_common_pw(run: CalibrationRun | ValidationRun, slurm_status: SlurmStatusEnum) -> bool:
    """
    Common logic for the callback function that gets executed when a Slurm job completes.

    :param run: The CalibrationRun or ValidationRun object representing the job run.
    :param slurm_status: The status of the Slurm job process.
    :return: A boolean indicating whether the job completed successfully.
    """
    job_description = get_job_description(run)
    logger.info(f'Job end callback received for {job_description} with status {slurm_status}')

    if slurm_status == SlurmStatusEnum.CANCELED:
        logger.error(f'{job_description} was cancelled')
        set_job_status(run, StatusEnum.CANCELLED)
        return False
    elif slurm_status == SlurmStatusEnum.FAILED:
        logger.error(f'{job_description} ending due to abnormal return code')
        set_job_status(run, StatusEnum.FAILED)
        return False
    return True


def run_calibration_job_callback_slurm(calibration_run: CalibrationRun, slurm_status: SlurmStatusEnum) -> None:
    """
    Callback function that gets executed when a calibration job completes via Slurm.

    :param calibration_run: The CalibrationRun object representing the job run.
    :param slurm_status: The status of the Slurm job process.
    """
    if run_job_callback_common_pw(calibration_run, slurm_status):
        read_calibration_output(calibration_run)
        set_job_status(calibration_run, StatusEnum.DONE)
        # Always submit a control run
        create_and_submit_validation_control(calibration_run)


def run_validation_job_callback_slurm(validation_run: ValidationRun, slurm_status: SlurmStatusEnum) -> None:
    """
    Callback function that gets executed when a validation job completes via Slurm.

    :param validation_run: The ValidationRun object representing the job run.
    :param slurm_status: The status of the Slurm job process.
    """
    if run_job_callback_common_pw(validation_run, slurm_status):
        process_validation_output_and_maybe_create_best(validation_run)


def cancel_slurm_job(run: CalibrationRun | ValidationRun):
    """
     Terminates a job with the given calibration_run_id by sending a request to slurm.
     :param run: The CalibrationRun to terminate.
     """
    job_description = get_job_description(run)
    logger.info(f"Cancelling slurm job {run.slurm_job_id} for {job_description}")

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

    logger.info(f"{job_description} - {payload['slurm_job_id']} cancelled successfully")
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
