import logging
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Any, Callable

from kombu import Connection, Exchange, Producer, Queue

from job_runner.config import (
    JOB_EXECUTION_MODE,
    RABBITMQ_URL,
    RABBITMQ_JOB_EVENTS_QUEUE,
    RUNTIME_INFO,
)
from job_runner.job_runner_enums import SlurmCallbackStatusEnum, JobExecutionMode

logger = logging.getLogger(__name__)

pool: ThreadPoolExecutor = ThreadPoolExecutor()
job_registry: dict[str, subprocess.Popen] = {}

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


def get_registry_key(job_type: str, run_id: int) -> str:
    """
    Return the internal registry key used to track a running job process.

    This value is also used as the Docker container name when running in
    DOCKER mode.

    NOTE:
    This key is specific to the Docker execution path and is not used for
    Slurm / Parallel Works jobs, which are tracked by slurm_job_id instead.

    :param job_type: Normalized job type string
    :param run_id: Run identifier
    :return: Registry key / Docker container name
    """
    return f"{job_type}_{run_id}"


def get_script_name(job_type: str, payload: dict[str, Any]) -> str:
    """
    Return the runtime script name for the given job.

    Most jobs map directly from job_type to script name.
    Validation iteration jobs are a special case and use the
    'validation_iteration' script instead of the generic validation script.

    NOTE:
    This logic is only applicable to the Docker execution path. Slurm /
    Parallel Works execution does not rely on these script names and instead
    uses its own submission configuration.

    :param job_type: Normalized job type string
    :param payload: Job-specific execution payload
    :return: Script name to pass into the runtime container
    """
    if job_type == "validation" and payload.get("worker_name") and payload.get("iteration") is not None:
        return "validation_iteration"
    return job_type


def build_docker_command(job_type: str, run_id: int, payload: dict[str, Any]) -> list[str]:
    """
    Build the full Docker command used to launch a job.

    This selects the configured runtime command template, derives the script
    name from the job type, assigns a deterministic container name, and appends
    the job-specific arguments expected by the container entrypoint.

    :param job_type: Normalized job type string
    :param run_id: Run identifier
    :param payload: Job-specific execution payload
    :return: Full command as a list suitable for subprocess.Popen
    :raises ValueError: If job_type is unsupported
    """
    script_name = get_script_name(job_type, payload)
    template = RUNTIME_INFO[script_name]
    container_name = get_registry_key(job_type, run_id)

    spawn_command = template.format(name=container_name).split()

    if job_type == "calibration":
        payload_values = [
            payload["input_file"],
        ]
        stdout_file = payload["output_file"]

    elif job_type == "validation":
        if payload.get("worker_name") and payload.get("iteration") is not None:
            payload_values = [
                payload["input_file"],
                payload["worker_name"],
                str(payload["iteration"]),
            ]
        else:
            payload_values = [
                payload["input_file"],
            ]
        stdout_file = payload["output_file"]

    elif job_type == "cold_start":
        payload_values = [
            payload["validation_yaml"],
            payload["realization_file"],
        ]
        stdout_file = payload["stdout_file"]

    elif job_type == "forecast":
        payload_values = [
            payload["validation_yaml"],
            payload["realization_file"],
        ]
        stdout_file = payload["stdout_file"]

    elif job_type == "hindcast":
        payload_values = [
            payload["validation_yaml"],
            payload["config_file"],
            payload["run_name"],
            str(payload["interval_cycle"]),
            str(payload["num_iterations"]),
            payload["use_state"],
        ]
        stdout_file = payload["stdout_file"]

    elif job_type == "verification":
        payload_values = [
            payload["verification_config"],
        ]
        stdout_file = payload["stdout_file"]

    else:
        raise ValueError(f"Unsupported job_type: {job_type}")

    return spawn_command + [script_name] + payload_values + [stdout_file]


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


def docker_job_done_callback(
        job_type: str,
        run_id: int,
) -> Callable[[Future], None]:
    """
    Return the completion callback for a running Docker job.

    The returned callback:
    - removes the job from the in-memory registry
    - inspects the process exit code
    - publishes the corresponding terminal job event

    Exit-code handling:
    - 0      -> DONE
    - < 0    -> CANCELED
    - > 0    -> FAILED

    If callback processing itself fails, a best-effort FAILED event is published.

    :param job_type: Normalized job type string
    :param run_id: Run identifier
    :return: Completion callback for the submitted Future
    """

    def _callback(future: Future) -> None:
        registry_key = get_registry_key(job_type, run_id)
        job_registry.pop(registry_key, None)

        try:
            exit_code = future.result()

            if exit_code == 0:
                status = SlurmCallbackStatusEnum.DONE
            elif exit_code < 0:
                status = SlurmCallbackStatusEnum.CANCELED
            else:
                status = SlurmCallbackStatusEnum.FAILED

            publish_terminal_job_event(job_type, run_id, status)

        except Exception:
            logger.exception(
                "DOCKER job completion callback failed for job_type=%s run_id=%s",
                job_type,
                run_id,
            )
            publish_terminal_job_event(
                job_type,
                run_id,
                SlurmCallbackStatusEnum.FAILED,
            )

    return _callback


