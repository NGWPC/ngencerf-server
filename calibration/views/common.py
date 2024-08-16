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
    run = CalibrationRun.objects.filter(id=calibration_run_id, owner=user).select_related('status', 'gage').first()
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
        try:
            return view_func(request, *args, **kwargs)
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
    return _wrapped_view


def ResponseError(error, httpStatus=status.HTTP_400_BAD_REQUEST):
    response = {'error': error}
    serializer = ErrorResponseSerializer(response)
    logger.error(serializer.data)
    return Response(serializer.data, status=httpStatus)
