import logging
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Any, Callable

from job_runner.config import RUNTIME_INFO
from job_runner.job_executor_common import publish_job_event, publish_terminal_job_event
from job_runner.job_runner_enums import SlurmCallbackStatusEnum

logger = logging.getLogger(__name__)

pool: ThreadPoolExecutor = ThreadPoolExecutor()
job_registry: dict[str, subprocess.Popen] = {}


def handle_docker_message(body: dict[str, Any]) -> None:
    """
    Handle a validated message using the Docker execution backend.

    :param body: Incoming message body deserialized from RabbitMQ
    :raises ValueError: If the message_type is unsupported or cancellation fails
    """
    message_type = body["message_type"]
    job_type = body["job_type"]
    run_id = body["run_id"]

    if message_type == "submit_job":
        run_docker_job(job_type, run_id, body["payload"])
        return

    if message_type == "cancel_job":
        if not cancel_docker_job(job_type, run_id):
            raise ValueError(
                f"Unable to cancel DOCKER job for job_type={job_type} run_id={run_id}"
            )
        return

    raise ValueError(f"Unsupported message_type: {message_type}")


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
