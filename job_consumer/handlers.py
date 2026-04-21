import logging
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Any, Callable

import requests

from job_consumer.config import JOB_EXECUTIION_MODE, RUNTIME_INFO, CERF_SERVER_URL
from job_consumer.job_consumer_enums import JobExecutionMode, SlurmCallbackStatusEnum

logger = logging.getLogger(__name__)

pool: ThreadPoolExecutor = ThreadPoolExecutor()
job_registry: dict[str, subprocess.Popen] = {}

# Replace these paths if your actual URL paths differ.
CALLBACK_PATHS = {
    "calibration": "/calibration/calibration_job_slurm_callback/",
    "validation": "/calibration/validation_job_slurm_callback/",
    "cold_start": "/calibration/cold_start_job_slurm_callback/",
    "forecast": "/calibration/forecast_job_slurm_callback/",
    "hindcast": "/calibration/hindcast_job_slurm_callback/",
    "verification": "/calibration/verification_job_slurm_callback/",
}

RUN_ID_FIELD_NAMES = {
    "calibration": "calibration_run_id",
    "validation": "validation_run_id",
    "cold_start": "cold_start_run_id",
    "forecast": "forecast_run_id",
    "hindcast": "hindcast_run_id",
    "verification": "verification_run_id",
}


def validate_message(message: dict[str, Any]) -> None:
    required_top_level = [
        "message_type",
        "version",
        "job_type",
        "run_id",
        "auth_token",
        "submitted_at",
        "payload",
    ]

    for key in required_top_level:
        if key not in message:
            raise ValueError(f"Missing required key: {key}")

    if message["message_type"] != "submit_slurm_job":
        raise ValueError(f"Invalid message_type: {message['message_type']}")

    if not isinstance(message["version"], int):
        raise ValueError("version must be an integer")

    if not isinstance(message["job_type"], str):
        raise ValueError("job_type must be a string")

    if not isinstance(message["run_id"], int):
        raise ValueError("run_id must be an integer")

    if not isinstance(message["auth_token"], str):
        raise ValueError("auth_token must be a string")

    if not isinstance(message["submitted_at"], str):
        raise ValueError("submitted_at must be a string")

    if not isinstance(message["payload"], dict):
        raise ValueError("payload must be a dictionary")


def get_registry_key(job_type: str, run_id: int) -> str:
    name_map = {
        "calibration": "calibrationrun",
        "validation": "validationrun",
        "cold_start": "coldstartrun",
        "forecast": "forecastrun",
        "hindcast": "hindcastrun",
        "verification": "verificationrun",
    }
    return f"{name_map[job_type]}_{run_id}"


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

    # Keep argument ordering explicit and per-job-type.
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


def post_job_callback(
        job_type: str,
        run_id: int,
        job_status: SlurmCallbackStatusEnum,
        auth_token: str,
        slurm_job_id: int | None = None,
) -> None:
    """
    Call the Django callback endpoint for the given job type.

    For DOCKER jobs, slurm_job_id should normally be None.
    """
    if not CERF_SERVER_URL:
        raise RuntimeError("CERF_SERVER_URL is not configured")

    try:
        callback_path = CALLBACK_PATHS[job_type]
        run_id_field = RUN_ID_FIELD_NAMES[job_type]
    except KeyError as e:
        raise ValueError(f"Unsupported job_type for callback: {job_type}") from e

    url = f"{CERF_SERVER_URL.rstrip('/')}{callback_path}"
    payload = {
        run_id_field: run_id,
        "job_status": job_status.value,
        "slurm_job_id": slurm_job_id,
    }

    logger.info(
        "Posting callback to server for job_type=%s run_id=%s status=%s url=%s",
        job_type,
        run_id,
        job_status.value,
        url,
    )
    logger.debug("Callback payload: %s", payload)

    try:
        response = requests.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=30,
        )
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        response = e.response
        response_text = response.text if response is not None else "<no response body>"

        logger.error(
            "Callback HTTP error for job_type=%s run_id=%s status=%s url=%s "
            "status_code=%s response=%s",
            job_type,
            run_id,
            job_status.value,
            url,
            response.status_code if response is not None else "<unknown>",
            response_text,
        )
        raise
    except requests.exceptions.RequestException:
        logger.exception(
            "Callback request failed for job_type=%s run_id=%s status=%s url=%s",
            job_type,
            run_id,
            job_status.value,
            url,
        )
        raise


