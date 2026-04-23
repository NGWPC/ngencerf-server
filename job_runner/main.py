import logging

from job_runner.config import (
    JOB_EXECUTION_MODE,
    RABBITMQ_URL,
    RABBITMQ_JOBS_QUEUE,
)
from job_runner.job_listener import JobListener
from job_runner.logging_config import configure_logging

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging()

    logger.info("Starting job consumer with configuration:")
    logger.info("  JOB_EXECUTION_MODE = %s", JOB_EXECUTION_MODE.name)
    logger.info("  RABBITMQ_QUEUE     = %s", RABBITMQ_JOBS_QUEUE)

    # Avoid dumping credentials from the URL
    if RABBITMQ_URL:
        logger.info("  RABBITMQ_URL       = %s", _sanitize_rabbitmq_url(RABBITMQ_URL))
    else:
        logger.warning("  RABBITMQ_URL is not set")

    consumer = JobListener()
    consumer.run()


def _sanitize_rabbitmq_url(url: str) -> str:
    """
    Remove credentials from the RabbitMQ URL for safe logging.
    """
    try:
        # amqp://user:pass@host:port// → amqp://***:***@host:port//
        prefix, rest = url.split("://", 1)
        if "@" in rest:
            creds, host = rest.split("@", 1)
            return f"{prefix}://***:***@{host}"
        return url
    except Exception:
        return "<invalid RABBITMQ_URL>"


if __name__ == "__main__":
    main()
