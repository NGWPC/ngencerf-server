import json
import logging
from json.decoder import JSONDecodeError

from django.http import JsonResponse
from rest_framework import serializers
from rest_framework.decorators import api_view

from calibration.calibration_validators import CalibrationRunValidator
from views import ngen_cal_input
from views.common import get_run, JsonException, JsonError, JsonValidationError

logger = logging.getLogger(__name__)


@api_view(['GET', 'POST'])
# @login_required()
def is_ready(request):
    try:
        print('user', request.user)

        body = json.loads(request.body or '{}')
        logger.debug(f'is_ready() request from {request.user} - {body}')

        validate = CalibrationRunValidator(data=body)
        validate.is_valid(raise_exception=True)

        calibration_run_id = validate.data.get('calibration_run_id')

        run, errorReturn = get_run(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn

        messages = ngen_cal_input.ready_to_run(run)

        response = {'calibration_run_id': run.id, 'status': run.status.name}
        ready_not_ready = 'not ready' if messages else 'ready'
        response['message'] = f'Calibration Run {run.id} is {ready_not_ready}'
        if messages:
            response['errors'] = messages

        logger.debug(f'Returning to {request.user} from is_ready() - {response}')
        return JsonResponse(response)
    except (serializers.ValidationError, JSONDecodeError) as v:
        return JsonValidationError(v)
    except Exception as e:
        return JsonException(e)


@api_view(['POST'])
def run_calibration(request):
    try:
        print('user', request.user)

        body = json.loads(request.body or '{}')
        logger.debug(f'run_calibration() request from {request.user} - {body}')

        validate = CalibrationRunValidator(data=body)
        validate.is_valid(raise_exception=True)

        calibration_run_id = validate.data.get('calibration_run_id')

        run, errorReturn = get_run(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn

        messages = ngen_cal_input.ready_to_run(run)
        if messages:
            return JsonError(f'Calibration Run {calibration_run_id} is not ready')

        response = {'message': f'Calibration Run {run.id} has been submitted', 'calibration_run_id': calibration_run_id, 'status': run.status.name}
        logger.debug(f'Returning to {request.user} from run_calibration() - {response}')
        return JsonResponse(response)
    except (serializers.ValidationError, JSONDecodeError) as v:
        return JsonValidationError(v)
    except Exception as e:
        return JsonException(e)


