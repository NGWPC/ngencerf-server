import json
import logging
from json.decoder import JSONDecodeError

from django.db import transaction
from django.http import JsonResponse
from django.middleware.csrf import get_token
from rest_framework import serializers
from rest_framework import status
from rest_framework.decorators import api_view

from calibration.calibration_validators import SaveGageValidator, GageIdValidator, CalibrationRunValidator
from calibration.management.commands import ngen_cal_input
from calibration.models import Gage, ForcingSource, ObservationalSource, Domain
from views.common import get_run, JsonException, JsonError, JsonValidationError

logger = logging.getLogger(__name__)


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

        logger.debug(f'load_gage_tab() request from {request.user} - {data}')

        validate = CalibrationRunValidator(data=data)
        validate.is_valid(raise_exception=True)

        calibration_run_id = validate.data.get('calibration_run_id')

        run, errorReturn = get_run(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn

        gage = {'gage_id': run.gage.id, 'agency': run.gage.agency, 'station_name': run.gage.station_name, 'latitude': run.gage.latitude,
                'longitude': run.gage.longitude, 'altitude': run.gage.altitude} if run.gage else {}

        forcing_source_values = list(ForcingSource.objects.only('name', 'description', 'is_active').values_list('name', 'description', 'is_active'))
        observational_source_values = list(ObservationalSource.objects.only('name', 'description', 'is_active').values_list('name', 'description', 'is_active'))
        domain_values = list(Domain.objects.only('name', 'description', 'is_active').values_list('name', 'description', 'is_active'))

        # Get all the gages so the user can select another
        gages = Gage.objects.filter(is_active=True).values_list('gage_id', flat=True)

        ngen_cal_input.ready_to_run(run=run)

        response = {'calibration_run_id': run.id, 'status': run.status.name, 'gage': gage,
                    'forcing_source': run.forcing_source, 'forcing_user_filename': run.forcing_user_filename,
                    'observational_source': run.observational_source, 'observational_user_filename': run.observational_user_filename,
                    'domain_values': domain_values, 'forcing_source_values': forcing_source_values, 'observational_source_values': observational_source_values,
                    'gages': list(gages)}
        logger.debug(f'Returning to {request.user} from load_gage_tab() - {response}')

        return JsonResponse(response, safe=False)
    except (serializers.ValidationError, JSONDecodeError) as v:
        return JsonValidationError(v)
    except Exception as e:
        return JsonException(e)


@api_view(['GET', 'POST'])
# @login_required()
def get_gage(request):
    try:
        if request.method == 'POST':
            data = json.loads(request.body or '{}')
        else:
            data = request.GET

        logger.debug(f'get_gage() request from {request.user} - {data}')

        validate = GageIdValidator(data=data)
        validate.is_valid(raise_exception=True)

        gage_id = validate.data.get('gage_id')

        gage = Gage.objects.filter(gage_id=gage_id).only('gage_id', 'agency', 'station_name').values(
            'gage_id', 'agency', 'station_name', 'latitude', 'longitude', 'altitude').first()
        if not gage:
            return JsonError("Gage '{}' does not exist".format(gage_id), status.HTTP_404_NOT_FOUND)
        logger.debug(f'Returning to {request.user} from get_gage() - {gage}')

        return JsonResponse(gage, safe=False)
    except (serializers.ValidationError, JSONDecodeError) as v:
        return JsonValidationError(v)
    except Exception as e:
        return JsonException(e)


@api_view(['POST'])
# @login_required
def save_gage_tab(request):
    try:
        print('user', request.user)

        body = json.loads(request.body or '{}')
        logger.debug(f'save_gage_tab() request from {request.user} - {body}')
        validate = SaveGageValidator(data=body)
        validate.is_valid(raise_exception=True)

        calibration_run_id = validate.data.get('calibration_run_id')
        gage_id = validate.data.get('gage_id')
        forcing_source = validate.data.get('forcing_source')
        forcing_user_filename = validate.data.get('forcing_user_filename')
        observational_source = validate.data.get('observational_source')
        observational_user_filename = validate.data.get('observational_user_filename')

        run, errorReturn = get_run(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn

        if gage_id:
            gage = Gage.objects.filter(gage_id=gage_id).first()
            if not gage:
                return JsonError("Gage '{}' does not exist".format(gage_id), status.HTTP_404_NOT_FOUND)
            else:
                run.gage = gage

        run.forcing_source = forcing_source
        run.forcing_user_filename = forcing_user_filename
        run.observational_source = observational_source
        run.observational_user_filename = observational_user_filename
        # TODO Need to fill in forcing_path and observational_path with our location

        with transaction.atomic():
            run.save()

        ngen_cal_input.ready_to_run(run=run)

        response = {'message': f'Calibration Run {run.id} updated', 'calibration_run_key': run.id, 'status': run.status.name}
        logger.debug(f'Returning to {request.user} from save_gage_tab() - {response}')
        return JsonResponse(response)
    except (serializers.ValidationError, JSONDecodeError) as v:
        return JsonValidationError(v)
    except Exception as e:
        return JsonException(e)
