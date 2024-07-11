import json
import traceback

from django.db import transaction
from django.http import JsonResponse
from django.middleware.csrf import get_token
from rest_framework import status
from rest_framework.decorators import api_view

from calibration.calibration_validators import SaveGageValidator, GageIdValidator
from calibration.enums import StatusEnum
from calibration.models import Gage, CalibrationRun


# Probably don't need this
@api_view(['GET'])
def csrf(request):
    return JsonResponse({'csrf': get_token(request)})


@api_view(['GET', 'POST'])
# @login_required()
def get_gage(request):
    try:
        if request.method == 'POST':
            data = json.loads(request.body)
        else:
            data = request.GET

        validate = GageIdValidator(data=data or {})
        validate.is_valid(raise_exception=True)

        gage_id = validate.data.get('gage_id')

        print('gage_id', gage_id)

        gage = Gage.objects.filter(gage_id=gage_id).only('gage_id', 'agency', 'station_name').values(
            'gage_id', 'agency', 'station_name', 'latitude', 'longitude', 'altitude').first()
        if not gage:
            return JsonResponse({"error": f"Gage '{gage_id}' does not exist"}, status=status.HTTP_404_NOT_FOUND)

        return JsonResponse(gage, safe=False)
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"exception": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET', 'POST'])
# @login_required()
def get_gages(request):
    try:
        gages = Gage.objects.filter(is_active=True)
        return JsonResponse(list(gages.values_list('gage_id', flat=True)), safe=False)
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"exception": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
# @login_required
def save_gage_tab(request):
    try:
        print('user', request.user)

        body = json.loads(request.body)
        validate = SaveGageValidator(data=body or {})
        validate.is_valid(raise_exception=True)

        calibration_run_id = validate.data.get('calibration_run_id')
        gage_id = body.get('gage_id')
        forcing_source = body.get('forcing_source')
        forcing_path = body.get('forcing_path')

        with transaction.atomic():
            gage = Gage.objects.filter(gage_id=gage_id).first()
            if not gage:
                return JsonResponse({"error": f"Gage '{gage_id}' does not exist"}, status=status.HTTP_404_NOT_FOUND)

            # Do we want only SAVED?  Want to make sure it hasn't been run yet
            # Or do we want anything that's not RUNNING?
            run = CalibrationRun.objects.filter(id=calibration_run_id, status__name=StatusEnum.SAVED).first()
            if not run:
                return JsonResponse({'message': f'Calibration Run {calibration_run_id} does not exist'})

            run.gage = gage
            run.forcing_source = forcing_source
            run.forcing_path = forcing_path
            run.save()
            return JsonResponse({'message': f'Calibration Run {run.id} updated', 'calibration_run_key': run.id})
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"exception": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
