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

    if message["message_type"] not in {"submit_slurm_job", "cancel_job"}:
        raise ValueError(f"Invalid message_type: {message['message_type']}")

    if not isinstance(message["version"], int):
        raise ValueError("version must be an integer")

    if not isinstance(message["job_type"], str):
        raise ValueError("job_type must be a string")

    if not isinstance(message["run_id"], int):
        raise ValueError("run_id must be an integer")

    if not isinstance(message["submitted_at"], str):
        raise ValueError("submitted_at must be a string")

    if message["message_type"] == "submit_slurm_job":
        if "payload" not in message:
            raise ValueError("Missing required key: payload")
        if not isinstance(message["payload"], dict):
            raise ValueError("payload must be a dictionary")


def get_registry_key(job_type: str, run_id: int) -> str:
    return f"{job_type}_{run_id}"


def get_script_name(job_type: str, payload: dict[str, Any]) -> str:
    """
    Match the old script selection logic.

    Validation iteration uses a different script name than other validation jobs.
    """
    if job_type == "validation" and payload.get("worker_name") and payload.get("iteration") is not None:
        return "validation_iteration"
    return job_type


def build_docker_command(job_type: str, run_id: int, payload: dict[str, Any]) -> list[str]:
    """
    Build the docker command for the given job.

    This mirrors the spirit of your current Django-side DOCKER path, where
    the command is chosen by run type and uses a generated container name.
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

    Expected payload shape matches JobEventSerializer on the server side.
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


def docker_job_done_callback(
        job_type: str,
        run_id: int,
) -> Callable[[Future], None]:
    def _callback(future: Future) -> None:
        registry_key = get_registry_key(job_type, run_id)
        job_registry.pop(registry_key, None)

        try:
            exit_code = future.result()
            logger.info(
                "DOCKER job finished for job_type=%s run_id=%s exit_code=%s",
                job_type,
                run_id,
                exit_code,
            )

            if exit_code == 0:
                publish_job_event(
                    job_type=job_type,
                    run_id=run_id,
                    job_status=SlurmCallbackStatusEnum.DONE,
                    slurm_job_id=None,
                )
            elif exit_code < 0:
                publish_job_event(
                    job_type=job_type,
                    run_id=run_id,
                    job_status=SlurmCallbackStatusEnum.CANCELED,
                    slurm_job_id=None,
                )
            else:
                publish_job_event(
                    job_type=job_type,
                    run_id=run_id,
                    job_status=SlurmCallbackStatusEnum.FAILED,
                    slurm_job_id=None,
                )

        except Exception:
            logger.exception(
                "DOCKER job completion callback failed for job_type=%s run_id=%s",
                job_type,
                run_id,
            )
            try:
                publish_job_event(
                    job_type=job_type,
                    run_id=run_id,
                    job_status=SlurmCallbackStatusEnum.FAILED,
                    slurm_job_id=None,
                )
            except Exception:
                logger.exception(
                    "Failed publishing terminal FAILED event for job_type=%s run_id=%s",
                    job_type,
                    run_id,
                )

    return _callback


def run_docker_job(job_type: str, run_id: int, payload: dict[str, Any]) -> None:
    """
    Launch the Docker job using the same general pattern as the old spawn_job():
    - Popen
    - pool.submit(process.wait)
    - registry entry
    - done callback

    Job lifecycle updates are now published to RabbitMQ instead of being sent
    to Django callback endpoints over HTTP.
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
    Cancel a running Docker job.

    use `docker kill <container_name>` where the container name matches the
    registry key, and remove the registry entry on success.
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


def submit_parallel_works_job(job_type: str, run_id: int, payload: dict[str, Any]) -> None:
    """
    PARALLEL_WORKS path:
    stub only for now.

    Later this should:
      1. submit to Slurm
      2. obtain slurm_job_id
      3. publish SUBMITTED with slurm_job_id to job_events_queue
      4. later publish STARTING / terminal status updates
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


def dispatch_message(body: dict[str, Any]) -> None:
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

    if message_type == "submit_slurm_job":
        payload = body["payload"]

        if JOB_EXECUTION_MODE == JobExecutionMode.DOCKER:
            run_docker_job(job_type, run_id, payload)
            return

        if JOB_EXECUTION_MODE == JobExecutionMode.PARALLEL_WORKS:
            submit_parallel_works_job(job_type, run_id, payload)
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
            raise NotImplementedError("cancel_job is not yet implemented for PARALLEL_WORKS")

        raise ValueError(f"Unsupported consumer environment: {JOB_EXECUTION_MODE}")

    raise ValueError(f"Unsupported message_type: {message_type}")
