import logging
import os
import socket
import subprocess
from typing import Any

from job_runner.job_executor_common import publish_job_event, publish_terminal_job_event
from job_runner.job_runner_enums import SlurmCallbackStatusEnum

logger = logging.getLogger(__name__)

CONTROLLER_HOSTNAME = socket.gethostname()
LOCAL_DATA_DIR = os.environ.get('LOCAL_DATA_DIR')
CONTAINER_DATA_DIR = os.environ.get('CONTAINER_DATA_DIR')
NWM_CAL_MGR_SINGULARITY_CONTAINER_PATH = os.environ.get('nwm_cal_mgr_singularity_container_path')
NWM_FCST_MGR_SINGULARITY_CONTAINER_PATH = os.environ.get('nwm_fcst_mgr_singularity_container_path')
NWM_VERF_SINGULARITY_CONTAINER_PATH = os.environ.get('nwm_verf_singularity_container_path')
NGENCERF_URL = f"http://{CONTROLLER_HOSTNAME}:8000"
SINGULARITY_RUN_NWM_CAL_MGR_CMD = f"/usr/bin/time -v singularity run -B {LOCAL_DATA_DIR}:{CONTAINER_DATA_DIR} --env NGENCERF_URL={NGENCERF_URL} {NWM_CAL_MGR_SINGULARITY_CONTAINER_PATH}"
SINGULARITY_RUN_NWM_FCST_MGR_CMD = f"/usr/bin/time -v singularity run -B {LOCAL_DATA_DIR}:{CONTAINER_DATA_DIR} --env NGENCERF_URL={NGENCERF_URL} {NWM_FCST_MGR_SINGULARITY_CONTAINER_PATH}"
SINGULARITY_RUN_NWM_VERF_CMD = f"/usr/bin/time -v singularity run -B {LOCAL_DATA_DIR}:{CONTAINER_DATA_DIR} --env NGENCERF_URL={NGENCERF_URL} {NWM_VERF_SINGULARITY_CONTAINER_PATH}"
PARTITIONS_STR = os.environ.get('PARTITIONS')
PARTITIONS = PARTITIONS_STR.split(',')
SLURM_JOB_METRICS = os.environ.get('SLURM_JOB_METRICS')

_PUBLISH_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'publish_job_event.py')


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


def ensure_file_owned(file_path: str):
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


def write_slurm_script(run_id, job_type, input_file_local, output_file_local, singularity_run_cmd, nprocs=1):
    job_script = output_file_local.rsplit('.', 1)[0] + '.slurm.sh'
    job_dir = os.path.dirname(os.path.dirname(input_file_local))
    performance_file = output_file_local.replace('stdout', 'performance')

    rabbitmq_url = os.environ.get('RABBITMQ_URL', '')
    rabbitmq_queue = os.environ.get('RABBITMQ_JOB_EVENTS_QUEUE', 'job_events_queue')

    ensure_file_owned(job_script)
    ensure_file_owned(output_file_local)

    with open(job_script, 'w') as script:
        script.write('#!/bin/bash\n')
        script.write(f'#SBATCH --job-name={job_type}-{run_id}\n')
        script.write('#SBATCH --nodes=1\n')
        script.write('#SBATCH --no-requeue\n')
        script.write('#SBATCH --ntasks=1\n')
        script.write(f'#SBATCH --cpus-per-task={nprocs}\n')
        script.write(f'#SBATCH --output={output_file_local}\n')
        script.write('\n')

        script.write('echo Running Job $SLURM_JOB_ID \n\n')

        script.write(f'export RABBITMQ_URL="{rabbitmq_url}"\n')
        script.write(f'export RABBITMQ_JOB_EVENTS_QUEUE="{rabbitmq_queue}"\n\n')

        current_uid = os.getuid()
        current_gid = os.getgid()

        script.write('p="$(command -v nproc >/dev/null 2>&1 && nproc || echo 8)"\n')

        script.write(
            f'sudo find -L "{job_dir}" \\( ! -uid {current_uid} -o ! -gid {current_gid} \\) ! -type l -print0 '
            f'| sudo xargs -0 -r -P"$p" chown {current_uid}:{current_gid}\n\n'
        )

        script.write(
            f'sudo find -L "{job_dir}" ! -type l '
            f'\\( ! -perm -u+r -o ! -perm -u+w -o \\( -xtype d ! -perm -u+x \\) \\) -print0 '
            f'| sudo xargs -0 -r -P"$p" chmod a+rwX\n\n'
        )

        notify_job_start_cmd = (
            f'python3 {_PUBLISH_SCRIPT} '
            f'--job_type {job_type} --run_id {run_id} '
            f'--job_status STARTING --slurm_job_id $SLURM_JOB_ID\n'
        )
        script.write(notify_job_start_cmd)

        script.write('\n# Extract the exact CPUs Slurm assigned to this job\n')
        script.write('CPUSET=$(python3 -c "import os; print(*sorted(os.sched_getaffinity(0)), sep=\',\')")\n')
        script.write('echo "Job isolated to CPUs: $CPUSET"\n\n')

        script.write('export SINGULARITYENV_OMPI_MCA_rmaps_base_oversubscribe=1\n\n')

        modified_singularity_run_cmd = f'taskset -c "${{CPUSET}}" {singularity_run_cmd}'
        script.write(f'{modified_singularity_run_cmd}\n')

        script.write('if [ $? -eq 0 ]; then\n')
        script.write('    job_status="DONE"\n')
        script.write('else\n')
        script.write('    job_status="FAILED"\n')
        script.write('fi\n')
        script.write('echo\n\n')

        script.write('echo Job Completed with status $job_status\n')
        script.write('echo\n\n')

        if SLURM_JOB_METRICS:
            script.write(f'sleep 5\n')
            script.write(f'sacct -j $SLURM_JOB_ID -o {SLURM_JOB_METRICS} --parsable --units=K > {performance_file}\n\n')

        notify_job_end_cmd = (
            f'python3 {_PUBLISH_SCRIPT} '
            f'--job_type {job_type} --run_id {run_id} '
            f'--job_status ${{job_status}} --slurm_job_id $SLURM_JOB_ID\n'
        )
        script.write(notify_job_end_cmd)

    return job_script


