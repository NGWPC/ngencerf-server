"""
Slurm execution backend.

Responsibilities:

- Building Singularity commands
- Generating Slurm batch scripts
- Submitting jobs with sbatch
- Cancelling jobs with scancel
- Sending lifecycle callbacks to Django

Deployment usage:

- Used primarily in deployed AWS PCS / HPC environments
- Requires the Django runtime to be configured as a Slurm submit client
- Requires sbatch/scancel on the Django runtime PATH
- Requires shared filesystem access between Django and Slurm compute nodes
- Job execution occurs asynchronously on Slurm compute resources

This module answers:

    "How does Slurm execute this job?"
"""

import logging
import os
import subprocess
from typing import Any

from django.conf import settings

from calibration.enums import SlurmCallbackStatusEnum
from calibration.enums_vanilla import JobExecutionMode
from calibration.run_util.job_lifecycle import handle_job_event
from calibration.run_util.job_runtime_mapping import get_job_runtime_details

logger = logging.getLogger(__name__)

# Optional sacct columns collected after job completion (depends on Slurm version)
SLURM_JOB_METRICS = os.environ.get('SLURM_JOB_METRICS')


def ensure_file_owned(file_path: str) -> dict[str, bool | str]:
    """
    Ensure the current user can write to the target file path.

    # TODO This was needed on Parallel Works.  Not sure if it will be a problem on other environments

    Creates the parent directory if needed, changes ownership of the parent
    directory to the current user/group, and creates the file if it does not
    already exist.

    :param file_path: Local filesystem path to prepare
    :return: Result dictionary containing success flag and message
    """
    try:
        current_uid = os.getuid()
        current_gid = os.getgid()
        file_path_dir = os.path.dirname(file_path)
        subprocess.run(f"sudo mkdir -p {file_path_dir}", shell=True, check=True)
        command_chown = f"sudo chown {current_uid}:{current_gid} {file_path_dir}"
        subprocess.run(command_chown, shell=True, check=True)
        subprocess.run(f"touch {file_path}", shell=True, check=True)
        logger.info(f"Ownership granted to file {file_path}")
        return {"success": True, "message": f"Access granted to {file_path}"}
    except subprocess.CalledProcessError as e:
        logger.exception(f"Failed to change ownership of file {file_path}")
        return {"success": False, "message": str(e)}


def build_slurm_command(
        job_type: str,
        payload: dict[str, Any],
) -> tuple[str, str, str, str | None, int | str]:
    """
    Build the Singularity command and Slurm submission metadata.

    Slurm uses the same runtime argument mapping as Docker, but wraps those
    arguments in a Singularity command instead of a Docker command.

    :param job_type: Normalized job type string.
    :param payload: Job-specific execution payload.
    :return: Tuple of singularity_run_cmd, input_file, stdout_file, node_type, and nprocs.
    :raises KeyError: If required payload fields are missing.
    :raises ValueError: If job_type is unsupported.
    """
    script_name, payload_values, input_file, stdout_file, node_type, nprocs = get_job_runtime_details(
        job_type,
        payload
    )

    template = settings.SINGULARITY_RUNTIME_INFO[script_name]
    singularity_run_cmd = " ".join([template, script_name, *payload_values])

    return singularity_run_cmd, input_file, stdout_file, node_type, nprocs


