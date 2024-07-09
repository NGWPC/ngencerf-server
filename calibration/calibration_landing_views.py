import traceback

from django.db import transaction
from django.db.backends.signals import connection_created
from django.dispatch import receiver
from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import api_view

from .models import StatusEnum, Status, CalibrationRun


# Use this function to do any database clean, such
# as identifying any CalibrationRun or ValidationRuns in Running status
@receiver(connection_created)
def start_up(connection, **kwargs):
    with connection.cursor() as cursor:
        # do something with database
        print('hello world')

    # Disconnect so we don't run again
    connection_created.disconnect(start_up)


@api_view(['POST'])
# @login_required
def create_calibration_run(request):
    try:
        print('user', request.user)

        with transaction.atomic():
            # Need to add request.user to the Run object
            run = CalibrationRun.objects.create(is_active=True, status=Status.objects.get(name=StatusEnum.SAVED.value))

            return JsonResponse({'message': f'Calibration Run {run.id} created', 'calibration_run_key': run.id},
                                status=status.HTTP_201_CREATED)
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"exception": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
