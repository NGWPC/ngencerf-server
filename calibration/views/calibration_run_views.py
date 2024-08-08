import importlib.util
import json
import logging
import os
import sys
from json.decoder import JSONDecodeError

from drf_spectacular.utils import extend_schema, PolymorphicProxySerializer
from git import Repo
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from calibration.util.calibration_validators import CalibrationRunValidator, IsReadyResponseSerializer, GenericResponseSerializer, \
    ErrorResponseSerializer, ExceptionResponseSerializer, ValidationErrorSerializer, ValidationExceptionSerializer
from calibration.util.ngen_locations import create_input_dir
from calibration.views import ngen_cal_input
from calibration.views.common import get_run
from cerfServer.settings import NGEN_REPO_ROOT, NGEN_CAL_REPO_ROOT

logger = logging.getLogger(__name__)


@extend_schema(
    request=CalibrationRunValidator,
    responses={
        200: IsReadyResponseSerializer,
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
    description="Check if a job is ready to run"
)
@api_view(['GET', 'POST'])
# @permission_classes([AllowAny])()
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

        messages, _ = ngen_cal_input.ready_to_run(run)

        response = {'calibration_run_id': run.id, 'status': run.status.name}
        ready_not_ready = 'not ready' if messages else 'ready'
        response['message'] = f'Calibration Run {run.id} is {ready_not_ready}'
        if messages:
            response['errors'] = messages

        serializer = IsReadyResponseSerializer(response)
        logger.debug(f'Returning to {request.user} from is_ready() - {serializer.data}')
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


@extend_schema(
    request=None,
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

        messages, config_file = ngen_cal_input.ready_to_run(run, build=True)
        print('config file', config_file)

        # TODO Normally, we return if not ready, but for testing, we'll skip this test
        # if messages:
        #     return JsonError(f'Calibration Run {calibration_run_id} is not ready')

        # Save the latest git hash or ngen and ngen-cal
        run.ngen_commit_hash = Repo(NGEN_REPO_ROOT).head.object.hexsha
        run.ngen_cal_commit_hash = Repo(NGEN_CAL_REPO_ROOT).head.object.hexsha
        run.save()

        # Get access to create_input.py 
        parent_dir = os.path.dirname(create_input_dir)
        create_input_py = 'create_input.py'
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        spec = importlib.util.spec_from_file_location('createInput.create_input', os.path.join(create_input_dir, create_input_py))

        if spec is None:
            raise Exception(f"Cannot find 'create_input.py' in {create_input_dir}")
        else:
            # Create module from the spec
            create_input = importlib.util.module_from_spec(spec)

            spec.loader.exec_module(create_input)
            print('create_input imported successfully')

            sys.argv = [create_input_py, config_file]
            create_input.main()

            response = {'message': f'Calibration Run {run.id} has been submitted', 'calibration_run_id': calibration_run_id,
                        'status': run.status.name}
            serializer = GenericResponseSerializer(response)
            logger.debug(f'Returning to {request.user} from run_calibration() - {serializer.data}')
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
