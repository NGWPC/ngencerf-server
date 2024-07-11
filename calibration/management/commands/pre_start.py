from django.core.management.base import BaseCommand
from django.db import transaction

from calibration.enums import StatusEnum
from calibration.models import CalibrationRun, Status, ValidationRun


# This should be run prior to starting the server to clean up any orphans


class Command(BaseCommand):
    help = "Clean up running Calibration and Validation runs"

    def handle(self, *args, **options):
        with transaction.atomic():
            server_error = Status.objects.get(name=StatusEnum.SERVER_ERROR.value)
            count = CalibrationRun.objects.filter(status__name=StatusEnum.RUNNING).update(status=server_error)
            print(f'Updated {count} calibration run records')

            count = ValidationRun.objects.filter(status__name=StatusEnum.RUNNING).update(status=server_error)
            print(f'Updated {count} validation run records')
