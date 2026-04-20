import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import status

from calibration.models import CalibrationRun, ValidationRun, ForecastRun, ColdStartRun, VerificationRun
from calibration.models.base_run import BaseRun
from calibration.models.hindcast_run import HindcastRun
from calibration.util.calibration_validators import GenericMessageResponseSerializer
from calibration.util.messaging import publish_job_message
from calibration.views.common import generate_custom_token, TOKEN_SLURM_SCOPE, get_job_description, validate_response_data

logger = logging.getLogger(__name__)

User = get_user_model()  # Dynamically fetch the custom user model


def publish_job_request(
        run: BaseRun,
        owner: User,
        arguments: dict[str, str],
        stdout_file: str,
) -> None:
    """
    Publish a job request to RabbitMQ.

    This is the shared queue submission path for all execution environments.
    The consumer decides whether to run the job in DOCKER or PARALLEL_WORKS.

    Unlike the old direct-submit flow, this does not receive an immediate execution response.
    For PARALLEL_WORKS, run.slurm_job_id must be updated later by the consumer/callback path.
    For DOCKER, no slurm_job_id is expected.

    :param run: The CalibrationRun, ValidationRun, ColdStartRun, ForecastRun, or VerificationRun object.
    :param owner: The owner (user instance) of the job, used to generate the auth token.
    :param arguments: Dictionary containing command-line arguments for the job (e.g., 'input_file').
    :param stdout_file: The path to the file where job output will be written.
    :raises ValueError: If the run type is unsupported.
    :raises SlurmJobException: If there is an HTTP error during the job submission.
    """
    job_description = get_job_description(run)
    message = build_job_submit_message(run, owner, arguments, stdout_file)

    # Probably too much information to publish
    logger.info(
        "Publishing job request for %s to jobs_queue: %s",
        job_description,
        message,
    )
    # logger.info(
    #     "Publishing job request for %s to jobs_queue (job_type=%s, run_id=%s)",
    #     job_description,
    #     message["job_type"],
    #     message["run_id"],
    # )

    try:
        publish_job_message(message)
    except Exception as e:
        message_text = f"Failed to publish job request for {job_description}: {e}"
        logger.error(message_text)
        raise JobSubmissionException(message_text) from e

    logger.info(
        "%s job request published successfully. "
        "Waiting for downstream consumer callbacks.",
        job_description,
    )


def validate_job_submit_message(message: dict[str, object]) -> None:
    """
    Validate the structure of a job submission message before publishing.

    This enforces a stable contract between the Django producer and the job consumer.
    It only validates the envelope (top-level structure), not the job-specific payload.

    Expected message format:

    {
        "message_type": "submit_slurm_job",   # REQUIRED: identifies intent of message
        "version": 1,                         # REQUIRED: schema version for future changes
        "job_type": str,                      # REQUIRED: routing key for consumer logic
        "run_id": int,                        # REQUIRED: primary identifier for DB lookup
        "auth_token": str,                    # REQUIRED: token used by downstream system for auth
        "submitted_at": str,                  # REQUIRED: ISO8601 UTC timestamp (for tracing/debugging)
        "payload": dict                       # REQUIRED: job-specific parameters
    }
    """

    # ------------------------------------------------------------
    # Required top-level fields
    # ------------------------------------------------------------
    required_top_level = [
        "message_type",
        "version",
        "job_type",
        "run_id",
        "auth_token",  # Only needed for callbacks.  Might get rid of this
        "submitted_at",
        "payload",
    ]

    for key in required_top_level:
        if key not in message:
            raise ValueError(f"Missing required key: {key}")

    # ------------------------------------------------------------
    # message_type
    # ------------------------------------------------------------
    # Defines what kind of message this is.
    # This allows future expansion (e.g., cancel, status update, etc.)
    if message["message_type"] != "submit_slurm_job":
        raise ValueError(f"Invalid message_type: {message['message_type']}")

    # ------------------------------------------------------------
    # version
    # ------------------------------------------------------------
    # Allows backward-compatible schema evolution.
    # Keep this fixed unless you intentionally introduce a breaking change.
    if not isinstance(message["version"], int):
        raise ValueError("version must be an integer")

    # ------------------------------------------------------------
    # job_type
    # ------------------------------------------------------------
    # Used by the consumer to route handling logic.
    # Expected values match your run types:
    #   calibration, validation, forecast, hindcast, cold_start, verification
    if not isinstance(message["job_type"], str):
        raise ValueError("job_type must be a string")

    # ------------------------------------------------------------
    # run_id
    # ------------------------------------------------------------
    # Must map directly to a DB record in your system.
    # Consumer will typically use this to fetch/update the run.
    if not isinstance(message["run_id"], int):
        raise ValueError("run_id must be an integer")

    # ------------------------------------------------------------
    # auth_token
    # ------------------------------------------------------------
    # Token passed through to downstream system (Slurm service).
    # No validation here beyond type; actual validation happens downstream.
    if not isinstance(message["auth_token"], str):
        raise ValueError("auth_token must be a string")

    # ------------------------------------------------------------
    # submitted_at
    # ------------------------------------------------------------
    # ISO8601 UTC timestamp string.
    # Used for logging, tracing, and debugging.
    # Example: "2026-04-20T09:00:00+00:00"
    if not isinstance(message["submitted_at"], str):
        raise ValueError("submitted_at must be a string")

    # ------------------------------------------------------------
    # payload
    # ------------------------------------------------------------
    # Contains job-specific parameters.
    # Structure depends on job_type and is validated by the consumer.
    if not isinstance(message["payload"], dict):
        raise ValueError("payload must be a dictionary")


