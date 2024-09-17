import inspect
import logging
from functools import wraps
from pathlib import Path
from typing import List, cast, Optional, Tuple

from rest_framework import status
from rest_framework.exceptions import ValidationError, ParseError
from rest_framework.response import Response

from calibration.enums import StatusEnum
from calibration.models import CalibrationRun, Status
from calibration.util.calibration_validators import ErrorResponseSerializer
from cerfServer import settings

logger = logging.getLogger(__name__)


def get_run(calibration_run_id, user, run_status=None) -> Tuple[Optional[CalibrationRun], Optional[Response]]:
    """
    Get an instance of a CalibrationRun by id, but only if it's owned by the user
    and is one of the passed-in statuses. If the CalibrationRun exists but has a
    disallowed status, return a specific error message.

    :param calibration_run_id: The ID of the CalibrationRun to retrieve.
    :param user: The user requesting the run.
    :param run_status: A list of StatusEnum members (e.g., [StatusEnum.READY, StatusEnum.SAVED]).
    :return: The CalibrationRun instance and an optional error Response.
    """
    # Default to READY and SAVED statuses if no run_status is passed
    run_status = run_status or [StatusEnum.READY, StatusEnum.SAVED]

    # Convert the StatusEnum instances to Status model instances - we cast explicitly to avoid PyCharm warnings
    allowed_statuses: List[Status] = [cast(Status, StatusEnum.from_enum(status_enum)) for status_enum in run_status]

    # Query the CalibrationRun without filtering by status
    run = (CalibrationRun.objects.filter(id=calibration_run_id, owner=user, is_deleted=False)
           .select_related('status', 'gage')
           .only('id', 'status', 'gage', 'owner')
           .first())

    if not run:
        # Return error if no CalibrationRun is found for the given ID and user
        return None, Response(
            {'error': f'Calibration Run {calibration_run_id} does not exist or is not owned by {user.username}'},
            status=status.HTTP_400_BAD_REQUEST)

    # Check if the status of the run is in the allowed statuses
    if run.status not in allowed_statuses:
        allowed_status_names = [allowed_status.name for allowed_status in allowed_statuses]
        return run, Response(
            {'error': (f'Calibration Run {calibration_run_id} is not in the allowed statuses '
                       f'({", ".join(allowed_status_names)}). '
                       f'Current status: {run.status.name}')},
            status=status.HTTP_400_BAD_REQUEST)

    # If the status matches, return the run with no errors
    return run, None


def join(items):
    if not items:
        return ''
    elif len(items) == 1:
        return items[0].lower()
    else:
        return ', '.join(items[:-1]) + ' or ' + items[-1]


def create_calibration_run_internal(request) -> CalibrationRun:
    run = CalibrationRun.objects.create(is_active=True, owner=request.user, status=Status.objects.get(name=StatusEnum.SAVED.value))

    run.job_data_dir = Path(settings.NGEN_CAL_RUN_DIR) / f'{run.id}_{run.owner.username}'
    run.save(update_fields=['job_data_dir'])
    return run


# Function wrapper to implement common exception handling
def handle_exceptions(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        original_logger = logging.getLogger(view_func.__module__)
        try:
            return view_func(request, *args, **kwargs)
        except ParseError as e:
            message = f"{type(e).__name__} - {str(e)} - while running {view_func.__module__}.{view_func.__name__}"
            original_logger.exception(message)
            return ResponseError(message, response_type='parse_error')
        except CerfException as e:
            message = f"{type(e).__name__} - {str(e)} - while running {view_func.__module__}.{view_func.__name__}"
            original_logger.exception(message)
            return ResponseError(message, response_type='error')
        except Exception as e:
            message = f"{type(e).__name__} - {str(e)} - while running {view_func.__module__}.{view_func.__name__}"
            original_logger.exception(message)
            return ResponseError(message, response_type='exception')

    return _wrapped_view


def ResponseError(message, response_type='error', validation_errors=None, http_status=status.HTTP_400_BAD_REQUEST):
    response = {'response_type': response_type, 'message': message}
    if validation_errors:
        response['validation_errors'] = validation_errors
    serializer = ErrorResponseSerializer(response)
    logger.error(serializer.data)
    return Response(serializer.data, status=http_status)


def validate_request(serializer_class, data, context=None):
    validator = None
    try:
        validator = serializer_class(data=data, context=context)
        validator.is_valid(raise_exception=True)
        return validator.data, None
    except ValidationError as e:
        calling_function = inspect.stack()[1].function  # Get the name of the calling function
        message = f"called from {calling_function}"
        validation_errors = validator.errors if validator else str(e)
        return None, ResponseError(message, response_type='validation_error', validation_errors=validation_errors)


def validate_response(serializer_class, data):
    validator = None
    try:
        validator = serializer_class(data=data)
        validator.is_valid(raise_exception=True)
        return validator, None
    except ValidationError as e:
        # Note that an exception here is most likely due to a coding error
        calling_function = inspect.stack()[1].function  # Get the name of the calling function
        message = f"Data format error in response returning from {calling_function}"
        validation_errors = validator.errors if validator else str(e)
        return None, ResponseError(message, response_type='validation_error_response', validation_errors=validation_errors)


class CerfException(Exception):
    def __init__(self, message=None, details=None):
        self.message = message
        self.details = details
        super().__init__(self.message)

    def __str__(self):
        if self.details:
            return f"{self.message}: {self.details}"
        return self.message
