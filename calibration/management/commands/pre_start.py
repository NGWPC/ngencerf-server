import logging

from django.core.management.base import BaseCommand
from django.db import transaction

from calibration.enums import StatusEnum
from calibration.models import CalibrationRun, ValidationRun
from django.conf import settings
from cerfServer.settings import NgenEnvironmentEnum

logger = logging.getLogger(__name__)


# This should be run prior to starting the server to clean up any orphans

class Command(BaseCommand):
    help = "Clean up running Calibration and Validation runs"

    def handle(self, *args, **options):
        if settings.NGEN_ENVIRONMENT == NgenEnvironmentEnum.LOCAL:
            with transaction.atomic():
                running_status = StatusEnum.from_enum(StatusEnum.RUNNING)
                error_status = StatusEnum.from_enum(StatusEnum.SERVER_ERROR)

                count = CalibrationRun.objects.filter(status=running_status).update(status=error_status)
                logger.info(f'Updated {count} calibration run records')

                count = ValidationRun.objects.filter(status=running_status).update(status=error_status)
                logger.info(f'Updated {count} validation run records')
