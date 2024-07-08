import json

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from rest_framework import status
from rest_framework.decorators import api_view

from .calibration_validators import SaveGageValidator, GageIdValidator
from .models import Gage, CalibrationRun


@api_view(['GET'])
def csrf(request):
    return JsonResponse({'csrf': get_token(request)})


@api_view(['GET', 'POST'])
# @login_required()
def get_gage(request, gage_id=None):
    if request.method == 'POST':
        body = json.loads(request.body)
        validate = GageIdValidator(data=body or {})
        if not validate.is_valid():
            print('Validation errors', validate.errors)
            return JsonResponse({"errors": validate.errors})
        else:
            gage_id = body.get('gage_id')

    print('gage_id', gage_id)

    gage = Gage.objects.filter(gage_id=gage_id).only('gage_id', 'agency', 'station_name').values(
        'gage_id', 'agency', 'station_name', 'latitude', 'longitude', 'altitude').first()
    if not gage:
        return JsonResponse({"error": f"Gage '{gage_id}' does not exist"}, status=status.HTTP_404_NOT_FOUND)

    return JsonResponse(gage, safe=False)


@api_view(['GET', 'POST'])
# @login_required()
def get_gages(request):
    gages = Gage.objects.filter(is_active=True)
    return JsonResponse(list(gages.values_list('gage_id', flat=True)), safe=False)


@api_view(['POST'])
# @login_required
@transaction.atomic
def save_gage_tab(request):
    print('user', request.user)
    body = json.loads(request.body)
    validate = SaveGageValidator(data=body or {})
    if not validate.is_valid():
        print('Validation errors', validate.errors)
        return JsonResponse({"errors": validate.errors})
    calibration_run_id = validate.data.calibration_run_id
    gage_id = body.get('gage_id')
    forcing_source = body.get('forcing_source')
    forcing_path = body.get('forcing_path')

    gage = Gage.objects.filter(gage_id=gage_id).first()
    if not gage:
        return JsonResponse({"error": f"Gage '{gage_id}' does not exist"}, status=status.HTTP_404_NOT_FOUND)

    run = CalibrationRun.objects.filter(id=calibration_run_id).first()
    if not run:
        return JsonResponse({'message': f'Calibration Run {calibration_run_id} does not exist'})

    run.gage = gage
    run.forcing_source = forcing_source
    run.forcing_path = forcing_path
    run.save()
    return JsonResponse({'message': f'Calibration Run {run.id} updated', 'calibration_run_key': run.id})


@api_view(['GET'])
def test(request):
    return HttpResponse('hello')
