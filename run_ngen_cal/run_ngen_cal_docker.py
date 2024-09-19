import logging
from pathlib import Path
from urllib.parse import urljoin

import requests

from calibration.models import CalibrationRun
from cerfServer import settings
from run_ngen_cal.run_ngen_cal import JobStage

logger = logging.getLogger(__name__)





def run_docker(run: CalibrationRun, stage: JobStage, input_file, output_file):
    """
    Executes a local job for either CALIBRATION or VALIDATION stages by calling the shell script
    with appropriate input and output file arguments, and registering a callback for job stage transitions.
    :param run: The CalibrationRun object representing the job run.
    :param stage: The current job stage.
    :param input_file: Path to the input file for the stage.
    :param output_file: NOt used, since Slurm takes care of this
    """
    url = urljoin(settings.SLURM_URL, settings.SLURM_SUBMIT_ENDPOINT)
    payload = {
        'job_id':   Path(run.job_data_dir).name,
        'job_type': str(stage),
        'input_file': input_file,
    }

    # TODO How do we set callback?


    response = requests.post(url, data={"payload": payload})
    try:
        response.raise_for_status()
        run.slurm_job_id = response.json().get('slurm_job_id')
        run.save()
        logger.info(f"Job submitted successfully! Slurm id: {run.slurm_job_id}")
    except requests.exceptions.HTTPError:
        logger.error(f"Call to Slurm {url} failed with {response.status_code}.")
        logger.error(f"Response from Slurm: response.text - {str(e)}")
        return


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
    except requests.exceptions.HTTPError:
        logger.error(f"Failed to cancel job: {response.json().get('error')}")
        logger.error(f"Response from Slurm: response.text - {str(e)}")
        return
