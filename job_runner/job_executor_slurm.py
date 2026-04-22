import logging
from typing import Any

from job_runner.job_executor_common import publish_terminal_job_event
from job_runner.job_runner_enums import SlurmCallbackStatusEnum

logger = logging.getLogger(__name__)


def handle_slurm_message(body: dict[str, Any]) -> None:
    """
    Handle a validated message using the Slurm / Parallel Works execution backend.

    :param body: Incoming message body deserialized from RabbitMQ
    :raises ValueError: If the message_type is unsupported or required slurm_job_id is missing
    """
    message_type = body["message_type"]
    job_type = body["job_type"]
    run_id = body["run_id"]

    if message_type == "submit_job":
        submit_slurm_job(job_type, run_id, body["payload"])
        return

    if message_type == "cancel_job":
        slurm_job_id = body.get("slurm_job_id")
        if slurm_job_id is None:
            raise ValueError("Missing slurm_job_id")
        if not isinstance(slurm_job_id, int):
            raise ValueError("slurm_job_id must be an integer")

        if not cancel_slurm_job(job_type, run_id, slurm_job_id):
            raise ValueError(
                f"Unable to cancel PARALLEL_WORKS job for job_type={job_type} run_id={run_id}"
            )
        return

    raise ValueError(f"Unsupported message_type: {message_type}")


def submit_slurm_job(job_type: str, run_id: int, payload: dict[str, Any]) -> None:
    """
    Submit a job through the Parallel Works / Slurm execution path.

    This path is responsible for both submitting the job and publishing the
    lifecycle callbacks back to Django through the job events queue.

    Required callback sequence:

    1. SUBMITTED
       - Publish immediately after successful Slurm submission
       - Must include the returned slurm_job_id
       - Allows Django to persist the Slurm job identifier

    2. STARTING
       - Publish when the job actually begins execution
       - Should include slurm_job_id
       - Allows Django to mark the run as RUNNING and set run_start

    3. Terminal callback (exactly one)
       - Status must be one of:
         DONE | FAILED | CANCELED
       - Must include slurm_job_id
       - Triggers final status updates and post-processing in Django

    Example sequence:

        # After submission
        publish_job_event(
            job_type,
            run_id,
            SlurmCallbackStatusEnum.SUBMITTED,
            slurm_job_id=slurm_job_id
        )

        # When execution begins
        publish_job_event(
            job_type,
            run_id,
            SlurmCallbackStatusEnum.STARTING,
            slurm_job_id=slurm_job_id
        )

        # When job completes
        publish_terminal_job_event(
            job_type,
            run_id,
            SlurmCallbackStatusEnum.DONE,
            slurm_job_id=slurm_job_id
        )

    Planned behavior:
    1. submit the job to Slurm
    2. obtain the slurm_job_id
    3. publish SUBMITTED
    4. publish STARTING when execution begins
    5. publish one terminal event

    This is not fully implemented yet.

    :param job_type: Normalized job type string
    :param run_id: Run identifier
    :param payload: Job-specific execution payload
    """
    logger.info(
        "PARALLEL_WORKS stub for job_type=%s run_id=%s payload=%s",
        job_type,
        run_id,
        payload,
    )

    # TODO: submit to Slurm
    # TODO: get slurm_job_id
    # TODO: publish SUBMITTED event with slurm_job_id
    # TODO: publish STARTING event with slurm_job_id when execution begins
    # TODO: publish terminal DONE / FAILED / CANCELED event with slurm_job_id


def cancel_slurm_job(
        job_type: str,
        run_id: int,
        slurm_job_id: int,
) -> bool:
    """
    Cancel a job through the Parallel Works / Slurm execution path.

    This function requires a valid slurm_job_id. The external consumer does
    not perform any lookup against Django or other storage, so the identifier
    must be provided in the incoming message.

    At present, the actual Slurm cancellation command is not yet implemented.
    As placeholder behavior, this function logs the request and publishes a
    terminal CANCELED event.

    Planned behavior:
    1. call Slurm cancellation command using slurm_job_id
    2. publish a CANCELED event (or FAILED if cancellation fails)

    NOTE:
    This function is currently a stub. The actual Slurm cancellation command
    (e.g., `scancel`) is not yet implemented.

    :param job_type: Normalized job type string
    :param run_id: Run identifier
    :param slurm_job_id: Slurm job identifier (required)
    :return: True if cancellation was successful (stubbed as True)
    :raises ValueError: If slurm_job_id is None
    """
    if slurm_job_id is None:
        raise ValueError(
            f"slurm_job_id is required for Slurm cancellation "
            f"(job_type={job_type}, run_id={run_id})"
        )

    logger.info(
        "PARALLEL_WORKS cancel request for job_type=%s run_id=%s slurm_job_id=%s",
        job_type,
        run_id,
        slurm_job_id,
    )

    # TODO:
    # subprocess.run(["scancel", str(slurm_job_id)], check=True)
    # publish_job_event(...)

    publish_terminal_job_event(
        job_type,
        run_id,
        SlurmCallbackStatusEnum.CANCELED,
        slurm_job_id,
    )
    return True
