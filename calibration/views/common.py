import base64
import inspect
import logging
from datetime import timedelta, datetime
from functools import wraps
from pathlib import Path
from typing import List, cast, Optional, Tuple

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.decorators import permission_classes
from rest_framework.exceptions import ValidationError, ParseError
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import AccessToken

from calibration.enums import StatusEnum
from calibration.models import CalibrationRun, Status, ValidationRun
from calibration.util.calibration_validators import ErrorResponseSerializer
from django.conf import settings

logger = logging.getLogger(__name__)

SLOTH = 'SLoTH'


def get_run(calibration_run_id, user, run_status=None) -> Tuple[Optional[CalibrationRun], Optional[Response]]:
    """
    Get an instance of a CalibrationRun by id, but only if it's owned by the user
    and is one of the passed-in statuses. If the CalibrationRun exists but has a
    disallowed status, return a specific error message.

    :param calibration_run_id: The ID of the CalibrationRun to retrieve.
    :param user: The user requesting the run.
    :param run_status: A list of StatusEnum members (e.g., [StatusEnum.READY, StatusEnum.SAVED]).
    :return: A tuple containing the CalibrationRun (or None if not found) and an optional Response with an error.
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
            {'error': (f'Calibration Run {calibration_run_id} is not '
                       f'({join_with_or(allowed_status_names)}). '
                       f'Current status: {run.status.name}')},
            status=status.HTTP_400_BAD_REQUEST)

    # If the status matches, return the run with no errors
    return run, None


def join_with_or(items):
    """
       Join a list of strings into a single string, using commas and 'or' for the last item.

       :param items: A list of strings.
       :return: A grammatically joined string.
       """
    if not items:
        return ''
    elif len(items) == 1:
        return items[0].lower()
    else:
        return ', '.join(items[:-1]) + ' or ' + items[-1]


def png_str_to_base64_url(png_str):
    """
     Convert a PNG image in binary format to a base64-encoded data URL.

     :param png_str: The binary data of a PNG image.
     :return: A base64-encoded string for embedding images in URLs.
     """
    if png_str:
        base64_str = base64.b64encode(png_str).decode('utf-8')
        return f'data:image/png;base64,{base64_str}'
    else:
        return None


def create_calibration_run_internal(user) -> CalibrationRun:
    """
    Create a new CalibrationRun object for the user making the request.
    Ensures that the job directory is created and assigns the 'SAVED' status by default.

    :param user: The owner of the calibration run.
    :return: The newly created CalibrationRun instance.
     """
    run = CalibrationRun.objects.create(is_active=True, owner=user, status=StatusEnum.from_enum(StatusEnum.SAVED))

    run.job_data_dir = Path(settings.NGEN_CAL_RUN_DIR) / f'{run.id}_{run.owner.username}'
    # The directory will be created when we build the job in ready_to_run().  But clean up any existing directory now
    if run.job_data_dir.exists():
        # Rename the existing one
        # This should never happen in production, but just in case
        new_name = run.job_data_dir.with_name(f"{run.job_data_dir.name}_{datetime.now().isoformat()}")
        run.job_data_dir.rename(new_name)

    # This is always true
    run.automatic_validation = True
    run.save(update_fields=['job_data_dir', 'automatic_validation'])
    return run


def create_validation_run_internal(run: CalibrationRun) -> ValidationRun:
    """
    Create a new ValidationRun object for the given CalibrationRun.

    :param run: The calibration run that this validation run is associated with.
    :return: The newly created ValidationRun instance.
    """
    validation = ValidationRun.objects.create(status=StatusEnum.from_enum(StatusEnum.SAVED), calibration_run=run)

    return validation


token_slurm_scope = 'slurm_callback'
token_ngen = 'ngen'


def generate_custom_token(user: get_user_model(), scope: str) -> str:
    """
    Generate a JWT access token for a user, with a custom scope and a 24-hour expiration.

    :param user: The user for whom the token is being generated.
    :param scope: The custom scope to be embedded in the token.
    :return: The string representation of the access token.
    """
    access = AccessToken.for_user(user)
    # Set the expiration to 24 hours from now
    access.set_exp(lifetime=timedelta(hours=24))

    # Set our custom scope
    access['scope'] = scope

    return str(access)


def auth_scope_required(scope):
    """
    Custom decorator to require a specific token scope.
    """
    return permission_classes([lambda: CheckTokenScope(scope)])


class CheckTokenScope(BasePermission):
    """
    Permission class to check if the provided JWT token contains a specific scope.
    """

    def __init__(self, required_scope):
        self.required_scope = required_scope

    def has_permission(self, request, view):
        # Ensure that the user is authenticated and has a valid token
        if not request.user or not request.auth:
            logger.debug(f"No token or user provided - user: {request.user}, auth: {request.auth}")
            return False

        # We should already have a validated token in request.auth
        token = request.auth

        # Log the available scopes and the required one
        token_scope = token.get('scope', '').split()
        logger.debug(f"Token scope: {token_scope}, Required scope: {self.required_scope}")

        # Make sure we have our custom scope
        if self.required_scope not in token_scope:
            logger.debug(f"Permission denied: required scope '{self.required_scope}' not in token scope {token_scope}")
            return False

        return True


# Function wrapper to implement common exception handling
def handle_exceptions(view_func):
    """
    A decorator to wrap view functions and handle common exceptions.
    Logs the exception and returns a formatted error response when an exception occurs.

    :param view_func: The view function to wrap.
    :return: The wrapped view function with exception handling.
    """

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


# Get the valid path for a file that can come from Hydrofabric or user-upload
def get_valid_path(source, hydrofabric_path, upload_enum, get_path_func):
    job_specific_file = get_path_func()
    # print('get_valid_path', source, hydrofabric_path, upload_enum, get_path_func())

    if source:
        if source == upload_enum.from_enum(upload_enum):
            # Check job-specific path first
            if job_specific_file and Path(job_specific_file).exists():
                return job_specific_file
        # If not found or source is different, check the hydrofabric path
        if hydrofabric_path and Path(hydrofabric_path).exists():
            return hydrofabric_path

    return None


def truncate_large_fields(data, fields_to_truncate=None, max_length=100):
    """
    Truncate large fields (lists, dicts, strings) in the data to prevent logging large values.
    :param data: Dictionary of response data.
    :param fields_to_truncate: List of fields to truncate in logs.
    :param max_length: The maximum number of characters/items to display before truncating.
    :return: Redacted dictionary for logging.
    """
    if fields_to_truncate is None:
        fields_to_truncate = []

    truncated_data = data.copy()
    for field in fields_to_truncate:

        if field in truncated_data:
            value = truncated_data[field]
            # Truncate strings if they exceed max_length
            if isinstance(value, str) and len(value) > max_length:
                truncated_data[field] = f"{value[:max_length]}... (truncated)"
            # Truncate lists if they exceed max_length
            elif isinstance(value, list) and len(value) > max_length:
                truncated_data[field] = value[:max_length] + [f"... (truncated, {len(value)} total items)"]
            # Truncate dicts by taking the first max_length key-value pairs
            elif isinstance(value, dict) and len(value) > max_length:
                truncated_dict = {k: value[k] for k in list(value)[:max_length]}
                truncated_dict["..."] = f"(truncated, {len(value)} total keys)"
                truncated_data[field] = truncated_dict
    return truncated_data


def ResponseError(message, response_type='error', validation_errors=None, http_status=status.HTTP_400_BAD_REQUEST):
    """
    Return a standardized error response, with optional validation errors.

    :param message: The error message to include.
    :param response_type: The type of error (default is 'error').
    :param validation_errors: Optional validation errors to include.
    :param http_status: The HTTP status code for the response (default is 400).
    :return: A formatted Response object with the error details.
    """
    response = {'response_type': response_type, 'message': message}
    if validation_errors:
        response['validation_errors'] = validation_errors
    serializer = ErrorResponseSerializer(response)
    logger.error(serializer.data)
    return Response(serializer.data, status=http_status)


def validate_request(serializer_class, data, context=None):
    """
    Validate request data using the specified serializer class.
    Returns the validated data or an error response if validation fails.

    :param serializer_class: The serializer class to use for validation.
    :param data: The data to be validated.
    :param context: Optional context for the serializer.
    :return: The validated data or an error response.
    """
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


def validate_response(serializer_class, data, fields_to_truncate=None, max_length=100):
    validator = None
    try:
        validator = serializer_class(data=data)
        validator.is_valid(raise_exception=True)

        # Redact large fields before logging
        logger.debug(f'Validated response data: {truncate_large_fields(data, fields_to_truncate, max_length)}')

        return validator, None
    except ValidationError as e:
        # Log the full data and errors in case of validation failure
        logger.error(f"Validation error with data: {truncate_large_fields(data, fields_to_truncate, max_length)}")
        logger.error(f"Validation errors: {str(e)}")

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
