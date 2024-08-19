import inspect
import logging
from functools import wraps

import rest_framework
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from calibration.enums import StatusEnum
from calibration.models import CalibrationRun
from calibration.util.calibration_validators import ErrorResponseSerializer, ValidationExceptionSerializer, ExceptionResponseSerializer

logger = logging.getLogger(__name__)


# Get an instance of a run by id, but only if owned by the user and is one of the passed in Statuses
def get_run(calibration_run_id, user, run_status=None):
    if run_status is None:
        run_status = [StatusEnum.READY, StatusEnum.SAVED]
    status_names = [s.name.lower() for s in run_status]
    run = (CalibrationRun.objects.filter(id=calibration_run_id, owner=user)
           .select_related('status', 'gage')
           .only('id', 'status', 'gage', 'owner')
           .first())
    if not run:
        return run, Response({'error': f'Calibration Run {calibration_run_id} does not exist or is not owned by {user}'},
                             status=rest_framework.status.HTTP_400_BAD_REQUEST)
    if run.status.name.lower() not in status_names:
        return run, Response({'error': f'Calibration Run {calibration_run_id} is not {join(status_names)}.  Status: {run.status.name}'},
                             status=rest_framework.status.HTTP_400_BAD_REQUEST)
    return run, None


def join(items):
    if not items:
        return ''
    elif len(items) == 1:
        return items[0].lower()
    else:
        return ', '.join(items[:-1]) + ' or ' + items[-1]


# Function wrapper to implement common exception handling
def handle_exceptions(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        original_logger = logging.getLogger(view_func.__module__)
        try:
            return view_func(request, *args, **kwargs)

        except CerfException as e:
            response = {'error': f"{str(e)} - while running {view_func.__module__}.{view_func.__name__}"}
            serializer = ErrorResponseSerializer(response)
            original_logger.error(response)
            return Response(serializer.data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            response = {'exception': f"{str(e)} - while running {view_func.__module__}.{view_func.__name__}"}
            serializer = ExceptionResponseSerializer(response)
            original_logger.exception(response)
            return Response(serializer.data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return _wrapped_view


def ResponseError(error, httpStatus=status.HTTP_400_BAD_REQUEST):
    response = {'error': error}
    serializer = ErrorResponseSerializer(response)
    logger.error(serializer.data)
    return Response(serializer.data, status=httpStatus)


def validate_request(serializer_class, data):
    try:
        validator = serializer_class(data=data)
        validator.is_valid(raise_exception=True)
        return validator, None
    except ValidationError as e:
        calling_function = inspect.stack()[1].function  # Get the name of the calling function
        response_data = {'validation_error': f"called from {calling_function} - {str(e)}"}
        logger.error(response_data)
        error_serializer = ValidationExceptionSerializer(response_data)
        return None, Response(error_serializer.data, status=status.HTTP_400_BAD_REQUEST)


def validate_response(serializer_class, data):
    validator = None
    try:
        validator = serializer_class(data=data)
        validator.is_valid(raise_exception=True)
        return validator, None
    except ValidationError as _:
        # Note that an exception here is most likely due to a coding error
        calling_function = inspect.stack()[1].function  # Get the name of the calling function
        error_message = f"Data format error in response returning from {calling_function}"
        if validator is not None:
            error_message += f" - {validator.errors}"
        response_data = {'error': error_message}
        logger.error(response_data)
        error_serializer = ErrorResponseSerializer(response_data)

        return None, Response(error_serializer.data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CerfException(Exception):
    def __init__(self, message=None, details=None):
        self.message = message
        self.details = details
        super().__init__(self.message)

    def __str__(self):
        if self.details:
            return f"{self.message}: {self.details}"
        return self.message
