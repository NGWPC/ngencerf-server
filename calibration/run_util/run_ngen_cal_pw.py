import logging
from urllib.parse import urljoin

import requests
from django.conf import settings
from rest_framework import status

from calibration.enums import StatusEnum, SlurmStatusEnum
from calibration.models import CalibrationRun, ValidationRun
from calibration.run_util.run_common import JobStage, set_job_status, proceed_to_next_stage
from calibration.util.calibration_validators import SlurmSubmitJobResponse, GenericMessageResponseSerializer
from calibration.views.common import generate_custom_token, token_slurm_scope
from calibration.views.hydrofabric import validate_response_data
from calibration.views.read_output import read_validation_output

logger = logging.getLogger(__name__)


def run_calibration_job_parallel_works(calibration_run: CalibrationRun, stage: JobStage, input_file, output_file):
    """
    Executes a local calibration job for either CALIBRATION or VALIDATION stages by calling the shell script
    with appropriate input and output file arguments, and registering a callback for job stage transitions.
    :param calibration_run: The CalibrationRun object representing the job run.sl
    :param stage: The current job stage, as an enum
    :param input_file: Path to the input file for the stage.
    :param output_file: Path to the output file for the stage.
    """
    url = urljoin(settings.SLURM_URL, settings.SLURM_SUBMIT_CALIBRATION_JOB_ENDPOINT)
    payload = {
        'calibration_run_id': (None, calibration_run.id),
        'job_type': (None, 'calibration' if stage == JobStage.CALIBRATION else 'validation'),
        'job_stage': (None, stage.name),
        'input_file': (None, input_file),
        'output_file': (None, output_file),
        'auth_token': (None, generate_custom_token(calibration_run.owner, token_slurm_scope))
    }

    logger.info(f'slurm submit-calibration-job payload: {payload}')
    response = requests.post(url, files=payload)
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        logger.error(f"Call to Slurm {url} failed with {response.status_code}.")
        logger.error(f"Failed to submit job: {response.json().get('error')}, {str(e)}")
        raise

    logger.info(f'Response from slurm for submit-calibration-job: {response.json()}')
    slurm_response = validate_response_data(SlurmSubmitJobResponse, response.json(),
                                            'Submit calibration job response data from Slurm is not in the expected format')

    calibration_run.slurm_job_id = slurm_response.get('slurm_job_id')
    calibration_run.ngen_commit_hash = slurm_response.get('ngen_commit_hash')
    calibration_run.ngen_cal_commit_hash = slurm_response.get('ngen_cal_commit_hash')
    calibration_run.save(update_fields=['slurm_job_id', 'ngen_commit_hash', 'ngen_cal_commit_hash'])
    logger.info(f"Calibration job submitted successfully! Slurm id: {calibration_run.slurm_job_id}")


def run_validation_job_parallel_works(validation_run: ValidationRun, input_file, output_file, worker_name: str, iteration: int):
    """
    Executes a local job for either CALIBRATION or VALIDATION stages by calling the shell script
    with appropriate input and output file arguments, and registering a callback for job stage transitions.
    :param validation_run: The CalibrationRun object representing the job run.
    :param input_file: Path to the input file for the stage.
    :param output_file: Path to the output file for the stage.
    :param worker_name
    :param iteration
    """
    url = urljoin(settings.SLURM_URL, settings.SLURM_SUBMIT_VALIDATION_JOB_ENDPOINT)
    payload = {
        'validation_run_id': (None, validation_run.id),
        'input_file': (None, input_file),
        'output_file': (None, output_file),
        'auth_token': (None, generate_custom_token(validation_run.calibration_run.owner, token_slurm_scope))
    }

    logger.info(f'slurm submit-validation-job payload: {payload}')
    response = requests.post(url, files=payload)
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        logger.error(f"Call to Slurm {url} failed with {response.status_code}.")
        logger.error(f"Failed to submit job: {response.json().get('error')}, {str(e)}")
        raise

    logger.info(f'Response from slurm for submit-validation-job: {response.json()}')
    slurm_response = validate_response_data(SlurmSubmitJobResponse, response.json(),
                                            'Submit validation job response data from Slurm is not in the expected format')

    validation_run.slurm_job_id = response.json().get('slurm_job_id')
    validation_run.ngen_commit_hash = slurm_response.get('ngen_commit_hash')
    validation_run.ngen_cal_commit_hash = slurm_response.get('ngen_cal_commit_hash')
    validation_run.save(update_fields=['slurm_job_id', 'ngen_commit_hash', 'ngen_cal_commit_hash'])
    logger.info(f"Validation job submitted successfully! Slurm id: {validation_run.slurm_job_id}")


def run_calibration_job_callback_slurm(current_stage: JobStage | None, calibration_run: CalibrationRun, slurm_status: SlurmStatusEnum):
    """
    Callback function that gets executed when a job stage completes. It handles job stage transitions, including
    moving to the next stage (if validation is enabled) or finishing the job.
    :param current_stage: The current job stage, as an Enum (or None, if the job was cancelled)
    :param calibration_run: The CalibrationRun object representing the job run.
    :param slurm_status: Whether the job succeeded or failed, as an Enum
    """
    logger.info(
        f'Job end callback received for job {calibration_run.id}/{calibration_run.owner.username} in stage {current_stage} with status {slurm_status}')

    if slurm_status == SlurmStatusEnum.CANCELED:
        logger.error(f'Calibration job {calibration_run.id}/{calibration_run.owner.sername} was cancelled')
        set_job_status(calibration_run, StatusEnum.CANCELLED)
    elif slurm_status == SlurmStatusEnum.FAILED:
        logger.error(f'Calibration job {calibration_run.id}/{calibration_run.owner.username} ending due to abnormal return code')
        set_job_status(calibration_run, StatusEnum.FAILED)
    else:
        proceed_to_next_stage(calibration_run, current_stage)


def run_validation_job_callback_slurm(validation_run: ValidationRun, slurm_status: SlurmStatusEnum):
    """
    Callback function that gets executed when a job stage completes. It handles job stage transitions, including
    moving to the next stage (if validation is enabled) or finishing the job.
    :param validation_run: The CalibrationRun object representing the job run.
    :param slurm_status: Whether the job succeeded or failed, as an Enum
    """
    logger.info(
        f'Job end callback received for validation job {validation_run.id}/{validation_run.calibration_run.owner.username} with status {slurm_status}')

    if slurm_status == SlurmStatusEnum.CANCELED:
        logger.error(f'Validation job {validation_run.id}/{validation_run.calibration_run.owner.username} was cancelled')
        set_job_status(validation_run, StatusEnum.CANCELLED)
    elif slurm_status == SlurmStatusEnum.FAILED:
        logger.error(f'Validation job {validation_run.id}/{validation_run.calibration_run.owner.username}ending due to abnormal return code')
        set_job_status(validation_run, StatusEnum.FAILED)
    else:
        read_validation_output(validation_run)


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
    run_calibration_job_callback_slurm(None, run, SlurmStatusEnum.CANCELED)
    return True
