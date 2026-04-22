import logging
from typing import Any

from kombu import Connection, Exchange, Producer, Queue

from job_runner.config import (
    JOB_EXECUTION_MODE,
    RABBITMQ_URL,
    RABBITMQ_JOB_EVENTS_QUEUE,
)
from job_runner.job_runner_enums import SlurmCallbackStatusEnum, JobExecutionMode

logger = logging.getLogger(__name__)


# Reuse one RabbitMQ connection for publishing.
# Channels are created per publish, which is the safer pattern when callbacks
# may run in different threads.
_connection = Connection(RABBITMQ_URL)


def validate_message(message: dict[str, Any]) -> None:
    """
    Validate the top-level structure of an incoming job-runner message.

    Supported message types:
    - submit_job
    - cancel_job

    All messages must include the common envelope fields:
    - message_type
    - version
    - job_type
    - run_id
    - submitted_at

    submit_job messages must also include:
    - payload

    This function validates only the shared message envelope and basic types.
    Job-specific payload validation is handled later by the execution logic.

    :param message: Incoming message body deserialized from RabbitMQ
    :raises ValueError: If the message is missing required fields or has invalid types
    """
    required_top_level = [
        "message_type",
        "version",
        "job_type",
        "run_id",
        "submitted_at",
    ]

    for key in required_top_level:
        if key not in message:
            raise ValueError(f"Missing required key: {key}")

    if message["message_type"] not in {"submit_job", "cancel_job"}:
        raise ValueError(f"Invalid message_type: {message['message_type']}")

    if not isinstance(message["version"], int):
        raise ValueError("version must be an integer")

    if not isinstance(message["job_type"], str):
        raise ValueError("job_type must be a string")

    if not isinstance(message["run_id"], int):
        raise ValueError("run_id must be an integer")

    if not isinstance(message["submitted_at"], str):
        raise ValueError("submitted_at must be a string")

    if message["message_type"] == "submit_job":
        if "payload" not in message:
            raise ValueError("Missing required key: payload")
        if not isinstance(message["payload"], dict):
            raise ValueError("payload must be a dictionary")


def publish_job_event(
        job_type: str,
        run_id: int,
        job_status: SlurmCallbackStatusEnum,
        slurm_job_id: int | None = None,
) -> None:
    """
    Publish a job lifecycle event to the Django-side job events queue.

    These events are consumed by the Django server and are used to represent
    submission acknowledgement, start notification, and terminal job state.

    Expected payload shape matches the server-side JobEventSerializer.

    :param job_type: Normalized job type string
    :param run_id: Run identifier
    :param job_status: Job lifecycle status to publish
    :param slurm_job_id: Slurm job identifier, when applicable
    """
    payload = {
        "job_type": job_type,
        "run_id": run_id,
        "job_status": job_status.value,
        "slurm_job_id": slurm_job_id,
    }

    logger.info(
        "Publishing job event for job_type=%s run_id=%s status=%s slurm_job_id=%s queue=%s",
        job_type,
        run_id,
        job_status.value,
        slurm_job_id,
        RABBITMQ_JOB_EVENTS_QUEUE,
    )
    logger.debug("Job event payload: %s", payload)

    queue = Queue(
        name=RABBITMQ_JOB_EVENTS_QUEUE,
        exchange=Exchange("", type="direct"),
        routing_key=RABBITMQ_JOB_EVENTS_QUEUE,
        durable=True,
    )

    # Ensure the shared connection is alive before opening a channel on it.
    _connection.ensure_connection(max_retries=3)

    with _connection.channel() as channel:
        producer = Producer(channel)

        producer.publish(
            payload,
            serializer="json",
            exchange="",
            routing_key=RABBITMQ_JOB_EVENTS_QUEUE,
            declare=[queue],
            retry=True,
            retry_policy={
                "max_retries": 3,
                "interval_start": 0,
                "interval_step": 1,
                "interval_max": 2,
            },
            delivery_mode=2,
        )


def publish_terminal_job_event(
        job_type: str,
        run_id: int,
        status: SlurmCallbackStatusEnum,
        slurm_job_id: int | None = None,
) -> None:
    """
    Publish a terminal job event with consistent error handling.

    :param job_type: Normalized job type string
    :param run_id: Run identifier
    :param status: Terminal job status
    :param slurm_job_id: Slurm job identifier, if applicable
    """
    try:
        publish_job_event(
            job_type=job_type,
            run_id=run_id,
            job_status=status,
            slurm_job_id=slurm_job_id,
        )
    except Exception:
        logger.exception(
            "Failed publishing terminal event for job_type=%s run_id=%s",
            job_type,
            run_id,
        )


def dispatch_message(body: dict[str, Any]) -> None:
    """
    Route message to the correct execution backend.

    :param body: Incoming message
    """
    validate_message(body)

    if JOB_EXECUTION_MODE == JobExecutionMode.DOCKER:
        from job_runner.job_executor_docker import handle_docker_message
        handle_docker_message(body)
        return

    if JOB_EXECUTION_MODE == JobExecutionMode.PARALLEL_WORKS:
        from job_runner.job_executor_slurm import handle_slurm_message
        handle_slurm_message(body)
        return

    raise ValueError(f"Unsupported execution mode: {JOB_EXECUTION_MODE}")
