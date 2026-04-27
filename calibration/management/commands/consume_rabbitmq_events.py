import logging
from datetime import datetime, timezone

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from kombu import Connection, Consumer, Queue
from kombu.exceptions import KombuError

from calibration.enums import SlurmCallbackStatusEnum, StatusEnum, JobType
from calibration.enums_vanilla import JobExecutionMode
from calibration.models import CalibrationRun, Iteration
from calibration.run_util.job_lifecycle import run_job_callback_pw
from calibration.util.calibration_validators import JobEventSerializer, ReportIterationSerializer
from calibration.views.calibration_run_views import acknowledge_slurm_submission
from calibration.views.common import (
    get_calibration_run,
    get_validation_run,
    get_forecast_run,
    get_cold_start_run,
    get_verification_run,
    get_hindcast_run,
)
from calibration.views.common import validate_request, get_job_description

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Consume RabbitMQ job lifecycle and iteration event messages."

    def __init__(self) -> None:
        super().__init__()

        self.rabbitmq_url = settings.RABBITMQ_URL

        # TODO The job-end event for a Calibration job can take a few minutes
        # Might want to consider having a separate queue for that
        self.job_events_queue = Queue(
            name=settings.RABBITMQ_JOB_EVENTS_QUEUE,
            durable=True,
        )

        self.iteration_events_queue = Queue(
            name=settings.RABBITMQ_ITERATION_EVENTS_QUEUE,
            durable=True,
        )

        self.should_stop = False

    def handle(self, *args, **options) -> None:
        logger.info(
            "Starting RabbitMQ event consumer for queues '%s' and '%s'",
            self.job_events_queue.name,
            self.iteration_events_queue.name,
        )

        with Connection(self.rabbitmq_url) as conn:
            for queue in [self.job_events_queue, self.iteration_events_queue]:
                bound_queue = queue(conn.default_channel)
                bound_queue.declare()
                logger.info("Declared queue '%s'", queue.name)

            with Consumer(
                    conn,
                    queues=[self.job_events_queue, self.iteration_events_queue],
                    callbacks=[self.process_message],
                    accept=["json"],
                    prefetch_count=1,
            ):
                while not self.should_stop:
                    try:
                        conn.drain_events(timeout=5)
                    except TimeoutError:
                        continue
                    except KombuError:
                        logger.exception("Kombu error while draining RabbitMQ event messages")
                        raise

    def process_message(self, body, message) -> None:
        """
        Process one RabbitMQ event message.

        Acknowledge only after successful handling.
        Reject malformed or failed messages so they do not sit unacked forever.
        """
        delivery_tag = getattr(message, "delivery_tag", None)
        routing_key = message.delivery_info.get("routing_key")

        logger.info(
            "Received RabbitMQ event delivery_tag=%s routing_key=%s body=%s",
            delivery_tag,
            routing_key,
            body,
        )

        try:
            if not isinstance(body, dict):
                raise ValueError("Expected message body to deserialize to a dict")

            if routing_key == settings.RABBITMQ_JOB_EVENTS_QUEUE:
                self.dispatch_job_event(body)
            elif routing_key == settings.RABBITMQ_ITERATION_EVENTS_QUEUE:
                self.dispatch_iteration_event(body)
            else:
                raise ValueError(f"Unsupported RabbitMQ routing_key: {routing_key}")

            message.ack()
            logger.info(
                "Acknowledged RabbitMQ event delivery_tag=%s routing_key=%s",
                delivery_tag,
                routing_key,
            )

        except ValueError as e:
            logger.error(
                "Rejecting invalid RabbitMQ event delivery_tag=%s routing_key=%s: %s",
                delivery_tag,
                routing_key,
                e,
            )
            # TODO Put these in a dead-letter queue
            message.reject(requeue=False)

        except Exception as e:
            logger.exception(
                "RabbitMQ event handler failed for delivery_tag=%s routing_key=%s: %s",
                delivery_tag,
                routing_key,
                e,
            )
            # For now, do not requeue automatically.
            # Otherwise a permanently bad message can spin forever.
            message.reject(requeue=False)

    @staticmethod
    def dispatch_job_event(body: dict) -> None:
        """
        Process a job lifecycle event from the job events queue.

        Expected payload:
        {
            "job_type": "calibration" | "validation" | "cold_start" | "forecast" | "hindcast" | "verification",
            "run_id": 123,
            "job_status": "SUBMITTED" | "STARTING" | "DONE" | "FAILED" | "CANCELED",
            "slurm_job_id": 456789 | null
        }
        """

        # ------------------------------------------------------------
        # Validate incoming message
        # ------------------------------------------------------------
        validator, error_return = validate_request(JobEventSerializer, body)
        if error_return:
            raise ValueError(str(error_return.data if hasattr(error_return, "data") else error_return))

        job_type = validator.get("job_type")
        run_id = validator.get("run_id")
        job_status = validator.get("job_status")
        slurm_job_id = validator.get("slurm_job_id")

        assert isinstance(job_type, str)
        assert isinstance(run_id, int)
        assert isinstance(job_status, str)

        slurm_status = SlurmCallbackStatusEnum(job_status)

        # ------------------------------------------------------------
        # Map job_type → get_run function
        # ------------------------------------------------------------
        get_run_map = {
            JobType.CALIBRATION.value: get_calibration_run,
            JobType.VALIDATION.value: get_validation_run,
            JobType.COLD_START.value: get_cold_start_run,
            JobType.FORECAST.value: get_forecast_run,
            JobType.HINDCAST.value: get_hindcast_run,
            JobType.VERIFICATION.value: get_verification_run,
        }

        if job_type not in get_run_map:
            raise ValueError(f"Unsupported job_type: {job_type}")

        get_run_fn = get_run_map[job_type]

        # ------------------------------------------------------------
        # Validate slurm_job_id requirement for PW
        # ------------------------------------------------------------
        if settings.JOB_EXECUTION_MODE == JobExecutionMode.PARALLEL_WORKS and slurm_job_id is None:
            raise ValueError(
                "slurm_job_id is required for callbacks when JOB_EXECUTION_MODE is PARALLEL_WORKS"
            )

        # ------------------------------------------------------------
        # Determine allowed DB states (same as handle_slurm_callback)
        # ------------------------------------------------------------
        if slurm_status in [SlurmCallbackStatusEnum.SUBMITTED, SlurmCallbackStatusEnum.STARTING]:
            expected_status = [StatusEnum.SUBMITTED]
        else:
            # End callbacks are allowed from RUNNING or SUBMITTED to tolerate races
            expected_status = [StatusEnum.RUNNING, StatusEnum.SUBMITTED]

        run, error_return = get_run_fn(run_id, None, run_status=expected_status)
        if error_return:
            raise ValueError(str(error_return.data if hasattr(error_return, "data") else error_return))
        assert run is not None

        logger.info(
            "Processing job event job_type=%s run_id=%s status=%s slurm_job_id=%s",
            job_type,
            run_id,
            slurm_status.value,
            slurm_job_id,
        )

        job_description = f"{get_job_description(run)} (slurm_job_id: {run.slurm_job_id})"

        # ------------------------------------------------------------
        # SUBMITTED
        # ------------------------------------------------------------
        if slurm_status == SlurmCallbackStatusEnum.SUBMITTED:
            logger.info(
                f"{job_description} received submission acknowledgement "
                f"with callback slurm_job_id={slurm_job_id}"
            )
            if slurm_job_id is not None:
                assert isinstance(slurm_job_id, int)
                acknowledge_slurm_submission(run, slurm_job_id)
            return

        # ------------------------------------------------------------
        # STARTING
        # ------------------------------------------------------------
        if slurm_status == SlurmCallbackStatusEnum.STARTING:
            if slurm_job_id is not None:
                assert isinstance(slurm_job_id, int)
                acknowledge_slurm_submission(run, slurm_job_id)

            logger.info(f"{job_description} is starting")
            run.status = StatusEnum.RUNNING.db_instance
            run.run_start = datetime.now(timezone.utc)
            run.save(update_fields=["status", "run_start"])
            return

        # ------------------------------------------------------------
        # END OF JOB
        # ------------------------------------------------------------
        if slurm_job_id is not None:
            assert isinstance(slurm_job_id, int)
            acknowledge_slurm_submission(run, slurm_job_id)

        logger.info(f"{job_description} is ending")
        run_job_callback_pw(run, slurm_status)

    @staticmethod
    def dispatch_iteration_event(body: dict) -> None:
        """
        Process a calibration iteration event received from RabbitMQ.

        Expected payload:
        {
            "message_type": "report_iteration",
            "version": 1,
            "calibration_run_id": 123,
            "iteration": 7,
            "worker_name": "worker_2",
            "first_iteration_for_worker": true
        }

        Concurrency considerations:
        - Each CalibrationRun has a next_worker_number counter that is incremented
          atomically under select_for_update().
        - This guarantees that two new workers starting at the same time are
          serialized and each receives a unique worker number.
        - Once assigned, a worker number is reused for all iterations reported by
          that worker for the run.
        - The (iteration_num, worker_name, calibration_run) uniqueness constraint
          ensures that a worker cannot report the same iteration twice.

        Transaction strategy:
        - For new workers, the row lock on CalibrationRun ensures safe allocation
          of a worker number.
        - For existing workers, the latest prior iteration is queried so the same
          worker number can be reused.
        - The insert via get_or_create() occurs inside the same atomic block to
          prevent duplicates.

        :param body: Incoming RabbitMQ message body
        :raises ValueError: If validation fails or the run cannot be updated
        """
        # ------------------------------------------------------------
        # Validate incoming message
        # ------------------------------------------------------------
        validator, error_return = validate_request(ReportIterationSerializer, body)
        if error_return:
            raise ValueError(str(error_return.data if hasattr(error_return, "data") else error_return))

        calibration_run_id = validator.get("calibration_run_id")
        iteration_number = validator.get("iteration")
        worker_name = validator.get("worker_name")
        first_iteration_for_worker = validator.get("first_iteration_for_worker")

        assert isinstance(calibration_run_id, int)
        assert isinstance(iteration_number, int)
        assert isinstance(worker_name, str)
        assert isinstance(first_iteration_for_worker, bool)

        logger.debug(
            "Report Iteration for calibration_run_id %s, iteration number: %s, "
            "worker: %s, first_iteration: %s",
            calibration_run_id,
            iteration_number,
            worker_name,
            first_iteration_for_worker,
        )

        run, error_return = get_calibration_run(
            calibration_run_id,
            None,
            run_status=[StatusEnum.RUNNING],
        )
        if error_return:
            raise ValueError(str(error_return.data if hasattr(error_return, "data") else error_return))
        assert run is not None

        with transaction.atomic():
            if first_iteration_for_worker:
                run = CalibrationRun.objects.select_for_update().get(id=run.id)
                worker_number = run.next_worker_number
                run.next_worker_number += 1
                run.save(update_fields=["next_worker_number"])
                logger.debug("Assigned new worker: '%s' #%s", worker_name, worker_number)
            else:
                existing_iteration = (
                    Iteration.objects
                    .filter(calibration_run=run, worker_name=worker_name)
                    .only("worker_number")
                    .order_by("-iteration_num")
                    .first()
                )
                if existing_iteration:
                    worker_number = existing_iteration.worker_number
                else:
                    raise ValueError(
                        f"Worker '{worker_name}' not found for calibration run {run.id}."
                    )

            _, created = Iteration.objects.get_or_create(
                calibration_run=run,
                iteration_num=iteration_number,
                worker_name=worker_name,
                defaults={"worker_number": worker_number},
            )
            if not created:
                raise ValueError(
                    f"Iteration object already exists for calibration run {run.id}, "
                    f"worker {worker_name}, iteration {iteration_number}"
                )

        logger.info(
            "Iteration %s for worker_name '%s' set for Calibration Job %s",
            iteration_number,
            worker_name,
            run.id,
        )
