#!/usr/bin/env python3
"""
Publish a single job lifecycle event to RabbitMQ.

Called from inside SLURM job scripts to report STARTING / DONE / FAILED status
without requiring any HTTP server to be reachable from the compute node.

Usage:
    python3 publish_job_event.py \
        --job_type calibration \
        --run_id 42 \
        --job_status STARTING \
        --slurm_job_id 12345

Required environment variables:
    RABBITMQ_URL               RabbitMQ connection URL
    RABBITMQ_JOB_EVENTS_QUEUE  Queue name (default: job_events_queue)
"""
import argparse
import os

from kombu import Connection, Exchange, Producer, Queue


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--job_type', required=True)
    parser.add_argument('--run_id', type=int, required=True)
    parser.add_argument('--job_status', required=True)
    parser.add_argument('--slurm_job_id', type=int, required=True)
    args = parser.parse_args()

    url = os.environ['RABBITMQ_URL']
    queue_name = os.environ.get('RABBITMQ_JOB_EVENTS_QUEUE', 'job_events_queue')

    payload = {
        'job_type': args.job_type,
        'run_id': args.run_id,
        'job_status': args.job_status,
        'slurm_job_id': args.slurm_job_id,
    }

    queue = Queue(
        name=queue_name,
        exchange=Exchange('', type='direct'),
        routing_key=queue_name,
        durable=True,
    )

    with Connection(url) as conn:
        producer = Producer(conn.channel())
        producer.publish(
            payload,
            serializer='json',
            exchange='',
            routing_key=queue_name,
            declare=[queue],
            retry=True,
            retry_policy={'max_retries': 3, 'interval_start': 0, 'interval_step': 1, 'interval_max': 2},
            delivery_mode=2,
        )


if __name__ == '__main__':
    main()