def _run_sbatch(job_script, partition=None):
    """Submit a job script to SLURM and return the job ID. Optionally specify a partition."""
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


def submit_job(input_file, output_file, run_id, job_type, singularity_run_cmd, nprocs=1, partition=None):
    logger.info(f"Starting job submission for job run ID: {run_id}")
    input_file_local = input_file.replace(CONTAINER_DATA_DIR, LOCAL_DATA_DIR)
    output_file_local = output_file.replace(CONTAINER_DATA_DIR, LOCAL_DATA_DIR)
    if not os.path.exists(input_file_local):
        error_msg = f"File path '{input_file_local}' does not exist on the shared filesystem under {LOCAL_DATA_DIR}."
        logger.exception(error_msg)
        raise RuntimeError(error_msg)

    try:
        job_script = write_slurm_script(run_id, job_type, input_file_local, output_file_local, singularity_run_cmd, nprocs=nprocs)
        logger.info(f"Job script written to: {job_script}")

        slurm_job_id, error = _run_sbatch(job_script, partition=partition)
        if error:
            raise RuntimeError(error)

        return slurm_job_id
    except RuntimeError:
        raise
    except Exception as e:
        error_msg = f"Failed to submit job: {str(e)}"
        logger.exception(error_msg)
        raise RuntimeError(error_msg)


def submit_calibration_job(run_id, payload):
    job_type = 'calibration'
    input_file = payload.get('input_file')
    output_file = payload.get('output_file')
    nprocs = payload.get('nprocs', '1')
    node_type = payload.get('node_type', None)

    if not input_file:
        raise ValueError("No ngen-cal input file provided")

    if not output_file:
        raise ValueError("No output_file provided")

    if node_type:
        if node_type not in PARTITIONS:
            raise ValueError(f"node_type {node_type} provided does not match any partitions {PARTITIONS_STR}")

    singularity_run_cmd = f"{SINGULARITY_RUN_NWM_CAL_MGR_CMD} calibration {input_file}"

    return submit_job(input_file, output_file, run_id, job_type, singularity_run_cmd, nprocs=nprocs, partition=node_type)


def submit_validation_job(run_id, payload):
    job_type = 'validation'
    input_file = payload.get('input_file')
    output_file = payload.get('output_file')
    validation_type = payload.get('validation_type')
    worker_name = payload.get('worker_name')
    iteration = payload.get('iteration')
    node_type = payload.get('node_type', None)
    nprocs = payload.get('nprocs', '1')

    if not input_file:
        raise ValueError("No ngen-cal input file provided")

    if not output_file:
        raise ValueError("No output_file provided")

    if node_type:
        if node_type not in PARTITIONS:
            raise ValueError(f"node_type {node_type} provided does not match any partitions {PARTITIONS_STR}")

    if validation_type == 'valid_iteration':
        if not worker_name:
            raise ValueError("No worker_name provided for validation_type 'valid_iteration'")
        if not iteration:
            raise ValueError("No iteration provided for validation_type 'valid_iteration'")

        try:
            int(iteration)
        except ValueError:
            raise ValueError("Invalid iteration provided; must be an integer")

    if validation_type in ['valid_control', 'valid_best']:
        singularity_run_cmd = f"{SINGULARITY_RUN_NWM_CAL_MGR_CMD} validation {input_file}"
    elif validation_type == 'valid_iteration':
        singularity_run_cmd = f"{SINGULARITY_RUN_NWM_CAL_MGR_CMD} validation_iteration {input_file} {worker_name} {iteration}"
    else:
        raise ValueError("Invalid validation_type provided; must be one of 'valid_control', 'valid_best', or 'valid_iteration'")

    return submit_job(input_file, output_file, run_id, job_type, singularity_run_cmd, nprocs=nprocs, partition=node_type)


