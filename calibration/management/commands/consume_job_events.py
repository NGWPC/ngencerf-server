import logging
from datetime import datetime, timezone

from django.conf import settings
from django.core.management.base import BaseCommand
from kombu import Connection, Consumer, Queue
from kombu.exceptions import KombuError

from calibration.enums import SlurmCallbackStatusEnum, StatusEnum
from calibration.enums_vanilla import JobExecutionMode
from calibration.enums_vanilla import JobType
from calibration.run_util.run_common import run_job_callback_pw
from calibration.util.calibration_validators import JobEventSerializer
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
    help = "Consume RabbitMQ job event messages and apply them to ngenCERF runs."

    def __init__(self) -> None:
        super().__init__()

        self.rabbitmq_url = settings.RABBITMQ_URL
        self.job_events_queue = Queue(
            name=settings.RABBITMQ_JOB_EVENTS_QUEUE,
            durable=True,
        )
        self.should_stop = False

    def handle(self, *args, **options) -> None:
        logger.info("Starting job event consumer for queue '%s'", self.job_events_queue.name)

        with Connection(self.rabbitmq_url) as conn:
            bound_queue = self.job_events_queue(conn.default_channel)
            bound_queue.declare()
            logger.info("Declared queue '%s'", self.job_events_queue.name)

            with Consumer(
                    conn,
                    queues=[self.job_events_queue],
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
                        logger.exception("Kombu error while draining job event messages")
                        raise

    def process_message(self, body, message) -> None:
        """
        Process one job event message.

        Acknowledge only after successful handling.
        Reject malformed or failed messages so they do not sit unacked forever.
        """
        delivery_tag = getattr(message, "delivery_tag", None)

        logger.info("Received job event delivery_tag=%s body=%s", delivery_tag, body)

        try:
            if not isinstance(body, dict):
                raise ValueError("Expected message body to deserialize to a dict")

            self.dispatch_message(body)

            message.ack()
            logger.info("Acknowledged job event delivery_tag=%s", delivery_tag)

        except ValueError as e:
            logger.error(
                "Rejecting invalid job event delivery_tag=%s: %s",
                delivery_tag,
                e,
            )
            # TODO Put these in a dead-letter queue
            message.reject(requeue=False)

        except Exception as e:
            logger.exception(
                "Job event handler failed for delivery_tag=%s: %s",
                delivery_tag,
                e,
            )
            # For now, do not requeue automatically.
            # Otherwise a permanently bad message can spin forever.
            message.reject(requeue=False)

    @staticmethod
    def dispatch_message(body: dict) -> None:
        """
        Process a Slurm job event from the queue using a generic payload.

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
        if settings.NGEN_ENVIRONMENT == JobExecutionMode.PARALLEL_WORKS and slurm_job_id is None:
            raise ValueError(
                "slurm_job_id is required for callbacks when NGEN_ENVIRONMENT is PARALLEL_WORKS"
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