def docker_job_done_callback(
        job_type: str,
        run_id: int,
        auth_token: str,
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
                post_job_callback(
                    job_type=job_type,
                    run_id=run_id,
                    job_status=SlurmCallbackStatusEnum.DONE,
                    auth_token=auth_token,
                    slurm_job_id=None,
                )
            else:
                # You may later want special handling for cancel-related exit codes.
                post_job_callback(
                    job_type=job_type,
                    run_id=run_id,
                    job_status=SlurmCallbackStatusEnum.FAILED,
                    auth_token=auth_token,
                    slurm_job_id=None,
                )

        except Exception:
            logger.exception(
                "DOCKER job completion callback failed for job_type=%s run_id=%s",
                job_type,
                run_id,
            )
            try:
                post_job_callback(
                    job_type=job_type,
                    run_id=run_id,
                    job_status=SlurmCallbackStatusEnum.FAILED,
                    auth_token=auth_token,
                    slurm_job_id=None,
                )
            except Exception:
                logger.exception(
                    "Failed posting terminal FAILED callback for job_type=%s run_id=%s",
                    job_type,
                    run_id,
                )

    return _callback


def run_docker_job(job_type: str, run_id: int, payload: dict[str, Any], auth_token: str) -> None:
    """
    Launch the Docker job using the same general pattern as the old spawn_job():
    - Popen
    - pool.submit(process.wait)
    - registry entry
    - done callback

    The difference is that completion is now reported back to Django through
    callback endpoints instead of local callback functions.
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

    # Notify Django that the job has started.
    post_job_callback(
        job_type=job_type,
        run_id=run_id,
        job_status=SlurmCallbackStatusEnum.STARTING,
        auth_token=auth_token,
        slurm_job_id=None,
    )

    future = pool.submit(process.wait)
    future.add_done_callback(
        docker_job_done_callback(job_type, run_id, auth_token)
    )


def submit_parallel_works_job(job_type: str, run_id: int, payload: dict[str, Any], auth_token: str) -> None:
    """
    PARALLEL_WORKS path:
    stub only for now.

    Later this should:
      1. submit to Slurm
      2. obtain slurm_job_id
      3. callback Django with job_status='Submitted' and slurm_job_id
      4. later callback with Starting / terminal status updates
    """
    logger.info(
        "PARALLEL_WORKS stub for job_type=%s run_id=%s payload=%s",
        job_type,
        run_id,
        payload,
    )

    # TODO: submit to Slurm
    # TODO: get slurm_job_id
    # TODO: callback Django with submission acknowledgement


def dispatch_message(body: dict[str, Any]) -> None:
    validate_message(body)

    job_type = body["job_type"]
    run_id = body["run_id"]
    auth_token = body["auth_token"]
    payload = body["payload"]

    logger.info(
        "Dispatching job_type=%s run_id=%s environment=%s",
        job_type,
        run_id,
        JOB_EXECUTIION_MODE,
    )

    if JOB_EXECUTIION_MODE == JobExecutionMode.DOCKER:
        run_docker_job(job_type, run_id, payload, auth_token)
        return

    if JOB_EXECUTIION_MODE == JobExecutionMode.PARALLEL_WORKS:
        submit_parallel_works_job(job_type, run_id, payload, auth_token)
        return

    raise ValueError(f"Unsupported consumer environment: {JOB_EXECUTIION_MODE}")
