from django.db import transaction
from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import api_view

from .models import StatusEnum, Status, CalibrationRun


@api_view(['POST'])
# @login_required
@transaction.atomic
def create_calibration_run(request):
    print('user', request.user)

    run = CalibrationRun.objects.create(is_active=True, status=StatusEnum.SAVED.value)

    return JsonResponse({'message': f'Calibration Run {run.id} created', 'calibration_run_key': run.id}, status=status.HTTP_201_CREATED)

