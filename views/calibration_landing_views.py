import traceback

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import api_view

from calibration.enums import StatusEnum
from calibration.models import CalibrationRun
from calibration.models.status import Status


@api_view(['POST'])
# @login_required
def create_calibration_run(request):
    try:
        print('user', request.user)

        with transaction.atomic():
            # Need to add request.user to the Run object
            run = CalibrationRun.objects.create(is_active=True, status=Status.objects.get(name=StatusEnum.SAVED.value))

            return JsonResponse({'message': f'Calibration Run {run.id} created', 'calibration_run_id': run.id},
                                status=status.HTTP_201_CREATED)
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"exception": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# TODO Need to test this with start/end period
# noinspection PyUnusedLocal
@api_view(['POST', 'GET'])
# @login_required
def get_jobs(request):
    # Get all jobs for this user
    # TODO Need to filter jobs by user
    runs = list(CalibrationRun.objects.only('formulation_name', 'gage', 'run_date', 'calibration_start_period', 'calibration_end_period', 'status').values(
        'formulation_name', 'gage__gage_id', 'run_date', 'calibration_start_period', 'calibration_end_period', 'status__name'))
    print('run', runs)
    for r in runs:
        r['gage_id'] = r.pop('gage__gage_id')
        r['status'] = r.pop('status__name')
    return JsonResponse(runs, safe=False)


# noinspection PyUnusedLocal
@api_view(['POST', 'GET'])
# @login_required
def get_footer(request):
    try:
        return JsonResponse({"version": settings.VERSION, "contact_email": settings.CONTACT_EMAIL})
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"exception": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
