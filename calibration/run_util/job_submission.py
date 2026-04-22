"""
RabbitMQ job submission interface for Django.

This module is responsible for:
- Building normalized job submission and cancellation messages
- Validating message structure using DRF serializers
- Publishing messages to the job request queue

The external job_runner service consumes these messages and:
- Executes jobs in Docker or Slurm / Parallel Works, depending on configuration
- Publishes lifecycle events back to Django

This module does NOT:
- Execute jobs
- Track job lifecycle state beyond initial submission
"""

import logging
from datetime import datetime, timezone
from typing import Any

from calibration.enums import JobType
from calibration.enums_vanilla import JobExecutionMode
from calibration.models import CalibrationRun, ValidationRun, ForecastRun, ColdStartRun, VerificationRun
from calibration.models.base_run import BaseRun
from calibration.models.hindcast_run import HindcastRun
from calibration.run_util.messaging import publish_job_message
from calibration.util.calibration_validators import JobSubmitMessageSerializer, CancelJobMessageSerializer
from calibration.views.common import get_job_description, validate_request
from cerfServer.settings import RABBITMQ_JOBS_QUEUE, JOB_EXECUTION_MODE

logger = logging.getLogger(__name__)


def publish_job_request(
        run: BaseRun,
        arguments: dict[str, str],
        stdout_file: str,
) -> None:
    """
    Publish a job submission request to RabbitMQ.

    The message is consumed asynchronously by the external job_runner service,
    which is responsible for executing the job in the configured execution
    environment (for example Docker or Slurm / Parallel Works).

    This function does not receive an execution response. Job status updates
    are returned later through separate job event messages.

    :param run: Run instance (CalibrationRun, ValidationRun, etc.)
    :param arguments: Job-specific CLI arguments
    :param stdout_file: Path for job stdout output
    :raises JobSubmissionException: If publishing fails
    """
    job_description = get_job_description(run)
    message = build_job_submit_message(run, arguments, stdout_file)

    # Probably too much information to publish
    logger.info(
        "Publishing job request for %s to queue %s: %s",
        job_description,
        RABBITMQ_JOBS_QUEUE,
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


def publish_cancel_job_request(run: BaseRun) -> bool:
    """
    Publish a job cancellation request to RabbitMQ.

    The external consumer is responsible for handling cancellation logic for
    the configured execution environment.

    :param run: Run instance to cancel
    :return: True if message was successfully published
    :raises JobSubmissionException: If publishing fails
    """
    job_description = get_job_description(run)
    message = build_cancel_job_message(run)

    logger.info(
        "Publishing cancel job request for %s to queue %s: %s",
        job_description,
        RABBITMQ_JOBS_QUEUE,
        message,
    )

    try:
        publish_job_message(message)
    except Exception as e:
        message_text = f"Failed to publish cancel job request for {job_description}: {e}"
        logger.error(message_text)
        raise JobSubmissionException(message_text) from e

    logger.info("%s cancel job request published successfully.", job_description)
    return True


def build_job_submit_message(
        run: BaseRun,
        arguments: dict[str, str],
        stdout_file: str,
) -> dict[str, Any]:
    """
    Build and validate a job submission message.

    Produces a normalized message format with:
    - a stable envelope (message_type, version, job_type, run_id, timestamp)
    - a job-specific payload

    The payload structure varies by job type, but the full message is validated
    before publishing.

    :param run: Run instance
    :param arguments: Job-specific arguments
    :param stdout_file: Output file path
    :return: Validated message dict
    :raises ValueError: If validation fails
    """
    job_type = get_job_type(run)

    message: dict[str, Any] = {
        "message_type": "submit_job",
        "version": 1,
        "job_type": job_type.value,
        "run_id": run.id,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "payload": build_job_submit_payload(run, arguments, stdout_file, job_type),
    }

    validated, error = validate_request(JobSubmitMessageSerializer, message)
    if error:
        raise ValueError(str(error))
    return validated


def build_job_submit_payload(
        run: BaseRun,
        arguments: dict[str, str],
        stdout_file: str,
        job_type: JobType | None = None,
) -> dict[str, Any]:
    """
    Build the job-specific payload portion of a submission message.

    This helper only builds the payload dictionary. The caller is responsible
    for constructing and validating the full message envelope.

    :param run: Run instance
    :param arguments: Job-specific arguments
    :param stdout_file: Output file path
    :param job_type: Optional precomputed JobType
    :return: Payload dict
    :raises ValueError: If run type is unsupported
    """
    job_type = job_type or get_job_type(run)

    if job_type == JobType.CALIBRATION:
        calibration_run = run
        assert isinstance(calibration_run, CalibrationRun)
        return {
            "input_file": arguments["input_file"],
            "output_file": stdout_file,
            "nprocs": arguments["nprocs"],
            "node_type": calibration_run.node_type,
        }

    if job_type == JobType.VALIDATION:
        validation_run = run
        assert isinstance(validation_run, ValidationRun)
        return {
            "validation_type": validation_run.validation_type,
            "input_file": arguments["input_file"],
            "output_file": stdout_file,
            "nprocs": arguments["nprocs"],
            "node_type": validation_run.calibration_run.node_type,
            "worker_name": arguments.get("worker_name"),
            "iteration": arguments.get("iteration_num"),
        }

    if job_type == JobType.COLD_START:
        return {
            "validation_yaml": arguments["validation_yaml"],
            "realization_file": arguments["realization_file"],
            "stdout_file": stdout_file,
        }

    if job_type == JobType.FORECAST:
        return {
            "validation_yaml": arguments["validation_yaml"],
            "realization_file": arguments["realization_file"],
            "stdout_file": stdout_file,
        }

    if job_type == JobType.HINDCAST:
        return {
            "validation_yaml": arguments["validation_yaml"],
            "config_file": arguments["config_file"],
            "run_name": arguments["run_name"],
            "interval_cycle": arguments["interval_cycle"],
            "num_iterations": arguments["num_iterations"],
            "use_state": arguments["use_state"],
            "stdout_file": stdout_file,
        }

    if job_type == JobType.VERIFICATION:
        return {
            "verification_config": arguments["verification_config"],
            "stdout_file": stdout_file,
        }

    raise ValueError(f"Unsupported job type: {job_type}")


def build_cancel_job_message(run: BaseRun) -> dict[str, Any]:
    """
    Build and validate a job cancellation message.

    This message instructs the external consumer to cancel the job in the
    configured execution environment.

    If running in Slurm / Parallel Works mode, a slurm_job_id is required
    and must already be present on the run. This function will raise an
    error if it is missing.

    :param run: Run instance
    :return: Validated message dict
    :raises ValueError: If validation fails or required slurm_job_id is missing
    """
    job_type = get_job_type(run)

    slurm_job_id = run.slurm_job_id

    # Enforce contract for Slurm execution
    if JOB_EXECUTION_MODE == JobExecutionMode.PARALLEL_WORKS:
        if slurm_job_id is None:
            raise ValueError(
                f"Cannot cancel Slurm job without slurm_job_id "
                f"(job_type={job_type.value}, run_id={run.id})"
            )

    message: dict[str, Any] = {
        "message_type": "cancel_job",
        "version": 1,
        "job_type": job_type.value,
        "run_id": run.id,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "slurm_job_id": slurm_job_id,
    }

    validated, error = validate_request(CancelJobMessageSerializer, message)
    if error:
        raise ValueError(str(error))

    return validated


def get_job_type(run: BaseRun) -> JobType:
    """
    Map a run instance to its corresponding JobType enum.

    This ensures consistent job_type values across:
    - message publishing
    - consumer routing logic
    - validation layers

    :param run: Run instance
    :return: JobType enum
    :raises ValueError: If run type is unsupported
    """
    if isinstance(run, CalibrationRun):
        return JobType.CALIBRATION
    if isinstance(run, ValidationRun):
        return JobType.VALIDATION
    if isinstance(run, ColdStartRun):
        return JobType.COLD_START
    if isinstance(run, ForecastRun):
        return JobType.FORECAST
    if isinstance(run, HindcastRun):
        return JobType.HINDCAST
    if isinstance(run, VerificationRun):
        return JobType.VERIFICATION

    raise ValueError(f"Unsupported run type: {type(run).__name__}")


class JobSubmissionException(Exception):
    """
    Raised when a job submission or cancellation message fails to publish.
    """

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code
