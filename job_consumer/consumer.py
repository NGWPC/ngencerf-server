import logging

from kombu import Connection, Consumer, Queue
from kombu.exceptions import KombuError

from job_consumer.config import RABBITMQ_URL, RABBITMQ_JOBS_QUEUE
from job_consumer.handlers import dispatch_message

logger = logging.getLogger(__name__)


class JobConsumer:
    def __init__(self) -> None:
        self.jobs_queue = Queue(
            name=RABBITMQ_JOBS_QUEUE,
            durable=True,
        )

    def process_message(self, body, message) -> None:
        """
        Process one message from the queue.

        Acknowledge only after successful handling.
        Reject malformed or failed messages so they do not sit unacked forever.
        """
        delivery_tag = getattr(message, "delivery_tag", None)

        logger.info("Received message delivery_tag=%s body=%s", delivery_tag, body)

        try:
            if not isinstance(body, dict):
                raise ValueError("Expected message body to deserialize to a dict")

            dispatch_message(body)

            message.ack()
            logger.info("Acknowledged message delivery_tag=%s", delivery_tag)

        except ValueError as e:
            logger.error(
                "Rejecting invalid message delivery_tag=%s: %s",
                delivery_tag,
                e,
            )
            # TODO Need to put these in a dead-letter queue
            message.reject(requeue=False)

        except Exception as e:
            logger.exception(
                "Handler failed for delivery_tag=%s: %s",
                delivery_tag,
                e,
            )
            # For now, do not requeue automatically.
            # Otherwise a permanently bad message can spin forever.
            message.reject(requeue=False)

    def run(self) -> None:
        logger.info("Starting consumer for queue '%s'", RABBITMQ_JOBS_QUEUE)

        with Connection(RABBITMQ_URL) as conn:
            # Dev/local convenience only.
            # In production, the queue should already exist.
            bound_queue = self.jobs_queue(conn.default_channel)
            bound_queue.declare()
            logger.info("Declared queue '%s'", RABBITMQ_JOBS_QUEUE)

            with Consumer(
                    conn,
                    queues=[self.jobs_queue],
                    callbacks=[self.process_message],
                    accept=["json"],
                    prefetch_count=1,
            ):
                while True:
                    try:
                        conn.drain_events(timeout=5)
                    except TimeoutError:
                        continue
                    except KeyboardInterrupt:
                        logger.info("Received shutdown signal. Stopping consumer...")
                        break
                    except KombuError:
                        logger.exception("Kombu error while draining events")
                        raise