def submit_forecast_job(run_id, payload):
    job_type = 'forecast'
    validation_yaml = payload.get('validation_yaml')
    realization_file = payload.get('realization_file')
    stdout_file = payload.get('stdout_file')

    if not validation_yaml:
        raise ValueError("No validation_yaml provided")

    if not realization_file:
        raise ValueError("No realization_file provided")

    if not stdout_file:
        raise ValueError("No stdout_file provided")

    singularity_run_cmd = f"{SINGULARITY_RUN_NWM_FCST_MGR_CMD} forecast {validation_yaml} {realization_file}"

    return submit_job(validation_yaml, stdout_file, run_id, job_type, singularity_run_cmd)


def submit_hindcast_job(run_id, payload):
    job_type = 'hindcast'
    validation_yaml = payload.get('validation_yaml')
    config_file = payload.get('config_file')
    run_name = payload.get('run_name')
    interval_cycle = payload.get('interval_cycle')
    num_iterations = payload.get('num_iterations')
    use_state = payload.get('use_state')
    stdout_file = payload.get('stdout_file')

    if not validation_yaml:
        raise ValueError("No validation_yaml provided")

    if not config_file:
        raise ValueError("No config_file provided")

    if not run_name:
        raise ValueError("No run_name provided")

    if not interval_cycle:
        raise ValueError("No interval_cycle provided")

    if not num_iterations:
        raise ValueError("No num_iterations provided")

    if not use_state:
        raise ValueError("No use_state provided")

    if not stdout_file:
        raise ValueError("No stdout_file provided")

    singularity_run_cmd = f"{SINGULARITY_RUN_NWM_FCST_MGR_CMD} hindcast {validation_yaml} {config_file} {run_name} {interval_cycle} {num_iterations} {use_state}"

    return submit_job(validation_yaml, stdout_file, run_id, job_type, singularity_run_cmd)


def submit_cold_start_job(run_id, payload):
    job_type = 'cold-start'
    validation_yaml = payload.get('validation_yaml')
    realization_file = payload.get('realization_file')
    stdout_file = payload.get('stdout_file')

    if not validation_yaml:
        raise ValueError("No validation_yaml provided")

    if not realization_file:
        raise ValueError("No realization_file provided")

    if not stdout_file:
        raise ValueError("No stdout_file provided")

    singularity_run_cmd = f"{SINGULARITY_RUN_NWM_FCST_MGR_CMD} cold_start {validation_yaml} {realization_file}"

    return submit_job(validation_yaml, stdout_file, run_id, job_type, singularity_run_cmd)


def submit_verification_job(run_id, payload):
    job_type = 'verification-job'
    verification_config = payload.get('verification_config')
    stdout_file = payload.get('stdout_file')

    if not verification_config:
        raise ValueError("No verification_config provided")

    if not stdout_file:
        raise ValueError("No stdout_file provided")

    singularity_run_cmd = f"{SINGULARITY_RUN_NWM_VERF_CMD} verification {verification_config}"

    return submit_job(verification_config, stdout_file, run_id, job_type, singularity_run_cmd)


_JOB_DISPATCHERS = {
    'calibration': submit_calibration_job,
    'validation': submit_validation_job,
    'forecast': submit_forecast_job,
    'hindcast': submit_hindcast_job,
    'cold-start': submit_cold_start_job,
    'verification-job': submit_verification_job,
}


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
       - Published from inside the SLURM job script via publish_job_event.py
       - Allows Django to mark the run as RUNNING and set run_start

    3. Terminal callback (exactly one of DONE / FAILED / CANCELED)
       - Published from inside the SLURM job script via publish_job_event.py
       - Triggers final status updates and post-processing in Django

    :param job_type: Normalized job type string
    :param run_id: Run identifier
    :param payload: Job-specific execution payload
    """
    submit_fn = _JOB_DISPATCHERS.get(job_type)
    if submit_fn is None:
        raise ValueError(f"Unsupported job_type: {job_type}")

    slurm_job_id = submit_fn(run_id, payload)
    logger.info(
        "Submitted job_type=%s run_id=%s slurm_job_id=%s",
        job_type,
        run_id,
        slurm_job_id,
    )

    publish_job_event(
        job_type,
        run_id,
        SlurmCallbackStatusEnum.SUBMITTED,
        slurm_job_id=slurm_job_id,
    )


def cancel_slurm_job(
        job_type: str,
        run_id: int,
        slurm_job_id: int,
) -> bool:
    """
    Cancel a job through the Parallel Works / Slurm execution path.

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
