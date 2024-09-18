import logging
from urllib.parse import urljoin

import requests

from calibration.models import CalibrationRun
from cerfServer import settings

logger = logging.getLogger(__name__)


headers = {
    "Content-Type": "application/json"
}


def run_docker(run: CalibrationRun, cmd, input_file):
    """
    Placeholder for Docker execution. Currently not supported.
    :param run: The CalibrationRun object.
    :param cmd: The job command.
    :param input_file: Input file path.
    """
    url = urljoin(settings.SLURM_URL, 'endpoint')
    payload = {}
    response = requests.post(url, headers=headers, json={"payload": payload})
    try:
        response.raise_for_status()
        json_response = response.json()
    except requests.exceptions.HTTPError:
        logger.error(f"Call to Slurm {url} failed with {response.status_code}.")
        print("Response from Slurm:", response.text)
        return