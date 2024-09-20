import logging
from pathlib import Path
from urllib.parse import urljoin

import requests
from django.contrib.auth import get_user_model

from calibration.enums import StatusEnum
from calibration.models import CalibrationRun
from calibration.views.common import get_run
from cerfServer import settings
from calibration.run_util.run_common import JobStage, set_job_status
from calibration.run_util.run_ngen_cal import proceed_to_next_stage

logger = logging.getLogger(__name__)


def run_docker(run: CalibrationRun, stage: JobStage, input_file, output_file):
    """
    Executes a local job for either CALIBRATION or VALIDATION stages by calling the shell script
    with appropriate input and output file arguments, and registering a callback for job stage transitions.
    :param run: The CalibrationRun object representing the job run.
    :param stage: The current job stage.
    :param input_file: Path to the input file for the stage.
    :param output_file: Path to the output file for the stage.
    """
    url = urljoin(settings.SLURM_URL, settings.SLURM_SUBMIT_JOB_ENDPOINT)
    payload = {
        'job_id': Path(run.job_data_dir).name,
        'job_type': 'calibration' if stage == JobStage.CALIBRATION else 'validation',
        # 'job_stage': str(stage),
        'input_file': input_file,
        # 'output_file': output_file,
    }

    # TODO How do we set callback?
    callback = run_job_callback_slurm

    response = requests.post(url, data={"payload": payload})
    try:
        response.raise_for_status()
        run.slurm_job_id = response.json().get('slurm_job_id')
        run.save()
        logger.info(f"Job submitted successfully! Slurm id: {run.slurm_job_id}")
    except requests.exceptions.HTTPError as e:
        logger.error(f"Call to Slurm {url} failed with {response.status_code}.")
        logger.error(f"Response from Slurm: response.text - {str(e)}")
        return


def run_job_callback_slurm(current_stage: JobStage, process_id, job_status):
    """
    Callback function that gets executed when a job stage completes. It handles job stage transitions, including
    moving to the next stage (if validation is enabled) or finishing the job.
    :param current_stage: The current job stage.
    :param process_id: The process_id of the job (id_user)
    :param job_status: Whether the job succeeded or failed
    """
    # Get run id from the process id
    calibration_run_id, username = process_id.split('_')
    user = get_user_model().objects.get(username=username)
    run, error_return = get_run(calibration_run_id, user)
    if error_return:
        return error_return

    print(f'Job {process_id} completed stage {current_stage}')

    # TODO Display job status
    if job_status == 'exception':
        print(f"Exception occurred in process {process_id} at stage {current_stage.name}")
        set_job_status(run, StatusEnum.FAILED)
        return
    elif job_status == 'cancelled':
        print(f'Job {process_id} was cancelled')
        set_job_status(run, StatusEnum.CANCELLED)
    elif job_status == 'failed':
        print(f'Job {process_id} ending due to abnormal return code')
        set_job_status(run, StatusEnum.FAILED)
    else:
        proceed_to_next_stage(run, current_stage, run.automatic_validation)


def cancel_slurm_job(run: CalibrationRun):
    url = urljoin(settings.SLURM_URL, settings.SLURM_CANCEL_JOB_ENDPOINT)
    payload = {
        'slurm_job_id': run.slurm_job_id
    }
    response = requests.post(url, data={"payload": payload})
    try:
        response.raise_for_status()
        run.slurm_job_id = response.json().get('slurm_job_id')
        run.save()
        logger.info(f"Job {payload['slurm_job_id']} cancelled successfully")
    except requests.exceptions.HTTPError as e:
        logger.error(f"Failed to cancel job: {response.json().get('error')}")
        logger.error(f"Response from Slurm: response.text - {str(e)}")
        return
