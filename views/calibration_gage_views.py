import json
import traceback

from django.db import transaction
from django.http import JsonResponse
from django.middleware.csrf import get_token
from rest_framework import status
from rest_framework.decorators import api_view

from calibration.calibration_validators import SaveGageValidator, GageIdValidator, CalibrationRunValidator
from calibration.enums import StatusEnum
from calibration.management.commands import ngen_cal_input
from calibration.models import Gage, CalibrationRun


# Probably don't need this
@api_view(['GET'])
def csrf(request):
    return JsonResponse({'csrf': get_token(request)})


@api_view(['GET', 'POST'])
# @login_required
def load_gage_tab(request):
    try:
        print('user', request.user)
        if request.method == 'POST':
            data = json.loads(request.body or '{}')
        else:
            data = request.GET

        validate = CalibrationRunValidator(data=data)
        validate.is_valid(raise_exception=True)

        calibration_run_id = validate.data.get('calibration_run_id')

        # TODO Need to filter jobs by user
        run = CalibrationRun.objects.filter(id=calibration_run_id).select_related('status', 'gage').first()
        if not run:
            return JsonResponse({'error': f'Calibration Run {calibration_run_id} does not exist or is not owned by {request.user}'},
                                status=status.HTTP_400_BAD_REQUEST)
        if run.status.name != StatusEnum.READY and run.status.name != StatusEnum.SAVED:
            return JsonResponse({'error': f'Calibration Run {calibration_run_id} is not saved or ready.  Status: {run.status.name}'},
                                status=status.HTTP_400_BAD_REQUEST)

        gage = {'gage_id': run.gage.id, 'agency': run.gage.agency, 'station_name': run.gage.station_name, 'latitude': run.gage.latitude,
                'longitude': run.gage.longitude, 'altitude': run.gage.altitude} if run.gage else {}
        forcing_source = run.forcing_source
        forcing_user_filename = run.forcing_user_filename

        # Get all the gages so the user can select another
        gages = Gage.objects.filter(is_active=True).values_list('gage_id', flat=True)

        ngen_cal_input.ready_to_run(run=run)

        return JsonResponse({'calibration_run_id': run.id, 'status': run.status.name, 'gage': gage, 'forcing_source': forcing_source,
                             'forcing_user_filename': forcing_user_filename, 'gages': list(gages)}, safe=False)
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"exception": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET', 'POST'])
# @login_required()
def get_gage(request):
    try:
        if request.method == 'POST':
            data = json.loads(request.body or '{}')
        else:
            data = request.GET

        validate = GageIdValidator(data=data)
        validate.is_valid(raise_exception=True)

        gage_id = validate.data.get('gage_id')

        gage = Gage.objects.filter(gage_id=gage_id).only('gage_id', 'agency', 'station_name').values(
            'gage_id', 'agency', 'station_name', 'latitude', 'longitude', 'altitude').first()
        if not gage:
            return JsonResponse({"error": f"Gage '{gage_id}' does not exist"}, status=status.HTTP_404_NOT_FOUND)

        return JsonResponse(gage, safe=False)
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"exception": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
# @login_required
def save_gage_tab(request):
    try:
        print('user', request.user)

        body = json.loads(request.body or '{}')
        validate = SaveGageValidator(data=body)
        validate.is_valid(raise_exception=True)

        calibration_run_id = validate.data.get('calibration_run_id')
        gage_id = validate.data.get('gage_id')
        forcing_source = validate.data.get('forcing_source')
        forcing_user_filename = validate.data.get('forcing_user_filename')

        # TODO Need to filter jobs by user
        run = CalibrationRun.objects.filter(id=calibration_run_id).select_related('status').first()
        if not run:
            return JsonResponse({'error': f'Calibration Run {calibration_run_id} does not exist or is not owned by {request.user}'},
                                status=status.HTTP_400_BAD_REQUEST)
        if run.status.name != StatusEnum.READY and run.status.name != StatusEnum.SAVED:
            return JsonResponse({'error': f'Calibration Run {calibration_run_id} is not saved or ready.  Status: {run.status.name}'},
                                status=status.HTTP_400_BAD_REQUEST)

        if gage_id:
            gage = Gage.objects.filter(gage_id=gage_id).first()
            if not gage:
                return JsonResponse({"error": f"Gage '{gage_id}' does not exist"}, status=status.HTTP_404_NOT_FOUND)
            else:
                run.gage = gage

        run.forcing_source = forcing_source
        run.forcing_user_filename = forcing_user_filename
        # TODO Need to fill in forcing_path with our location

        with transaction.atomic():
            run.save()

        ngen_cal_input.ready_to_run(run=run)

        return JsonResponse({'message': f'Calibration Run {run.id} updated', 'calibration_run_key': run.id, 'status': run.status.name})
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"exception": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
