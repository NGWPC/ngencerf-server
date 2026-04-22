# messaging.py
from __future__ import annotations

from typing import Any

from django.conf import settings
from kombu import Connection, Producer, Queue

# ------------------------------------------------------------------
# Queue definition
# ------------------------------------------------------------------
SLURM_SUBMIT_QUEUE = Queue(
    name=settings.RABBITMQ_JOBS_QUEUE,
    durable=True,
)

# ------------------------------------------------------------------
# Shared connection (reused across publishes)
# ------------------------------------------------------------------
_connection = Connection(settings.RABBITMQ_URL)


def publish_job_message(payload: dict[str, Any]) -> None:
    """
    Publish a Slurm submission message to the RabbitMQ default exchange.

    Messages are routed directly to 'jobs_queue' by using the queue name
    as the routing key.

    Uses a shared connection with per-call channels (thread-safe pattern).
    """

    # Ensure connection is alive (handles reconnects)
    _connection.ensure_connection(max_retries=3)

    with _connection.channel() as channel:
        producer = Producer(channel)

        # ------------------------------------------------------------------
        # Optional: ensure queue exists
        # ------------------------------------------------------------------
        # This will create the queue if it does not exist.
        # In production, queues should typically be pre-defined via
        # infrastructure (Terraform, Helm, UI, etc.), so this should not
        # be relied on long-term.
        bound_queue = SLURM_SUBMIT_QUEUE(channel)
        bound_queue.declare()

        producer.publish(
            payload,
            exchange="",  # default exchange
            routing_key=settings.RABBITMQ_JOBS_QUEUE,
            serializer="json",
            delivery_mode=2,
            retry=True,
            retry_policy={
                "max_retries": 3,
                "interval_start": 0,
                "interval_step": 1,
                "interval_max": 2,
            },
        )
