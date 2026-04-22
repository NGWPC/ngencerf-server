import os
from pathlib import Path

from job_consumer.job_consumer_enums import JobExecutionMode

BASE_DIR = Path(__file__).resolve().parent.parent

RABBITMQ_URL = os.getenv("RABBITMQ_URL")
RABBITMQ_JOBS_QUEUE = os.getenv("RABBITMQ_JOBS_QUEUE", "jobs_queue")
RABBITMQ_JOB_EVENTS_QUEUE = os.getenv("RABBITMQ_JOB_EVENTS_QUEUE", "job_events_queue")

# ------------------------------------------------------------
# Job execution environment
# ------------------------------------------------------------
JOB_EXECUTION_MODE_STR = os.getenv(
    "JOB_EXECUTION_MODE",
    JobExecutionMode.DOCKER.name,
)

try:
    JOB_EXECUTION_MODE = JobExecutionMode(JOB_EXECUTION_MODE_STR)
except ValueError:
    raise SystemExit(
        "Invalid environment value for JOB_EXECUTION_MODE: "
        f"{JOB_EXECUTION_MODE_STR}. Must be one of "
        f"{JobExecutionMode.DOCKER.name}, {JobExecutionMode.PARALLEL_WORKS.name}"
    )

if JOB_EXECUTION_MODE not in [
    JobExecutionMode.DOCKER,
    JobExecutionMode.PARALLEL_WORKS,
]:
    raise SystemExit(
        "JOB_EXECUTION_MODE must be either "
        f"{JobExecutionMode.DOCKER.name} or {JobExecutionMode.PARALLEL_WORKS.name}"
    )

# ------------------------------------------------------------
# ngen / run locations
# ------------------------------------------------------------


# This must match the data location in the ngen/nwm-cal-mgr docker
# Do not change this location.  You can put your data wherever you want, but you should then create a symbolic link to /ngencerf/data
# sudo mkdir /ngencerf
# sudo ln -s ~/your/data/dir /ngencerf/data
NGEN_CAL_MOUNT_POINT = "/ngencerf/data"
# NGEN_CAL_DATA_PATH = os.getenv("NGEN_CAL_DATA_PATH", NGEN_CAL_MOUNT_POINT)
#
# NGEN_STATIC_DIR = os.path.join(NGEN_CAL_MOUNT_POINT, "ngen-static-files")
# NGEN_CAL_WORK_DIR = os.path.join(NGEN_CAL_MOUNT_POINT, "ngen-cal-work")
# NGEN_VERIFICATION_WORK_DIR = os.path.join(NGEN_CAL_MOUNT_POINT, "verification_work")
# NGEN_BMI_FORCING_WORK_DIR = os.path.join(NGEN_CAL_MOUNT_POINT, "bmi_forcing_work")

# NGEN_CAL_RUN_DIR = os.path.join(NGEN_CAL_WORK_DIR, "run_calib")

# ------------------------------------------------------------
# Docker runtime commands
# ------------------------------------------------------------
# Used when running in JOB_EXECUTION_MODE=DOCKER
# --rm ensures containers are auto-removed after exit
# Use {name} placeholder for the container name, which will be substituted at runtime
CAL_MGR_DOCKER_CMD = (
    f"docker run --rm --network host --name {{name}} "
    f"-v {NGEN_CAL_MOUNT_POINT}:{NGEN_CAL_MOUNT_POINT} nwm-cal-mgr"
)
NGEN_FORECAST_DOCKER_CMD = (
    f"docker run --rm --name {{name}} "
    f"-v {NGEN_CAL_MOUNT_POINT}:{NGEN_CAL_MOUNT_POINT} nwm-fcst-mgr"
)
NWM_VERF_DOCKER_CMD = (
    f"docker run --rm --name {{name}} "
    f"-v {NGEN_CAL_MOUNT_POINT}:{NGEN_CAL_MOUNT_POINT} nwm-verf"
)

RUNTIME_INFO = {
    "calibration": CAL_MGR_DOCKER_CMD,
    "validation": CAL_MGR_DOCKER_CMD,
    "validation_iteration": CAL_MGR_DOCKER_CMD,
    "cold_start": NGEN_FORECAST_DOCKER_CMD,
    "forecast": NGEN_FORECAST_DOCKER_CMD,
    "hindcast": NGEN_FORECAST_DOCKER_CMD,
    "verification": NWM_VERF_DOCKER_CMD,
}

# ------------------------------------------------------------
# Logging
# ------------------------------------------------------------
NGEN_LOGGING_DIR = BASE_DIR / "logs"
os.makedirs(NGEN_LOGGING_DIR, exist_ok=True)

JOB_CONSUMER_LOG_FILE = NGEN_LOGGING_DIR / "job_consumer.log"
JOB_CONSUMER_LOG_LEVEL = os.getenv("JOB_CONSUMER_LOG_LEVEL", "INFO")