def build_job_submit_message(
        run: BaseRun,
        owner: User,
        arguments: dict[str, str],
        stdout_file: str,
) -> dict[str, Any]:
    """
    Build a normalized RabbitMQ message for submitting a job request.

    The consumer will inspect job_type and decide whether to execute in
    DOCKER or PARALLEL_WORKS.

    This replaces the old REST multipart payload with a structured JSON message.

    Top-level fields are stable across all job types.
    Job-specific data lives under "payload".
    """

    base_message: dict[str, Any] = {
        "message_type": "submit_slurm_job",
        "version": 1,
        "job_type": None,  # set below
        "run_id": run.id,
        "auth_token": generate_custom_token(owner, TOKEN_SLURM_SCOPE),
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "payload": {},
    }

    if isinstance(run, CalibrationRun):
        base_message["job_type"] = "calibration"
        base_message["payload"] = {
            "input_file": arguments["input_file"],
            "output_file": stdout_file,
            "nprocs": arguments["nprocs"],
            "node_type": run.node_type,
        }

    elif isinstance(run, ValidationRun):
        base_message["job_type"] = "validation"
        base_message["payload"] = {
            "validation_type": run.validation_type,
            "input_file": arguments["input_file"],
            "output_file": stdout_file,
            "nprocs": arguments["nprocs"],
            "node_type": run.calibration_run.node_type,
            "worker_name": arguments.get("worker_name"),
            "iteration": arguments.get("iteration_num"),
        }

    elif isinstance(run, ColdStartRun):
        base_message["job_type"] = "cold_start"
        base_message["payload"] = {
            "validation_yaml": arguments["validation_yaml"],
            "realization_file": arguments["realization_file"],
            "stdout_file": stdout_file,
        }

    elif isinstance(run, ForecastRun):
        base_message["job_type"] = "forecast"
        base_message["payload"] = {
            "validation_yaml": arguments["validation_yaml"],
            "realization_file": arguments["realization_file"],
            "stdout_file": stdout_file,
        }

    elif isinstance(run, HindcastRun):
        base_message["job_type"] = "hindcast"
        base_message["payload"] = {
            "validation_yaml": arguments["validation_yaml"],
            "config_file": arguments["config_file"],
            "run_name": arguments["run_name"],
            "interval_cycle": arguments["interval_cycle"],
            "num_iterations": arguments["num_iterations"],
            "use_state": arguments["use_state"],
            "stdout_file": stdout_file,
        }

    elif isinstance(run, VerificationRun):
        base_message["job_type"] = "verification"
        base_message["payload"] = {
            "verification_config": arguments["verification_config"],
            "stdout_file": stdout_file,
        }

    else:
        raise ValueError(
            f"Unsupported run type: {type(run).__name__}"
        )

    # Enforce structure before returning
    validate_job_submit_message(base_message)

    return base_message


def cancel_slurm_job(run: BaseRun) -> bool:
    """
    Cancel a running Slurm job by sending a cancellation request.

    This function constructs the payload with the Slurm job ID, sends an HTTP POST
    request to the Slurm cancellation endpoint, and validates the response.

    :param run: The CalibrationRun, ValidationRun, ColdStartRun, ForecastRun, etc. object to terminate.
    :return: True if the job was successfully canceled, False otherwise.
    :raises requests.exceptions.HTTPError: If the cancellation request fails with an HTTP error.
    """
    job_description = get_job_description(run)
    logger.info(f"Cancelling slurm job {run.slurm_job_id} for {job_description}")

    url = urljoin(settings.SLURM_URL, settings.SLURM_CANCEL_JOB_ENDPOINT)
    payload = {"slurm_job_id": (None, str(run.slurm_job_id))}

    logger.info(f"Slurm cancel-job payload to {url}: {payload}")
    response = requests.post(url, files=payload)

    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        logger.error(f"Call to Slurm {url} failed with {response.status_code}.")
        logger.error(f"Failed to cancel job: {response.json().get('error')}, {str(e)}")
        if response.status_code == status.HTTP_404_NOT_FOUND:
            return False
        raise

    logger.info(f"Response from cancel slurm: {response.json()}")

    validate_response_data(
        GenericMessageResponseSerializer,
        response.json(),
        "Cancel job response data from Slurm is not in the expected format",
    )

    logger.info(f"{job_description} - {payload['slurm_job_id']} cancelled successfully")
    return True


class JobSubmissionException(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code