def get_callback_run_id_field(job_type: str) -> str:
    """
    Return the callback request field name that identifies the run.

    Each Slurm callback endpoint expects a job-specific run id field, such as
    calibration_run_id or forecast_run_id.

    :param job_type: Normalized job type string.
    :return: Callback payload field name containing the run id.
    :raises ValueError: If job_type is unsupported.
    """
    callback_id_fields = {
        "calibration": "calibration_run_id",
        "validation": "validation_run_id",
        "cold_start": "cold_start_run_id",
        "forecast": "forecast_run_id",
        "hindcast": "hindcast_run_id",
        "verification": "verification_run_id",
    }

    try:
        return callback_id_fields[job_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported job_type for callback: {job_type}") from exc


def get_callback_url(job_type: str) -> str:
    """
    Build the Django callback URL for a Slurm job type.

    The URL is derived from the configured server base URL plus the
    job-specific callback endpoint path.

    :param job_type: Normalized job type string.
    :return: Fully qualified callback URL for the job type.
    :raises ValueError: If job_type is unsupported.
    """
    callback_paths = {
        "calibration": "/calibration/calibration_job_slurm_callback/",
        "validation": "/calibration/validation_job_slurm_callback/",
        "cold_start": "/calibration/cold_start_job_slurm_callback/",
        "forecast": "/calibration/forecast_job_slurm_callback/",
        "hindcast": "/calibration/hindcast_job_slurm_callback/",
        "verification": "/calibration/verification_jobslurm_callback/",
    }

    try:
        callback_path = callback_paths[job_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported job_type for callback: {job_type}") from exc

    return f"{settings.NGENCERF_BASE_URL}{callback_path}"


def write_slurm_script(
        run_id: int,
        job_type: str,
        input_file_local: str,
        output_file_local: str,
        singularity_run_cmd: str,
        auth_token: str,
        nprocs: int | str = 1,
) -> str:
    """
    Write the Slurm batch script used to execute a job.

    The generated script:
    - notifies Django when Slurm starts the job
    - repairs ownership and permissions under the job directory
    - runs the Singularity command under Slurm CPU affinity
    - records optional Slurm accounting metrics
    - notifies Django with the terminal job status

    :param run_id: Run identifier.
    :param job_type: Normalized job type string.
    :param input_file_local: Input file path on the host/shared filesystem.
    :param output_file_local: Stdout file path on the host/shared filesystem.
    :param singularity_run_cmd: Full Singularity command to execute.
    :param auth_token: Per-job callback token generated by Django and embedded
        into the Slurm script for authenticated callback requests.
    :param nprocs: Number of CPUs requested for the job.
    :return: Path to the generated Slurm script.
    """

    # Use the stdout file basename to place the generated Slurm script beside the job log
    job_script = output_file_local.rsplit(".", 1)[0] + ".slurm.sh"

    # Repair permissions from the run directory level, not only the specific input file directory
    job_dir = os.path.dirname(os.path.dirname(input_file_local))

    # Performance metrics output alongside stdout log
    performance_file = output_file_local.replace("stdout", "performance")

    callback_url = get_callback_url(job_type)
    callback_run_id_field = get_callback_run_id_field(job_type)

    # Token is generated by Django per submission and embedded into this job script.
    callback_token = auth_token

    # Ensure script/log files are writable by the current user
    # ensure_file_owned(job_script)
    # ensure_file_owned(output_file_local)

    with open(job_script, "w") as script:
        script.write("#!/bin/bash\n")
        script.write(f"#SBATCH --job-name={job_type}-{run_id}\n")
        script.write("#SBATCH --nodes=1\n")
        script.write("#SBATCH --no-requeue\n")
        script.write("#SBATCH --ntasks=1\n")
        script.write(f"#SBATCH --cpus-per-task={nprocs}\n")
        script.write(f"#SBATCH --output={output_file_local}\n")
        script.write("\n")
        script.write("set +e\n\n")

        script.write(f'CALLBACK_URL="{callback_url}"\n')
        script.write(f'CALLBACK_TOKEN="{callback_token}"\n')
        script.write(f'CALLBACK_RUN_ID_FIELD="{callback_run_id_field}"\n')
        script.write(f'RUN_ID="{run_id}"\n\n')

        script.write(
            """notify_job_event() {
    local job_status="$1"

    curl -fsS -X POST "$CALLBACK_URL" \\
        -H "Authorization: Bearer $CALLBACK_TOKEN" \\
        -H "Content-Type: application/json" \\
        --data "{
            \\"${CALLBACK_RUN_ID_FIELD}\\": ${RUN_ID},
            \\"job_status\\": \\"${job_status}\\",
            \\"slurm_job_id\\": ${SLURM_JOB_ID}
        }"

    if [ $? -ne 0 ]; then
        echo "WARNING: Failed to notify Django callback endpoint for status ${job_status}"
    fi
}

"""
        )

        script.write('echo "Running Slurm Job $SLURM_JOB_ID"\n\n')

        current_uid = os.getuid()
        current_gid = os.getgid()

        # Number of parallel workers used by xargs during permission repair.
        # Falls back to 8 if nproc is unavailable on the compute node.
        script.write('p="$(command -v nproc >/dev/null 2>&1 && nproc || echo 8)"\n')

        # Some run files may be owned by root or another account after prior
        # containerized steps. Reset ownership back to the current runner user.
        script.write(
            f'sudo find -L "{job_dir}" \\( ! -uid {current_uid} -o ! -gid {current_gid} \\) ! -type l -print0 '
            f'| sudo xargs -0 -r -P"$p" chown {current_uid}:{current_gid}\n\n'
        )

        # Ensure files are readable/writable and directories remain traversable.
        # a+rwX applies execute only where appropriate (dirs / existing executables).
        script.write(
            f'sudo find -L "{job_dir}" ! -type l '
            f'\\( ! -perm -u+r -o ! -perm -u+w -o \\( -xtype d ! -perm -u+x \\) \\) -print0 '
            f'| sudo xargs -0 -r -P"$p" chmod a+rwX\n\n'
        )

        script.write("notify_job_event STARTING\n\n")

        script.write("# Extract the exact CPUs Slurm assigned to this job\n")
        # Read the CPU affinity mask assigned by Slurm and convert it to a
        # comma-separated CPU list for taskset.
        script.write(
            'CPUSET=$(python3 -c "import os; '
            'print(*sorted(os.sched_getaffinity(0)), sep=\',\')")\n'
        )
        script.write('echo "Job isolated to CPUs: $CPUSET"\n\n')

        # Pass through OpenMPI override inside the Singularity container.
        script.write("export SINGULARITYENV_OMPI_MCA_rmaps_base_oversubscribe=1\n\n")

        # Force the workload to stay inside the CPUs Slurm granted this job.
        modified_singularity_run_cmd = f'taskset -c "${{CPUSET}}" {singularity_run_cmd}'
        script.write(f"{modified_singularity_run_cmd}\n")
        script.write("exit_code=$?\n\n")

        script.write('if [ "$exit_code" -eq 0 ]; then\n')
        script.write('    job_status="DONE"\n')
        script.write("else\n")
        script.write('    job_status="FAILED"\n')
        script.write("fi\n\n")

        script.write('echo "Job completed with status $job_status and exit_code=$exit_code"\n\n')

        if SLURM_JOB_METRICS:
            # Give Slurm accounting a moment to flush final metrics before sacct.
            script.write("sleep 5\n")

            # Write configured accounting fields to the paired performance file.
            script.write(
                f"sacct -j $SLURM_JOB_ID "
                f"-o {SLURM_JOB_METRICS} "
                f"--parsable --units=K > {performance_file}\n\n"
            )

        script.write('notify_job_event "$job_status"\n')
        script.write("exit $exit_code\n")

    return job_script


def _run_sbatch(
        job_script: str,
        partition: str | None = None,
) -> tuple[str | None, str | None]:
    """
    Submit a Slurm script with sbatch.

    :param job_script: Path to the generated Slurm script
    :param partition: Optional Slurm partition name
    :return: Tuple of slurm_job_id and error message
    """
    try:
        command = ["sbatch"]

        if partition:
            command += ["--partition", partition]

        command.append(job_script)

        logger.info('Running command: ' + ' '.join(command))
        result = subprocess.run(command, capture_output=True, text=True)

        if result.returncode != 0:
            error_msg = f"Failed to submit job script {job_script} with  command {command}: {result.stderr.strip()}"
            logger.error(error_msg)
            return None, error_msg

        slurm_job_id = result.stdout.strip().split()[-1]
        return slurm_job_id, None
    except Exception as e:
        error_msg = f"Failed to submit job script {job_script}: {str(e)}"
        logger.exception(error_msg)
        return None, error_msg


def submit_job(
        job_type: str,
        run_id: int,
        payload: dict[str, Any],
) -> str:
    """
    Submit a prepared job to Slurm.

    Resolves the Singularity command, converts container paths to host/shared
    filesystem paths, validates the selected Slurm partition, writes the Slurm
    script, submits it with sbatch, and returns the Slurm job id.

    In SLURM_MOCK mode, the script is written but sbatch is skipped.

    :param job_type: Normalized job type string.
    :param run_id: Run identifier.
    :param payload: Job-specific execution payload. Must include auth_token.
    :return: Slurm job id as a string. In SLURM_MOCK mode, returns "-1".
    :raises RuntimeError: If validation, script generation, or sbatch fails.
    :raises ValueError: If node_type is not an allowed Slurm partition.
    """
    logger.info("Starting Slurm job submission for job_type=%s run_id=%s", job_type, run_id)

    if not settings.HOST_DATA_ROOT:
        raise RuntimeError("HOST_DATA_ROOT is not configured")
    if not settings.CONTAINER_DATA_ROOT:
        raise RuntimeError("CONTAINER_DATA_ROOT is not configured")

    singularity_run_cmd, input_file, output_file, node_type, nprocs = build_slurm_command(
        job_type,
        payload,
    )

    input_file_local = input_file.replace(settings.CONTAINER_DATA_ROOT, settings.HOST_DATA_ROOT)
    output_file_local = output_file.replace(settings.CONTAINER_DATA_ROOT, settings.HOST_DATA_ROOT)

    if not os.path.exists(input_file_local):
        error_msg = (
            f"File path '{input_file_local}' does not exist on the shared "
            f"filesystem under {settings.HOST_DATA_ROOT}."
        )
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    if node_type and node_type not in settings.SLURM_PARTITIONS:
        raise ValueError(
            f"node_type {node_type} does not match any configured Slurm partitions: "
            f"{settings.SLURM_PARTITIONS}"
        )

    try:
        auth_token = payload.get("auth_token")

        if not isinstance(auth_token, str):
            raise RuntimeError(
                f"auth_token is required for Slurm callbacks "
                f"(job_type={job_type}, run_id={run_id})"
            )

        job_script = write_slurm_script(
            run_id=run_id,
            job_type=job_type,
            input_file_local=input_file_local,
            output_file_local=output_file_local,
            singularity_run_cmd=singularity_run_cmd,
            auth_token=auth_token,
            nprocs=nprocs,
        )

        logger.info("Job script written to: %s", job_script)

        if settings.JOB_EXECUTION_MODE == JobExecutionMode.SLURM_MOCK:
            logger.warning(
                "SLURM_MOCK mode enabled; skipping sbatch submission for "
                "job_type=%s run_id=%s. Generated script: %s",
                job_type,
                run_id,
                job_script,
            )
            return "-1"

        slurm_job_id, error = _run_sbatch(job_script, partition=node_type)
        if error:
            raise RuntimeError(error)
        assert slurm_job_id is not None

        return slurm_job_id

    except RuntimeError:
        raise
    except Exception as e:
        error_msg = f"Failed to submit Slurm job: {str(e)}"
        logger.exception(error_msg)
        raise RuntimeError(error_msg)


def submit_slurm_job(job_type: str, run_id: int, payload: dict[str, Any]) -> int:
    """
    Submit a job through the Slurm execution path.

    Lifecycle flow:

    1. Django submits job and persists slurm_job_id.

    2. Generated Slurm script invokes callback endpoint with:
       STARTING

    3. Generated Slurm script invokes callback endpoint with:
       DONE / FAILED / CANCELED

    The callback endpoint updates lifecycle state and triggers
    post-processing.

    :param job_type: Normalized job type string
    :param run_id: Run identifier
    :param payload: Job-specific execution payload
    """
    slurm_job_id_str = submit_job(job_type, run_id, payload)
    slurm_job_id = int(slurm_job_id_str)

    logger.info(
        "Submitted job_type=%s run_id=%s slurm_job_id=%s",
        job_type,
        run_id,
        slurm_job_id,
    )

    return slurm_job_id


def cancel_slurm_job(
        job_type: str,
        run_id: int,
        slurm_job_id: int,
) -> bool:
    """
    Cancel a job through the Slurm execution path.

    Runs scancel and sends a terminal CANCELED lifecycle event on success.

    A failed scancel request does not mean the job failed; it only means the
    cancellation request was not accepted.

    :param job_type: Normalized job type string
    :param run_id: Run identifier
    :param slurm_job_id: Slurm job identifier (required)
    :return: True if cancellation succeeded, False otherwise
    :raises ValueError: If slurm_job_id is None
    """
    if slurm_job_id is None:
        raise ValueError(
            f"slurm_job_id is required for Slurm cancellation "
            f"(job_type={job_type}, run_id={run_id})"
        )

    logger.info(
        "SLURM cancel request for job_type=%s run_id=%s slurm_job_id=%s",
        job_type,
        run_id,
        slurm_job_id,
    )

    # scancel requests cancellation asynchronously through Slurm
    result = subprocess.run(
        ["scancel", str(slurm_job_id)],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        logger.error(
            "scancel failed for job_type=%s run_id=%s slurm_job_id=%s: %s",
            job_type,
            run_id,
            slurm_job_id,
            result.stderr.strip()
        )
        return False

    handle_job_event(
        job_type=job_type,
        run_id=run_id,
        job_status=SlurmCallbackStatusEnum.CANCELED,
        slurm_job_id=slurm_job_id,
    )

    return True
