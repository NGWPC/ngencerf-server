import json
import logging
from json import JSONDecodeError


from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from calibration.util.calibration_validators import ValidationErrorSerializer, ValidationExceptionSerializer, ExceptionResponseSerializer, \
    CalibrationRunValidator, ExportValidator
from calibration.views.common import get_run, ResponseError

logger = logging.getLogger(__name__)


@api_view(['POST'])
# @permission_classes([AllowAny])
def export(request):
    try:
        print('user', request.user)
        body = json.loads(request.body or '{}')
        logger.debug(f'export() request from {request.user} - {body}')

        validator = CalibrationRunValidator(data=body)
        validator.is_valid(raise_exception=True)

        calibration_run_id = 1

        export_file = {}

        run, errorReturn = get_run(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn

        export_file['gage'] = run.gage.gage_id
        export_file['formulation_name'] = run.formulation_name

        print('export_file', export_file)

        export_file = {key: value for key, value in export_file.items() if value not in [None, '', [], {}]}

        serializer = ExportValidator(data=export_file)
        if not serializer.is_valid():
            return ResponseError(f'Data format error returning from export() - {serializer.errors}',
                                 httpStatus=status.HTTP_500_INTERNAL_SERVER_ERROR)

        logger.debug(f'Returning to {request.user} from load_formulation_tab() - {serializer.data}')
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
