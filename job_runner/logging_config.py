import logging
import os

from job_runner.config import JOB_RUNNER_LOG_FILE, JOB_RUNNER_LOG_LEVEL


def configure_logging() -> None:
    os.makedirs(os.path.dirname(JOB_RUNNER_LOG_FILE), exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s"
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(JOB_RUNNER_LOG_FILE)
    file_handler.setFormatter(formatter)

    logging.basicConfig(
        level=getattr(logging, JOB_RUNNER_LOG_LEVEL.upper(), logging.INFO),
        handlers=[console_handler, file_handler],
    )