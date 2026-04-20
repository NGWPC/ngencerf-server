import os
from pathlib import Path

from job_consumer.job_consumer_enums import ConsumerEnvironmentEnum

BASE_DIR = Path(__file__).resolve().parent.parent

RABBITMQ_URL = os.getenv("RABBITMQ_URL")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "jobs_queue")

# ------------------------------------------------------------
# Job execution environment
# ------------------------------------------------------------
JOB_CONSUMER_ENVIRONMENT_STR = os.getenv(
    "JOB_CONSUMER_ENVIRONMENT",
    ConsumerEnvironmentEnum.DOCKER.name,
)

try:
    JOB_CONSUMER_ENVIRONMENT = ConsumerEnvironmentEnum(JOB_CONSUMER_ENVIRONMENT_STR)
except ValueError:
    raise SystemExit(
        "Invalid environment value for JOB_CONSUMER_ENVIRONMENT: "
        f"{JOB_CONSUMER_ENVIRONMENT_STR}. Must be one of "
        f"{ConsumerEnvironmentEnum.DOCKER.name}, {ConsumerEnvironmentEnum.PARALLEL_WORKS.name}"
    )

if JOB_CONSUMER_ENVIRONMENT not in [
    ConsumerEnvironmentEnum.DOCKER,
    ConsumerEnvironmentEnum.PARALLEL_WORKS,
]:
    raise SystemExit(
        "JOB_CONSUMER_ENVIRONMENT must be either "
        f"{ConsumerEnvironmentEnum.DOCKER.name} or {ConsumerEnvironmentEnum.PARALLEL_WORKS.name}"
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
# Used when running in JOB_CONSUMER_ENVIRONMENT=DOCKER
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

# ------------------------------------------------------------
# Callback target
# ------------------------------------------------------------
# Used by the consumer to notify Django when jobs are submitted/starting/finished.
CERF_SERVER_URL = os.getenv("CERF_SERVER_URL", 'http://localhost:8000')
