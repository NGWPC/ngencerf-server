import json
import logging
from json.decoder import JSONDecodeError

from django.db import transaction
from drf_spectacular.utils import extend_schema, PolymorphicProxySerializer
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from calibration.enums import StatusEnum
from calibration.models import Iteration
from calibration.util.calibration_validators import ReportIterationValidator, GenericResponseSerializer, ErrorResponseSerializer, \
    ExceptionResponseSerializer, ValidationErrorSerializer, ValidationExceptionSerializer, CalibrationRunValidator
from calibration.views.common import get_run

logger = logging.getLogger(__name__)


@extend_schema(
    request=ReportIterationValidator,
    responses={
        200: GenericResponseSerializer,
        400: PolymorphicProxySerializer(
            component_name='MultipleErrorResponse',
            serializers=[
                ValidationExceptionSerializer,
                ValidationErrorSerializer,
                ErrorResponseSerializer,
            ],
            resource_type_field_name=None
        ),
        500: ExceptionResponseSerializer
    },
    description="Report iteration of a running calibration"
)
# Called by ngen_cal
@api_view(['POST'])
# @permission_classes([AllowAny])
def report_iteration(request):
    try:
        print('user', request.user)
        body = json.loads(request.body or '{}')
        logger.debug(f'report_iteration() request from {request.user} - {body}')

        validator = ReportIterationValidator(data=body)
        validator.is_valid(raise_exception=True)

        calibration_run_id = validator.data.get('calibration_run_id')
        iteration_number = validator.data.get('iteration')

        run, errorReturn = get_run(calibration_run_id, request.user, status=[StatusEnum.RUNNING])
        if errorReturn:
            return errorReturn

        with transaction.atomic():
            # TODO Do we always create a new one, or check to see if this iteration number exists?
            # TODO calibration_output_variable_value is required, so add placeholder for now.  Unless it shouldn't be required?
            Iteration.objects.create(calibration_run=run, iteration_num=iteration_number, calibration_output_variable_value=0)
            response = {'message': f'Iteration {iteration_number} set for Calibration Run {run.id}', 'calibration_run_id': run.id,
                        'status': run.status.name}
            serializer = GenericResponseSerializer(response)
            logger.debug(f'Returning to {request.user} from report_iteration() - {serializer.data}')

            return Response(serializer.data)
    except JSONDecodeError as e:
        response = {'validation_error': 'JSON parsing error - ' + str(e)}
        serializer = ValidationErrorSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)
    except ValidationError as e:
        response = {'validation_error': str(e)}
        serializer = ValidationExceptionSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        response = {'exception': str(e)}
        serializer = ExceptionResponseSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


extend_schema(
    request=CalibrationRunValidator,
    responses={
        200: GenericResponseSerializer,
        400: PolymorphicProxySerializer(
            component_name='MultipleErrorResponse',
            serializers=[
                ValidationExceptionSerializer,
                ValidationErrorSerializer,
                ErrorResponseSerializer,
            ],
            resource_type_field_name=None
        ),
        500: ExceptionResponseSerializer
    },
    description="Report iteration of a running calibration"
)
# Called by ngen_cal
@api_view(['POST'])
# @permission_classes([AllowAny])
def get_iteration(request):
    try:
        print('user', request.user)
        if request.method == 'POST':
            data = json.loads(request.body or '{}')
        else:
            data = request.GET
        logger.debug(f'get_iteration() request from {request.user} - {data}')

        validator = CalibrationRunValidator(data=data)
        validator.is_valid(raise_exception=True)

        calibration_run_id = validator.data.get('calibration_run_id')

        # TODO read output file

        run, errorReturn = get_run(calibration_run_id, request.user, status=[StatusEnum.RUNNING, StatusEnum.DONE, StatusEnum.FAILED])
        if errorReturn:
            return errorReturn

        iteration = 1
        response = {'message': f'Last iteration for Calibration Run {run.id} is {iteration}', 'calibration_run_id': run.id,
                    'status': run.status.name, 'iteration': iteration}
        serializer = GenericResponseSerializer(response)
        logger.debug(f'Returning to {request.user} from report_iteration() - {serializer.data}')

        return Response(serializer.data)
    except JSONDecodeError as e:
        response = {'validation_error': 'JSON parsing error - ' + str(e)}
        serializer = ValidationErrorSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)
    except ValidationError as e:
        response = {'validation_error': str(e)}
        serializer = ValidationExceptionSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        response = {'exception': str(e)}
        serializer = ExceptionResponseSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