def run_docker_job(job_type: str, run_id: int, payload: dict[str, Any]) -> None:
    """
    Launch a job in Docker and register lifecycle handling.

    This function:
    - builds the Docker command
    - starts the subprocess
    - stores the process in the in-memory registry
    - publishes a STARTING job event
    - waits for completion in a background thread
    - attaches a completion callback that publishes the terminal event

    Lifecycle events are published back to Django through RabbitMQ rather than
    through HTTP callback endpoints.

    :param job_type: Normalized job type string
    :param run_id: Run identifier
    :param payload: Job-specific execution payload
    """
    command = build_docker_command(job_type, run_id, payload)

    logger.info(
        "Launching DOCKER job for job_type=%s run_id=%s command=%s",
        job_type,
        run_id,
        command,
    )

    env = os.environ.copy()
    env["WGRIB2"] = os.path.expanduser("~/miniconda3/envs/NextGen_Forcings_Engine/bin/wgrib2")

    process = subprocess.Popen(command, env=env)

    registry_key = get_registry_key(job_type, run_id)
    job_registry[registry_key] = process

    publish_job_event(
        job_type=job_type,
        run_id=run_id,
        job_status=SlurmCallbackStatusEnum.STARTING,
        slurm_job_id=None,
    )

    future = pool.submit(process.wait)
    future.add_done_callback(
        docker_job_done_callback(job_type, run_id)
    )


def cancel_docker_job(job_type: str, run_id: int) -> bool:
    """
    Attempt to cancel a running Docker job.

    Cancellation is performed with `docker kill <container_name>`, where the
    container name matches the internal registry key. On successful kill, the
    job is removed from the in-memory registry.

    :param job_type: Normalized job type string
    :param run_id: Run identifier
    :return: True if the container was killed successfully, otherwise False
    """
    registry_key = get_registry_key(job_type, run_id)
    container_name = registry_key

    logger.info(
        "Cancelling DOCKER job for job_type=%s run_id=%s container_name=%s",
        job_type,
        run_id,
        container_name,
    )

    result = subprocess.run(
        ["docker", "kill", container_name],
        check=False,
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        logger.info(
            "Container %s killed successfully for job_type=%s run_id=%s",
            container_name,
            job_type,
            run_id,
        )
        job_registry.pop(registry_key, None)
        return True

    logger.warning(
        "Failed to kill container %s for job_type=%s run_id=%s: %s",
        container_name,
        job_type,
        run_id,
        result.stderr.strip(),
    )
    return False


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

    return True


def dispatch_message(body: dict[str, Any]) -> None:
    """
    Dispatch a validated inbound message to the appropriate execution handler.

    Supported message types:
    - submit_job
    - cancel_job

    Routing is based on both message_type and the configured execution mode.

    :param body: Incoming message body deserialized from RabbitMQ
    """
    validate_message(body)

    message_type = body["message_type"]
    job_type = body["job_type"]
    run_id = body["run_id"]

    logger.info(
        "Dispatching message_type=%s job_type=%s run_id=%s environment=%s",
        message_type,
        job_type,
        run_id,
        JOB_EXECUTION_MODE,
    )

    if message_type == "submit_job":
        payload = body["payload"]

        if JOB_EXECUTION_MODE == JobExecutionMode.DOCKER:
            run_docker_job(job_type, run_id, payload)
            return

        if JOB_EXECUTION_MODE == JobExecutionMode.PARALLEL_WORKS:
            submit_slurm_job(job_type, run_id, payload)
            return

        raise ValueError(f"Unsupported consumer environment: {JOB_EXECUTION_MODE}")

    if message_type == "cancel_job":
        if JOB_EXECUTION_MODE == JobExecutionMode.DOCKER:
            if not cancel_docker_job(job_type, run_id):
                raise ValueError(
                    f"Unable to cancel DOCKER job for job_type={job_type} run_id={run_id}"
                )
            return

        if JOB_EXECUTION_MODE == JobExecutionMode.PARALLEL_WORKS:
            slurm_job_id_raw = body.get("slurm_job_id")
            if slurm_job_id_raw is None:
                raise ValueError(
                    f"Missing slurm_job_id for PARALLEL_WORKS cancel "
                    f"(job_type={job_type}, run_id={run_id})"
                )
            if not isinstance(slurm_job_id_raw, int):
                raise ValueError(
                    f"slurm_job_id must be an integer for PARALLEL_WORKS cancel "
                    f"(job_type={job_type}, run_id={run_id})"
                )

            if not cancel_slurm_job(job_type, run_id, slurm_job_id_raw):
                raise ValueError(
                    f"Unable to cancel PARALLEL_WORKS job for job_type={job_type} run_id={run_id}"
                )
            return

        raise ValueError(f"Unsupported consumer environment: {JOB_EXECUTION_MODE}")

    raise ValueError(f"Unsupported message_type: {message_type}")
