import logging
from enum import StrEnum, auto
from pathlib import Path
from urllib.parse import urljoin

import requests

from calibration.enums import StatusEnum
from calibration.models import CalibrationRun
from calibration.run_util.run_common import JobStage, set_job_status
from calibration.run_util.run_ngen_cal import proceed_to_next_stage
from calibration.views.common import generate_custom_token, token_slurm_scope
from cerfServer import settings

logger = logging.getLogger(__name__)


def run_parallel_works(run: CalibrationRun, stage: JobStage, input_file, output_file):
    """
    Executes a local job for either CALIBRATION or VALIDATION stages by calling the shell script
    with appropriate input and output file arguments, and registering a callback for job stage transitions.
    :param run: The CalibrationRun object representing the job run.
    :param stage: The current job stage, as an enum
    :param input_file: Path to the input file for the stage.
    :param output_file: Path to the output file for the stage.
    """
    logger.info(f'in run_parallel_works: {type(stage)}, {stage}')

    slurm_token = generate_custom_token(run.owner, token_slurm_scope)
    print(f'slurm token: {slurm_token}')
    # Slurm uses multipart form-data
    url = urljoin(settings.SLURM_URL, settings.SLURM_SUBMIT_JOB_ENDPOINT)
    payload = {
        'job_id': (None, Path(run.job_data_dir).name),
        'job_type': (None, 'calibration' if stage == JobStage.CALIBRATION else 'validation'),
        'job_stage': (None, stage.value),
        'input_file': (None, input_file),
        'output_file': (None, output_file),
        'auth_token': (None, generate_custom_token(run.owner, token_slurm_scope))
    }

    # TODO How do we set callback?
    # callback = run_job_callback_slurm

    logger.info(f'slurm payload: {payload}')
    response = requests.post(url, files=payload)
    try:
        response.raise_for_status()
        run.slurm_job_id = response.json().get('slurm_job_id')
        run.save()
        logger.info(f"Job submitted successfully! Slurm id: {run.slurm_job_id}")
    except requests.exceptions.HTTPError as e:
        logger.error(f"Call to Slurm {url} failed with {response.status_code}.")
        logger.error(f"Response from Slurm: '{response.text}' - {str(e)}")
        raise


class SlurmStatusEnum(StrEnum):
    DONE = auto()
    FAILED = auto()
    CANCELED = auto()


def run_job_callback_slurm(current_stage: JobStage, process_id, run, slurm_status: SlurmStatusEnum):
    """
    Callback function that gets executed when a job stage completes. It handles job stage transitions, including
    moving to the next stage (if validation is enabled) or finishing the job.
    :param current_stage: The current job stage, as an Enum
    :param process_id: The process_id of the job (id_user)
    :param run: The CalibrationRun object representing the job run.
    :param slurm_status: Whether the job succeeded or failed, as an Enum
    """
    logger.info(f'Job {process_id} completed stage {current_stage}')

    if slurm_status == SlurmStatusEnum.CANCELED:
        logger.error(f'Job {process_id} was cancelled')
        set_job_status(run, StatusEnum.CANCELLED)
    elif slurm_status == SlurmStatusEnum.FAILED:
        logger.error(f'Job {process_id} ending due to abnormal return code')
        set_job_status(run, StatusEnum.FAILED)
    else:
        proceed_to_next_stage(run, current_stage, run.automatic_validation)


def cancel_slurm_job(run: CalibrationRun):
    """
     Terminates a job with the given calibration_run_id by sending a request to slurm.
     :param run: The CalibrationRun to terminate.
     """
    url = urljoin(settings.SLURM_URL, settings.SLURM_CANCEL_JOB_ENDPOINT)
    payload = {
        'slurm_job_id': (None, run.slurm_job_id)
    }

    logger.info(f'slurm payload: {payload}')
    response = requests.post(url, files=payload)
    try:
        # TODO Need to check for 'job doesn't exist' or some other error
        response.raise_for_status()
        logger.info(f"Job {payload['slurm_job_id']} cancelled successfully")
        return True
    except requests.exceptions.HTTPError as e:
        logger.error(f"Failed to cancel job: {response.json().get('error')}")
        logger.error(f"Response from Slurm: '{response.text}' - {str(e)}")
        raise
