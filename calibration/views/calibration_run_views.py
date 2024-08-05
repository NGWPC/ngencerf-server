import json
import logging
from json.decoder import JSONDecodeError

from django.http import JsonResponse
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.util.calibration_validators import CalibrationRunValidator, IsReadyResponseSerializer, GenericResponseSerializer
from calibration.views import ngen_cal_input
from calibration.views.common import get_run, ResponseException, ResponseValidationError, ResponseJsonError

logger = logging.getLogger(__name__)


@extend_schema(
    request=CalibrationRunValidator,
    responses={
        200: IsReadyResponseSerializer
    },
    description="Check if a job is ready to run"
)
@api_view(['GET', 'POST'])
# @login_required()
def is_ready(request):
    try:
        print('user', request.user)

        body = json.loads(request.body or '{}')
        logger.debug(f'is_ready() request from {request.user} - {body}')

        validator = CalibrationRunValidator(data=body)
        validator.is_valid(raise_exception=True)

        calibration_run_id = validator.data.get('calibration_run_id')

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
    except JSONDecodeError as e:
        return ResponseJsonError(e)
    except serializers.ValidationError as v:
        return ResponseValidationError(v)
    except Exception as e:
        return ResponseException(e)


@extend_schema(
    request=CalibrationRunValidator,
    responses={
        200: GenericResponseSerializer
    },
    description="Run a calibration"
)
@api_view(['POST'])
def run_calibration(request):
    try:
        print('user', request.user)

        body = json.loads(request.body or '{}')
        logger.debug(f'run_calibration() request from {request.user} - {body}')

        validator = CalibrationRunValidator(data=body)
        validator.is_valid(raise_exception=True)

        calibration_run_id = validator.data.get('calibration_run_id')

        run, errorReturn = get_run(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn

        messages = ngen_cal_input.ready_to_run(run, build=True)

        # TODO Normally, we return if not ready, but for testing, we'll skip this test
        # if messages:
        #     return JsonError(f'Calibration Run {calibration_run_id} is not ready')

        response = {'message': f'Calibration Run {run.id} has been submitted', 'calibration_run_id': calibration_run_id, 'status': run.status.name}
        serializer = GenericResponseSerializer(response)
        logger.debug(f'Returning to {request.user} from run_calibration() - {serializer.data}')
        return JsonResponse(serializer.data)
    except JSONDecodeError as e:
        logger.exception(e)
        return Response({'validation_error': 'JSON parsing error - ' + str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except serializers.ValidationError as e:
        logger.exception(e)
        return Response({'validation_error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception(e)
        return Response({'exception': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


