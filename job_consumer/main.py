from job_consumer.consumer import JobConsumer
from job_consumer.logging_config import configure_logging


def main() -> None:
    configure_logging()
    consumer = JobConsumer()
    consumer.run()


if __name__ == "__main__":
    main()
