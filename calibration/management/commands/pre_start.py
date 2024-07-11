from django.core.management.base import BaseCommand
from django.db import transaction

from calibration.enums import StatusEnum
from calibration.models import CalibrationRun, Status


# This should be run prior to starting the server to clean up any orphans


class Command(BaseCommand):
    help = "Clean up running Calibration and Validation runs"

    def handle(self, *args, **options):
        with transaction.atomic():
            CalibrationRun.objects.filter(statuse=StatusEnum.RUNNING.value).update(status=StatusEnum.SERVER_ERROR.value)


