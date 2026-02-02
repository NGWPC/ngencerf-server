import json
import logging
import math
import os
import secrets
import threading
import time
import zipfile
from collections import defaultdict
from datetime import datetime

from django.conf import settings
from django.core.cache import cache
from django.db.models import F, QuerySet
from django.http import FileResponse
from django.urls import reverse
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from calibration.enums import StatusEnum, ValidationMetricPeriod, ValidationType, LogCategory, LogName
from calibration.models import Iteration, NWMRetrospectiveMetrics, CalibrationRun, ValidationRun, IterationParameter, IterationMetric
from calibration.util.calibration_validators import CalibrationRunSerializer, CalibrationOrValidationOrColdStartOrForecastOrVerificationRunSerializer, \
    ErrorResponseSerializer, GetCalibrationDataByIterationResponseSerializer, GetLogsResponseSerializer, \
    GetLogNamesResponseSerializer, GetLogRequestSerializer, GetLogStatusRequestSerializer, \
    GetLogStatusResponseSerializer, GenericMessageWithIdResponseSerializer, GetZipStatusSerializer, GetZipDownloadUrlResponseSerializer
from calibration.util.ngen_locations import get_calibration_stdout_file, get_validation_best_stdout_file, get_validation_control_stdout_file, \
    get_validation_iteration_stdout_file, get_ngen_stdout_log_filename, get_ngen_log_path
from calibration.views.calibration_forecast_views import get_forecast_log, get_cold_start_log
from calibration.views.calibration_verification_views import get_verification_log
from calibration.views.called_from import get_caller_name
from calibration.views.common import get_calibration_run, handle_exceptions, validate_response, validate_request, truncate_large_fields, \
    get_validation_run, CerfException, process_worker_dirs, get_user_email, ResponseError, get_elapsed_str, \
    get_forecast_run, get_verification_run

logger = logging.getLogger(__name__)


def normalize_float(value):
    """
    Normalize numeric values for JSON serialization.

    - JSON does NOT support NaN or +/-Infinity.
    - Django/DRF will happily pass these through until serialization,
      where they can cause hard failures or invalid JSON.
    - This helper converts any non-finite float (NaN, +inf, -inf) to None.
    - Non-float values (ints, strings, dicts, lists, etc.) are returned unchanged.

    This is intentionally lightweight and meant to be applied ONLY at the
    points where floating-point values originate (metrics, objective values),
    instead of recursively walking the entire response payload.
    """

    # Preserve None as-is
    if value is None:
        return None

    # Only floats can be NaN or Infinity; ints are always safe
    if isinstance(value, float) and not math.isfinite(value):
        return None

    # All other values pass through unchanged
    return value


@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: GetCalibrationDataByIterationResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Retrieve metrics and parameters by iteration for a specific calibration run"
)
@api_view(['GET', 'POST'])
@handle_exceptions
def get_calibration_data_by_iteration(request: Request) -> Response:
    """
    Retrieves calibration data by iteration for a specific calibration run.

    - Handles user authentication and validation.
    - Fetches retrospective metrics and iteration data.
    - Constructs a response containing iterations, parameters, metrics, and validation information.

    :param request: The HTTP request object containing calibration run data.
    :return: JSON response with calibration data or error information.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=[StatusEnum.DONE])
    if error_return:
        return error_return

    # Fetch retrospective metrics data associated with the calibration run
    nwm_retrospective_data = list(
        NWMRetrospectiveMetrics.objects
        .filter(period=ValidationMetricPeriod.valid.value, calibration_run=run)
        .select_related('metric')
        .annotate(
            metric_name=F('metric__name'),
            metric_display_name=F('metric__display_name'),
        )
        .values('metric_name', 'metric_display_name', 'metric_value')
    )

    retrospective_data = [{'name': 'NWM 3.0', 'data': nwm_retrospective_data}]

    iterations = list(get_iterations_for_calibration_job(run))
    iteration_ids = [it.id for it in iterations]

    # Prefetch validation runs for all iterations
    validation_runs = (
        ValidationRun.objects
        .filter(
            iteration_id__in=iteration_ids,
            status__in=[
                StatusEnum.DONE.db_instance,
                StatusEnum.RUNNING.db_instance,
                StatusEnum.SUBMITTED.db_instance,
            ],
        )
        .only('id', 'iteration_id')
    )

    validation_runs_by_iteration = {vr.iteration_id: vr for vr in validation_runs}

    params_by_iter = defaultdict(list)
    for p in (
            IterationParameter.objects
                    .filter(iteration_id__in=iteration_ids)
                    .select_related('calibration_parameter')
                    .values(
                'iteration_id',
                'calibration_parameter__name',
                'tuned_value',
            )
    ):
        params_by_iter[p['iteration_id']].append({
            'parameter_name': p['calibration_parameter__name'],
            'parameter_value': p['tuned_value'],
        })

    metrics_by_iter = defaultdict(list)
    for m in (
            IterationMetric.objects
                    .select_related('metric')
                    .filter(iteration_id__in=iteration_ids)
                    .values(
                'iteration_id',
                'metric__name',
                'metric__display_name',
                'metric_value',
            )
    ):
        metrics_by_iter[m['iteration_id']].append({
            'metric_name': m['metric__name'],
            'metric_display_name': m['metric__display_name'],
            'metric_value': normalize_float(m['metric_value']),
        })

    # Construct iteration data with parameters, metrics, and validation reference
    iteration_data = []
    for iteration in iterations:
        validation_run = validation_runs_by_iteration.get(iteration.id)

        iteration_element = {
            'iteration_num': iteration.iteration_num,
            'iteration_id': iteration.id,
            'worker_name': iteration.worker_name,
            'best_params': iteration.best_params,
            'objective_function_value': normalize_float(iteration.objective_function_value),
            'parameters': params_by_iter.get(iteration.id, []),
            'metrics': metrics_by_iter.get(iteration.id, []),
        }

        if validation_run:
            iteration_element['validation_run_id'] = validation_run.id

        iteration_data.append(iteration_element)

    response = {
        'message': f'Calibration Job {run.id}, data retrieved',
        # Will be none for LSTM
        'objective_function_metric': run.objective_function.name if run.objective_function else None,
        'iteration_data': iteration_data,
        'retrospective_data': retrospective_data
    }

    response_validator, error_response = validate_response(
        GetCalibrationDataByIterationResponseSerializer,
        response,
        fields_to_truncate=['iteration_data'],
        max_length=10
    )
    if error_response:
        return error_response

    logger.debug(
        f'Returning to {get_user_email(request)} from {get_caller_name()}(){get_elapsed_str(request)} - '
        f'{json.dumps(truncate_large_fields(response_validator.data, fields_to_truncate=["iteration_data"], max_length=10))}'
    )

    return Response(response_validator.data)


def get_iterations_for_calibration_job(calibration_run: CalibrationRun, worker_name: str | None = None) -> QuerySet[Iteration]:
    """
        Fetches iterations for the given calibration run.

        - Optionally filters by worker name.
        - Prefetches related parameters and metrics for optimized retrieval.

        :param calibration_run: The CalibrationRun instance to fetch iterations for.
        :param worker_name: Optional worker name to filter iterations.
        :return: QuerySet of Iteration objects associated with the calibration run.
        """
    queryset = Iteration.objects.filter(calibration_run=calibration_run)

    if worker_name:
        queryset = queryset.filter(worker_name=worker_name)

    return (
        queryset
        .select_related('calibration_run')
        .prefetch_related('iterationparameter_set__calibration_parameter',
                          'iterationmetric_set')
        .order_by('worker_name', 'iteration_num')
    )


@extend_schema(
    request=CalibrationOrValidationOrColdStartOrForecastOrVerificationRunSerializer,
    responses={
        200: GetLogNamesResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Retrieve available log names for a given validation run"
)
@api_view(['POST', 'GET'])
@handle_exceptions
def get_log_names(request: Request) -> Response:
    """
    Retrieves a list of available log names for a specific calibration or validation run.

    - Handles request validation and user permissions.
    - Returns logs categorized by their association (calibration, validation, forecast, cold start, verification, global).

    :param request: The HTTP request object containing validation run ID.
    :return: JSON response with log names or error details.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {data}')

    validator, error_return = validate_request(CalibrationOrValidationOrColdStartOrForecastOrVerificationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    validation_run_id = validator.get('validation_run_id')
    forecast_run_id = validator.get('forecast_run_id')
    verification_run_id = validator.get('verification_run_id')

    if validation_run_id:
        validation_run, error_return = get_validation_run(
            validation_run_id,
            request.user,
            run_status=[StatusEnum.RUNNING, StatusEnum.SUBMITTED, StatusEnum.DONE, StatusEnum.FAILED, StatusEnum.CANCELLED, StatusEnum.SERVER_ERROR]
        )
        if error_return:
            return error_return

        # Define available log categories and names
        log_names = [
            {LogCategory.CALIBRATION.value: ['ngen stdout', 'ngen-cal stdout']},
            {LogCategory.VALIDATION.value: ['ngen-cal stdout']},
            {LogCategory.GLOBAL.value: ['ngen']},
        ]
    elif forecast_run_id:
        forecast_run, error_return = get_forecast_run(
            forecast_run_id,
            request.user,
            run_status=[StatusEnum.SAVED, StatusEnum.RUNNING, StatusEnum.SUBMITTED, StatusEnum.DONE, StatusEnum.FAILED, StatusEnum.CANCELLED,
                        StatusEnum.SERVER_ERROR]
        )
        if error_return:
            return error_return
        cold_start_run = forecast_run.cold_start_run

        # Define available log categories and names
        log_names = [
            {LogCategory.FORECAST.value: ['forecast stdout', 'ngen stdout', 'mswm', 'ngen']}
        ]
        if cold_start_run:
            log_names.append({LogCategory.COLD_START.value: ['cold start stdout', 'ngen stdout', 'mswm', 'ngen']})
    elif verification_run_id:
        verification_run, error_return = get_verification_run(
            verification_run_id,
            request.user,
            run_status=[StatusEnum.RUNNING, StatusEnum.SUBMITTED, StatusEnum.DONE, StatusEnum.FAILED, StatusEnum.CANCELLED, StatusEnum.SERVER_ERROR]
        )
        if error_return:
            return error_return

        # Define available log categories and names
        log_names = [
            {LogCategory.VERIFICATION.value: ['verification', 'verification stdout']}
        ]
    else:
        calibration_run, error_return = get_calibration_run(
            calibration_run_id,
            request.user,
            run_status=[StatusEnum.RUNNING, StatusEnum.SUBMITTED, StatusEnum.DONE, StatusEnum.FAILED, StatusEnum.CANCELLED, StatusEnum.SERVER_ERROR]
        )
        if error_return:
            return error_return

        # Define available log categories and names
        log_names = [
            {LogCategory.CALIBRATION.value: ['ngen stdout', 'ngen-cal stdout']},
            {LogCategory.GLOBAL.value: ['ngen']},
        ]

    response = {'log_names': log_names}

    response_validator, error_response = validate_response(GetLogNamesResponseSerializer, response)
    if error_response:
        return error_response

    logger.debug(
        f'Returning to {get_user_email(request)} from {get_caller_name()}(){get_elapsed_str(request)} - {json.dumps(response_validator.data)}')
    return Response(response_validator.data)


VALID_LOG_NAMES = {
    LogCategory.CALIBRATION: [LogName.NGEN_CAL_STDOUT, LogName.NGEN_STDOUT],
    LogCategory.VALIDATION: [LogName.NGEN_CAL_STDOUT, LogName.NGEN_STDOUT],
    LogCategory.FORECAST: [LogName.FORECAST_STDOUT, LogName.NGEN_STDOUT, LogName.MSWM, LogName.NGEN],
    LogCategory.COLD_START: [LogName.COLD_START_STDOUT, LogName.NGEN_STDOUT, LogName.MSWM, LogName.NGEN],
    LogCategory.VERIFICATION: [LogName.VERIFICATION, LogName.VERIFICATION_STDOUT],
    LogCategory.GLOBAL: [LogName.NGEN]
}


def validate_log_name(log_category: LogCategory, log_name: LogName):
    """
    Validates whether the provided log name is valid for the given log category.

    - Ensures the log name exists in the predefined valid logs for the category.

    :param log_category: The category of the log (enum representation of LogCategory).
    :param log_name: The log name to validate.
    :raises ValueError: If the log name is not valid for the given category.
    """
    valid_logs = VALID_LOG_NAMES.get(log_category, [])

    valid_log_values = [log.value for log in valid_logs]

    if log_name not in valid_logs:
        raise ValueError(f"Invalid log name '{log_name.value}' for category '{log_category.value}'. Valid options are: {valid_log_values}.")


@extend_schema(
    request=GetLogRequestSerializer,
    responses={
        200: GetLogsResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Retrieve a specific log file with pagination support"
)
@api_view(['GET', 'POST'])
@handle_exceptions
def get_log(request: Request) -> Response:
    """
    Retrieves a specific log file for a calibration, validation, forecast, cold start, or verification run.

    - Supports pagination for large log files.
    - Validates log category and log name.

    :param request: The HTTP request object containing run and log information.
    :return: JSON response with log file content or error details.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {data}')

    validator, error_return = validate_request(GetLogRequestSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    validation_run_id = validator.get('validation_run_id')
    forecast_run_id = validator.get('forecast_run_id')
    verification_run_id = validator.get('verification_run_id')
    log_category = LogCategory(validator.get('log_category'))
    log_name = LogName(validator.get('log_name'))
    start = validator.get('start')
    limit = validator.get('limit')

    # Validate log category and log name
    try:
        validate_log_name(log_category, log_name)
    except ValueError as e:
        raise CerfException(str(e))

    validation_run = None
    forecast_run = None
    cold_start_run = None
    verification_run = None

    if validation_run_id:
        validation_run, error_return = get_validation_run(
            validation_run_id,
            request.user,
            run_status=[StatusEnum.RUNNING, StatusEnum.SUBMITTED, StatusEnum.DONE, StatusEnum.FAILED, StatusEnum.CANCELLED, StatusEnum.SERVER_ERROR]
        )
        if error_return:
            return error_return
        calibration_run = validation_run.calibration_run
    elif forecast_run_id:
        forecast_run, error_return = get_forecast_run(
            forecast_run_id,
            request.user,
            run_status=[StatusEnum.SAVED, StatusEnum.RUNNING, StatusEnum.SUBMITTED, StatusEnum.DONE, StatusEnum.FAILED, StatusEnum.CANCELLED,
                        StatusEnum.SERVER_ERROR]
        )
        if error_return:
            return error_return
        calibration_run = forecast_run.calibration_run
        cold_start_run = forecast_run.cold_start_run
    elif verification_run_id:
        verification_run, error_return = get_verification_run(
            verification_run_id,
            request.user,
            run_status=[StatusEnum.RUNNING, StatusEnum.SUBMITTED, StatusEnum.DONE, StatusEnum.FAILED, StatusEnum.CANCELLED, StatusEnum.SERVER_ERROR]
        )
        if error_return:
            return error_return
        calibration_run = verification_run.forecast_run.calibration_run
    else:
        calibration_run, error_return = get_calibration_run(
            calibration_run_id,
            request.user,
            run_status=[StatusEnum.RUNNING, StatusEnum.SUBMITTED, StatusEnum.DONE, StatusEnum.FAILED, StatusEnum.CANCELLED, StatusEnum.SERVER_ERROR]
        )
        if error_return:
            return error_return
        validation_run = None

    log_path = None
    match log_category:
        case LogCategory.CALIBRATION:
            log_path = get_calibration_log(calibration_run, log_name)
        case LogCategory.VALIDATION:
            if validation_run:
                log_path = get_validation_log(validation_run, log_name)
            else:
                raise CerfException(f"Log category '{log_category.value}' not applicable for validation run")
        case LogCategory.FORECAST:
            if forecast_run:
                log_path = get_forecast_log(forecast_run, log_name)
            else:
                raise CerfException(f"Log category '{log_category.value}' not applicable for forecast run")
        case LogCategory.COLD_START:
            if forecast_run and cold_start_run:
                log_path = get_cold_start_log(cold_start_run, log_name)
            else:
                raise CerfException(f"Log category '{log_category.value}' not applicable for cold start run")
        case LogCategory.VERIFICATION:
            if verification_run:
                log_path = get_verification_log(verification_run, log_name)
            else:
                raise CerfException(f"Log category '{log_category.value}' not applicable for verification run")
        case LogCategory.GLOBAL:
            if validation_run:
                log_path = get_global_log(validation_run, log_name)
            else:
                log_path = get_global_log(calibration_run, log_name)

    # Check if the log file exists
    if log_path and not os.path.exists(log_path):
        raise CerfException(f"Log file not found: {log_path}")

    # Get the file size in bytes
    file_size = os.path.getsize(log_path)

    # Count the total number of lines in the file for pagination metadata
    with open(log_path, 'r') as f:
        total_lines = sum(1 for _ in f)

    # Read the requested lines from the log file with null replacement
    with open(log_path, 'r') as file:
        all_lines = [line.replace('\x00', ' ') for line in file]

    if start == -1:
        # Just get the last 'limit' lines
        paginated_lines = all_lines[-limit:]
    else:
        paginated_lines = all_lines[start:start + limit]

    pagination_metadata = {
        'start': start,
        'limit': limit,
        'count': total_lines
    }

    response = {
        'message': f"{log_category.value.capitalize()} {log_name.value} log file retrieved",
        'log_data': paginated_lines,
        'log_path': log_path,
        'byte_offset': file_size,
        'pagination_metadata': pagination_metadata
    }
    match log_category:
        case LogCategory.VALIDATION:
            response['status'] = validation_run.status.name
        case LogCategory.FORECAST:
            response['status'] = forecast_run.status.name
        case LogCategory.COLD_START:
            response['status'] = forecast_run.cold_start_run.status.name
        case LogCategory.VERIFICATION:
            response['status'] = verification_run.status.name
        case _:
            response['status'] = calibration_run.status.name

    response_validator, error_response = validate_response(GetLogsResponseSerializer, response, fields_to_truncate=['log_data'], max_length=10)
    if error_response:
        return error_response

    logger.debug(
        f'Returning to {get_user_email(request)} from {get_caller_name()}(){get_elapsed_str(request)} - '
        f'{json.dumps(truncate_large_fields(response_validator.data, fields_to_truncate=["log_data"], max_length=10))}'
    )
    return Response(response_validator.data)


@extend_schema(
    request=GetLogStatusRequestSerializer,
    responses={
        200: GetLogStatusResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Retrieve a specific log file with pagination support"
)
@api_view(['GET', 'POST'])
@handle_exceptions
def get_log_status(request: Request) -> Response:
    """
    Checks the status a specific log file to see if it has been updated since it was last requested.

    - Uses byte_offset to compare the size of the last data set retrieved to what is currently in the file/cache.

    :param request: The HTTP request object containing run and log information.
    :return: JSON response with log file content or error details.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {data}')

    validator, error_return = validate_request(GetLogStatusRequestSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    validation_run_id = validator.get('validation_run_id')
    forecast_run_id = validator.get('forecast_run_id')
    verification_run_id = validator.get('verification_run_id')
    log_path = validator.get('log_path')
    byte_offset = validator.get('byte_offset')

    validation_run = None
    forecast_run = None
    verification_run = None

    if validation_run_id:
        validation_run, error_return = get_validation_run(
            validation_run_id,
            request.user,
            run_status=[StatusEnum.RUNNING, StatusEnum.SUBMITTED, StatusEnum.DONE, StatusEnum.FAILED, StatusEnum.CANCELLED, StatusEnum.SERVER_ERROR]
        )
        if error_return:
            return error_return
        calibration_run = validation_run.calibration_run
    elif forecast_run_id:
        forecast_run, error_return = get_forecast_run(
            forecast_run_id,
            request.user,
            run_status=[StatusEnum.SAVED, StatusEnum.RUNNING, StatusEnum.SUBMITTED, StatusEnum.DONE, StatusEnum.FAILED, StatusEnum.CANCELLED,
                        StatusEnum.SERVER_ERROR]
        )
        if error_return:
            return error_return
        calibration_run = forecast_run.calibration_run
    elif verification_run_id:
        verification_run, error_return = get_verification_run(
            verification_run_id,
            request.user,
            run_status=[StatusEnum.RUNNING, StatusEnum.SUBMITTED, StatusEnum.DONE, StatusEnum.FAILED, StatusEnum.CANCELLED, StatusEnum.SERVER_ERROR]
        )
        if error_return:
            return error_return
        calibration_run = verification_run.forecast_run.calibration_run
    else:
        calibration_run, error_return = get_calibration_run(
            calibration_run_id,
            request.user,
            run_status=[StatusEnum.RUNNING, StatusEnum.SUBMITTED, StatusEnum.DONE, StatusEnum.FAILED, StatusEnum.CANCELLED, StatusEnum.SERVER_ERROR]
        )
        if error_return:
            return error_return

    # Check if the log file exists
    # TO DO: Get this from the cache if it's already been cached
    if not os.path.exists(log_path):
        raise CerfException(f"Log file not found: {log_path}")

    # Get the file size in bytes
    file_size = os.path.getsize(log_path)

    response = {
        'message': f"log file {log_path} has " + ("changed" if file_size != byte_offset else "not changed"),
        'file_updated': True if file_size != byte_offset else False
    }
    if validation_run_id:
        response['status'] = validation_run.status.name
    elif forecast_run_id:
        response['status'] = forecast_run.status.name
    elif verification_run_id:
        response['status'] = verification_run.status.name
    else:
        response['status'] = calibration_run.status.name

    response_validator, error_response = validate_response(GetLogStatusResponseSerializer, response)
    if error_response:
        return error_response

    logger.debug(
        f'Returning to {get_user_email(request)} from {get_caller_name()}(){get_elapsed_str(request)} - {json.dumps(response_validator.data)}')
    return Response(response_validator.data)


def get_calibration_log(calibration_run: CalibrationRun, log_name: LogName) -> str:
    """
    Retrieves the appropriate log file for a given calibration run.

    - Determines the log file based on the specified log name.
    - Supports logs like `ngen.stdout` and `ngen-cal.stdout`.

    :param calibration_run: The CalibrationRun object for which the log is retrieved.
    :param log_name: The LogName enum specifying the log type.
    :return: The path to the log file.
    """
    if log_name == LogName.NGEN_STDOUT:
        return find_ngen_stdout_log(calibration_run)
    elif log_name == LogName.NGEN_CAL_STDOUT:
        return get_calibration_stdout_file(calibration_run)

    raise CerfException(f'Invalid log name: {log_name}')


def get_validation_log(validation_run: ValidationRun, log_name: LogName) -> str:
    """
    Fetches the appropriate log file for a specific validation run.

    - Handles various validation types (best, control, iteration).
    - Supports logs like `ngen.stdout` and `ngen-cal.stdout`.

    :param validation_run: The ValidationRun object for which the log is retrieved.
    :param log_name: The LogName enum specifying the log type.
    :return: The path to the log file.
    """
    validation_type = validation_run.validation_type

    if validation_type in {ValidationType.VALID_BEST.value, ValidationType.VALID_CONTROL.value}:
        if log_name == LogName.NGEN_CAL_STDOUT:
            return (
                get_validation_best_stdout_file(validation_run.calibration_run)
                if validation_type == ValidationType.VALID_BEST.value
                else get_validation_control_stdout_file(validation_run.calibration_run)
            )

    elif validation_type == ValidationType.VALID_ITERATION.value:
        if log_name == LogName.NGEN_CAL_STDOUT:
            return get_validation_iteration_stdout_file(
                validation_run.calibration_run,
                validation_run.worker_name,
                validation_run.iteration_num
            )

    if log_name == LogName.NGEN_STDOUT:
        return find_ngen_stdout_log(validation_run)

    raise CerfException(f'Invalid log_name: {log_name}')


def get_global_log(run: CalibrationRun | ValidationRun, log_name: LogName) -> str:
    """
    Retrieves the global log file, if applicable.

    - Only supports `ngen` logs currently.

    :param run: The CalibrationRun or ValidationRun object.
    :param log_name: The LogName enum specifying the log type.
    :return: The path to the global log file.
    """
    if log_name == LogName.NGEN:
        return get_ngen_log_path(run if isinstance(run, CalibrationRun) else run.calibration_run)

    raise CerfException(f'Invalid log name: {log_name}')


def find_ngen_stdout_log(run: CalibrationRun | ValidationRun) -> str | None:
    """
    Searches for the `ngen.stdout` log file in worker directories of a given run.

    - Iterates over worker directories using `process_worker_dirs`.
    - Returns the path to the log file if found.

    :param run: The CalibrationRun or ValidationRun object.
    :return: The path of the `ngen.stdout` log file, or None if not found.
    """
    ngen_log_path = None

    # Custom function to check worker directories for the ngen log file
    def check_worker(worker_dir: str, _run: CalibrationRun | ValidationRun):
        nonlocal ngen_log_path
        potential_log_path = os.path.join(worker_dir, get_ngen_stdout_log_filename())

        # Check if ngen stdout file exists in the current worker directory
        if potential_log_path and os.path.isfile(potential_log_path):
            ngen_log_path = potential_log_path

    # Call process_worker_dirs to iterate through the worker directories
    process_worker_dirs(run, check_worker)

    if not ngen_log_path:
        raise CerfException('Could not find ngen log in worker directory')

    return ngen_log_path


def get_zip_cache_key(calibration_run_id: int) -> str:
    """
    Returns the standardized cache key used to track zip job status for a given calibration run.

    - All zip-related endpoints use this key to read/write shared status in the Django cache.
    - The cache value is a dict with fields such as: status, path, started_at, download_name.

    :param calibration_run_id: CalibrationRun ID.
    :return: Cache key string used for this run's zip status.
    """
    return f'zip_status_{calibration_run_id}'


def get_zip_download_token_cache_key(token: str) -> str:
    return f'zip_download_token_{token}'


@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: GetZipDownloadUrlResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        ),
    },
    description="Return a short-lived download URL for a prepared ZIP (the download itself does not require Authorization)."
)
@api_view(["GET", "POST"])
@handle_exceptions
def get_calibration_zip_download_url(request: Request) -> Response:
    data = request.data if request.method == "POST" else request.query_params.dict()
    logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {data}')

    validator, error_response = validate_request(CalibrationRunSerializer, data)
    if error_response:
        return error_response

    calibration_run_id = validator.get("calibration_run_id")
    zip_cache_key = get_zip_cache_key(calibration_run_id)

    cleanup_expired_zips()

    run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=downloadable_statuses)
    if error_return:
        return error_return

    zip_status = cache.get(zip_cache_key)
    if not zip_status:
        return ResponseError(f"Zip job not found for Calibration Job {calibration_run_id}", http_status=status.HTTP_404_NOT_FOUND)

    if zip_status.get("status") != "done":
        return ResponseError(f"Zip file for Calibration Job {calibration_run_id} is not ready yet")

    zip_path = zip_status.get("path")
    if not zip_path or not os.path.exists(zip_path):
        return ResponseError(f"Zip file is missing for Calibration Job {calibration_run_id}")

    download_name = zip_status.get("download_name") or f"calibration_{calibration_run_id}.zip"

    # The UI never calls the download endpoint directly.
    # It calls this endpoint first to get a manufactured, short-lived URL containing a one-time token.
    token = mint_one_time_download_token(
        payload={
            "user_id": request.user.id,
            "zip_path": zip_path,
            "download_name": download_name,
            "calibration_run_id": calibration_run_id,
        },
        ttl_seconds=settings.ZIP_DOWNLOAD_URL_TTL_SECONDS,
    )

    # Build a URL relative to your API prefix (works behind nginx /api/)
    # If you mount Django under /api/, the UI can just use the returned string.
    download_url = reverse("downloadCalibrationZipToken") + f"?token={token}"

    response = {
        "calibration_run_id": calibration_run_id,
        "download_url": download_url,
        "expires_in_seconds": settings.ZIP_DOWNLOAD_URL_TTL_SECONDS,
    }

    response_validator, error_response = validate_response(GetZipDownloadUrlResponseSerializer, response)
    if error_response:
        return error_response

    return Response(response_validator.data)


@extend_schema(
    responses={
        200: OpenApiResponse(
            description="ZIP file stream (token-based download)"
        ),
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Missing token"
        ),
        401: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Invalid or expired token"
        ),
        404: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Zip file not found"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        ),
    },
    description=(
            "Token-based ZIP download (short-lived, single-use).\n\n"
            "- Does NOT require Authorization header\n"
            "- Streams ZIP file as an attachment\n"
            "- Token is invalidated after first use\n"
            "- Token expires after a short TTL\n"
            "- Intended to be called using the URL returned by get_calibration_zip_download_url"
    )
)
@api_view(["GET"])
@handle_exceptions
@permission_classes([AllowAny])
def download_calibration_zip_token(request: Request) -> FileResponse | Response:
    """
    INTERNAL DOWNLOAD ENDPOINT — NOT CALLED DIRECTLY BY THE UI.

    The UI must first call `get_calibration_zip_download_url`, which:
    - Validates the user and job state
    - Mints a short-lived, single-use token
    - Returns a manufactured download URL containing that token

    The browser then navigates to that returned URL, which resolves to this
    endpoint. This endpoint:
    - Does NOT require an Authorization header
    - Trusts the short-lived token + cache TTL + single-use delete for access control
    - Streams the ZIP file directly to the client

    Direct calls to this endpoint without a token are rejected.

    """
    token = request.query_params.get("token")
    if not token:
        return ResponseError("Missing token", http_status=status.HTTP_400_BAD_REQUEST)

    token_cache_key = get_zip_download_token_cache_key(token)
    token_data = cache.get(token_cache_key)
    if not token_data:
        return ResponseError("Invalid or expired token", http_status=status.HTTP_401_UNAUTHORIZED)

    # Make sure token remains valid.  Chrome may retry/resume large downloads
    cache.touch(token_cache_key, timeout=settings.ZIP_DOWNLOAD_URL_TTL_SECONDS)

    # token_data was written by get_calibration_zip_download_url()
    # It contains:
    #   - user_id            (for optional same-user enforcement)
    #   - zip_path          (absolute path to the prepared ZIP file)
    #   - download_name    (canonical filename presented to the client)
    #   - calibration_run_id (for logging and user-facing error messages)
    #
    # This endpoint only *consumes* that cached record. It does not
    # look up the run or ZIP status in the DB or zip_status cache.
    calibration_run_id = token_data.get("calibration_run_id")

    zip_path = token_data.get("zip_path")
    download_name = token_data.get("download_name") or (
        f"calibration_{calibration_run_id}.zip" if calibration_run_id else "download.zip"
    )

    cleanup_expired_zips()

    if not zip_path or not os.path.exists(zip_path):
        return ResponseError(
            f"Zip file is missing for Calibration Job {calibration_run_id}" if calibration_run_id else "Zip file is missing",
            http_status=status.HTTP_404_NOT_FOUND
        )

    # Mark as "in use" by bumping mtime. Cleanup uses mtime, so this postpones TTL deletion.
    try:
        os.utime(zip_path, None)
    except Exception:
        logger.debug(f"Failed to utime(zip_path): {zip_path}", exc_info=True)

    zip_size = os.path.getsize(zip_path)
    if calibration_run_id:
        logger.info(
            f"Serving Calibration zip for Job {calibration_run_id} — "
            f"size: {zip_size / 1024 / 1024:.2f} MB"
        )
    else:
        logger.info(f"Serving tokenized zip — size: {zip_size / 1024 / 1024:.2f} MB")

    zip_file = None
    try:
        zip_file = open(zip_path, "rb")
        response = FileResponse(zip_file, content_type="application/zip")

        # Add Content-Length so the browser knows exactly how many bytes to expect.
        # This can reduce Chrome "restart" behavior on large downloads.
        response["Content-Length"] = str(zip_size)

        apply_zip_download_headers(response, download_name, origin=request.headers.get("Origin"))

        logger.debug(
            f"Returning tokenized zip"
            f"{f' for Calibration Job {calibration_run_id}' if calibration_run_id else ''} "
            f"from {get_caller_name()}(){get_elapsed_str(request)}"
        )
        return response

    except Exception as e:
        if zip_file is not None:
            try:
                zip_file.close()
            except Exception:
                logger.debug("Failed to close file handle", exc_info=True)

        logger.exception(
            f"Failed to serve zip file"
            f"{f' for Calibration Job {calibration_run_id}' if calibration_run_id else ''}: {e}"
        )
        return ResponseError(
            f"Failed to read zip file for Calibration Job {calibration_run_id}" if calibration_run_id else "Failed to read zip file"
        )


def mint_one_time_download_token(payload: dict, ttl_seconds: int) -> str:
    token = secrets.token_urlsafe(32)
    cache.set(get_zip_download_token_cache_key(token), payload, timeout=ttl_seconds)
    return token


downloadable_statuses = [s for s in StatusEnum if s not in {StatusEnum.READY, StatusEnum.SAVED, StatusEnum.SUBMITTED, StatusEnum.RUNNING}]


@api_view(['GET', 'POST'])
@handle_exceptions
def get_calibration_job_zip(request: Request) -> FileResponse | Response:
    """
    Synchronous ZIP download endpoint (primarily for the CLI).

    - Builds a ZIP of the calibration run's job_data_dir on disk (not in memory).
    - Writes to a temporary file first and then atomically renames it into place.
    - Streams the completed ZIP back as a FileResponse attachment.

    Notes:
    - This endpoint does not use the background cache-based zip workflow.
    - The created ZIP artifact is left on disk and later removed by cleanup_expired_zips().

    :param request: HTTP request containing calibration_run_id (POST body or query params).
    :return: FileResponse streaming the ZIP, or a formatted error Response.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    calibration_run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=downloadable_statuses)
    if error_return:
        return error_return

    cleanup_expired_zips()  # opportunistically delete old ZIPs (lazy TTL cleanup)

    job_data_dir = calibration_run.job_data_dir

    # Canonical download name (no timestamp)
    zip_base_name = f"{os.path.basename(job_data_dir)}_{calibration_run.user_formulation_name}"
    download_name = f"{zip_base_name}.zip"

    # Unique on-disk name (avoid collisions)
    zip_filename = f"{zip_base_name}_{int(time.time())}.zip"
    zip_path = os.path.join(settings.ZIP_DIR, zip_filename)

    # Write to a temp file first, then atomically rename into place.
    tmp_path = f"{zip_path}.tmp"

    # Build zip to temp path first, then atomically place the final file
    try:
        with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for root, _, files in os.walk(job_data_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arc_name = os.path.relpath(file_path, job_data_dir)
                    try:
                        zip_file.write(file_path, arc_name)
                    except FileNotFoundError:
                        logger.warning(f"File not found during zipping: {arc_name}")

        os.replace(tmp_path, zip_path)
        tmp_path = None

    finally:
        # Best-effort cleanup of temp zip if something failed mid-build
        if tmp_path:
            try:
                os.remove(tmp_path)
            except FileNotFoundError:
                pass
            except Exception:
                logger.exception(f"Failed deleting temp zip: {tmp_path}")

    # Stream the finished zip back
    zip_file = None
    try:
        zip_file = open(zip_path, "rb")
        response = FileResponse(zip_file, content_type="application/zip")

        zip_size = os.path.getsize(zip_path)
        response["Content-Length"] = str(zip_size)

        apply_zip_download_headers(response, download_name)

        return response

    except Exception as e:
        if zip_file is not None:
            try:
                zip_file.close()
            except Exception:
                logger.debug("Failed to close file handle", exc_info=True)
        logger.exception(f"Failed to serve zip file for Calibration Job {calibration_run_id}: {e}")
        return ResponseError(f"Failed to read zip file for Calibration Job {calibration_run_id}")


@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: GenericMessageWithIdResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Starts a background process to zip calibration job files. Use `get_zip_status` to track progress."
)
@api_view(['GET', 'POST'])
@handle_exceptions
def start_zip_for_calibration_job(request: Request) -> Response:
    """
    Starts a background job to create a ZIP for the calibration run's job_data_dir.

    - Sets a shared cache entry (status=pending) keyed by get_zip_cache_key(calibration_run_id).
    - Runs the zip build in a daemon thread and updates cache to status=done (or status=error).
    - The produced ZIP file is written to settings.ZIP_DIR and is later removed by cleanup_expired_zips().

    Cache fields written:
    - status: "pending" | "done" | "error"
    - path: absolute path to the built ZIP (done only)
    - started_at: ISO timestamp when the job began
    - download_name: canonical filename presented to the client (done only)

    :param request: HTTP request containing calibration_run_id (POST body or query params).
    :return: JSON message with calibration_run_id, or a formatted error Response.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    cache_key = get_zip_cache_key(calibration_run_id)

    cleanup_expired_zips()  # opportunistically delete old ZIPs (lazy TTL cleanup)

    run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=downloadable_statuses)
    if error_return:
        return error_return

    zip_status = cache.get(cache_key)
    if zip_status and zip_status.get('status') == 'pending':
        logger.info(f"Zip job already in progress for Calibration Job {calibration_run_id}")
        return Response({
            "message": "Zip job already in progress",
            "status": zip_status["status"],
            "calibration_run_id": calibration_run_id
        })

    # Mark status as pending (shared across workers)
    started_at = datetime.now().isoformat()
    cache.set(cache_key, {
        "status": "pending",
        "path": None,
        "started_at": started_at,
        "download_name": None,  # canonical download name (filled in when done)
    }, timeout=None)  # no timeout while building; "done" status gets a TTL

    # Launch zip process in background
    def zip_job():
        start_time = datetime.now()
        tmp_path = None

        try:
            job_data_dir = run.job_data_dir

            # Canonical download name (NO timestamp)
            zip_base_name = f"{os.path.basename(job_data_dir)}_{run.user_formulation_name}"
            download_name = f"{zip_base_name}.zip"

            # Unique on-disk filename includes timestamp to avoid collisions
            zip_filename = f"{zip_base_name}_{int(time.time())}.zip"
            zip_path = os.path.join(settings.ZIP_DIR, zip_filename)

            # Write to a temp file first, then atomically rename into place.
            tmp_path = f"{zip_path}.tmp"

            with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for root, _, files in os.walk(job_data_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arc_name = os.path.relpath(file_path, job_data_dir)
                        try:
                            zip_file.write(file_path, arc_name)
                        except FileNotFoundError:
                            logger.warning(f"File not found during zipping: {arc_name}")

            # Atomic replace: downloader will never see a partially-written zip.
            os.replace(tmp_path, zip_path)
            tmp_path = None  # prevent cleanup from deleting the final zip if names ever change

            # Mark the zip job as complete
            cache.set(cache_key, {
                "status": "done",
                "path": zip_path,
                "started_at": started_at,
                "download_name": download_name,
            }, timeout=3600)  # cache entry TTL; file TTL is controlled separately by ZIP_TTL_SECONDS

            duration = datetime.now() - start_time
            zip_size = os.path.getsize(zip_path)
            logger.info(
                f"Zip job completed for Calibration Job {run.id} in {duration.total_seconds():.2f} seconds "
                f"— size: {zip_size / 1024 / 1024:.2f} MB)"
            )

        except Exception as e:
            cache.set(cache_key, {
                "status": "error",
                "path": None,
                "started_at": started_at,
                "download_name": None,
            }, timeout=3600)  # Once it's done, don't leave it around forever
            duration = datetime.now() - start_time
            logger.exception(f"Failed to zip Calibration Job {run.id} after {duration.total_seconds():.2f} seconds: {e}")

        finally:
            # Best-effort cleanup of any temp file left behind
            if tmp_path:
                try:
                    os.remove(tmp_path)
                except FileNotFoundError:
                    pass
                except Exception:
                    logger.exception(f"Failed deleting temp zip: {tmp_path}")

    threading.Thread(target=zip_job, daemon=True).start()

    response = {"message": "Zip job started", "calibration_run_id": calibration_run_id}

    response_validator, error_response = validate_response(GenericMessageWithIdResponseSerializer, response)
    if error_response:
        return error_response

    logger.debug(
        f'Returning to {get_user_email(request)} from {get_caller_name()}(){get_elapsed_str(request)} - '
        f'{json.dumps(response_validator.data)}'
    )
    return Response(response_validator.data)


@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: GetZipStatusSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Polling endpoint that returns the current status of a calibration zip job"
)
@api_view(['GET', 'POST'])
@handle_exceptions
def get_zip_status(request: Request) -> Response:
    """
    Returns the current status of a background zip job started by start_zip_for_calibration_job().

    - Reads the shared cache entry keyed by get_zip_cache_key(calibration_run_id).
    - Does not start work; it only reports what is currently in cache.
    - Intended for polling until zip_status becomes "done" (or "error").

    Response fields:
    - calibration_run_id
    - zip_status: "pending" | "done" | "error"
    - path: ZIP path when done (used by download_calibration_zip)
    - started_at: ISO timestamp when the job began

    :param request: HTTP request containing calibration_run_id (POST body or query params).
    :return: JSON response with zip status information, or a formatted error Response.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {data}')

    validator, error_response = validate_request(CalibrationRunSerializer, data)
    if error_response:
        return error_response

    calibration_run_id = validator.get("calibration_run_id")
    cache_key = get_zip_cache_key(calibration_run_id)

    cleanup_expired_zips()  # opportunistically delete old ZIPs (lazy TTL cleanup)

    zip_status = cache.get(cache_key)
    if not zip_status:
        return ResponseError(f"No zip job found for Calibration Job {calibration_run_id}")

    response = {
        "calibration_run_id": calibration_run_id,
        "zip_status": zip_status.get("status"),
        "path": zip_status.get("path"),
        "started_at": zip_status.get("started_at"),
    }

    response_validator, error_response = validate_response(
        GetZipStatusSerializer,
        response
    )
    if error_response:
        return error_response

    logger.debug(
        f'Returning to {get_user_email(request)} from {get_caller_name()}'
        f'{get_elapsed_str(request)} - {json.dumps(response_validator.data)}'
    )

    return Response(response_validator.data)


#
# @extend_schema(
#     request=CalibrationRunSerializer,
#     responses={
#         200: OpenApiResponse(description="ZIP file ready for download"),
#         400: OpenApiResponse(
#             response=ErrorResponseSerializer,
#             description="Validation error or parsing error"
#         ),
#         500: OpenApiResponse(
#             response=ErrorResponseSerializer,
#             description="Internal server error"
#         )
#     },
#     description="Returns the zipped calibration job if ready."
# )
# @api_view(['GET', 'POST'])
# @handle_exceptions
# def download_calibration_zip(request: Request) -> FileResponse | Response:
#     """
#     Downloads the ZIP produced by start_zip_for_calibration_job() once it is ready.
#
#     - Validates that the cached zip status is "done".
#     - Streams the ZIP file at the cached path as a FileResponse attachment.
#     - Does not delete the ZIP immediately after returning (cleanup is handled separately by cleanup_expired_zips()).
#     - Touches the ZIP mtime via os.utime() to extend its on-disk TTL window.
#
#     :param request: HTTP request containing calibration_run_id (POST body or query params).
#     :return: FileResponse streaming the ZIP, or a formatted error Response.
#     """
#     data = request.data if request.method == 'POST' else request.query_params.dict()
#     logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {data}')
#
#     validator, error_response = validate_request(CalibrationRunSerializer, data)
#     if error_response:
#         return error_response
#
#     calibration_run_id = validator.get("calibration_run_id")
#     cache_key = get_zip_cache_key(calibration_run_id)
#
#     cleanup_expired_zips()  # opportunistically delete old ZIPs (lazy TTL cleanup)
#
#     zip_status = cache.get(cache_key)
#
#     if not zip_status:
#         return ResponseError(f"Zip job not found for Calibration Job {calibration_run_id}", http_status=status.HTTP_404_NOT_FOUND)
#
#     if zip_status.get("status") != "done":
#         return ResponseError(f"Zip file for Calibration Job {calibration_run_id} is not ready yet")
#
#     zip_path = zip_status.get("path")
#     if not zip_path or not os.path.exists(zip_path):
#         return ResponseError(f"Zip file is missing for Calibration Job {calibration_run_id}")
#
#     # Mark as "in use" by bumping mtime. Cleanup uses mtime, so this postpones TTL deletion.
#     try:
#         os.utime(zip_path, None)
#     except Exception:
#         # Not fatal; cleanup is best-effort.
#         logger.debug(f"Failed to utime(zip_path): {zip_path}", exc_info=True)
#
#     zip_size = os.path.getsize(zip_path)
#     logger.info(f"Serving zip file for Calibration Job {calibration_run_id} — size: {zip_size / 1024 / 1024:.2f} MB")
#
#     zip_file = None
#     try:
#         zip_file = open(zip_path, 'rb')
#         response = FileResponse(zip_file, content_type='application/zip')
#
#         origin = request.headers.get("Origin")
#
#         # Friendly filename for the browser (canonical), not the unique on-disk name
#         download_name = zip_status.get("download_name") or f"calibration_{calibration_run_id}.zip"
#         apply_zip_download_headers(response, download_name, origin=origin)
#         logger.debug(
#             f'Returning zip for Calibration Job {calibration_run_id} to {get_user_email(request)} '
#             f'from {get_caller_name()}(){get_elapsed_str(request)}'
#         )
#         return response
#
#     except Exception as e:
#         # If we opened the file but didn't hand it off successfully, close it here.
#         if zip_file is not None:
#             try:
#                 zip_file.close()
#             except Exception:
#                 logger.debug("Failed to close file handle", exc_info=True)
#         logger.exception(f"Failed to serve zip file for Calibration Job {calibration_run_id}: {e}")
#         return ResponseError(f"Failed to read zip file for Calibration Job {calibration_run_id}")


_CLEANUP_LAST_RUN_KEY = "zip_cleanup_last_run"
_CLEANUP_LOCK_KEY = "zip_cleanup_lock"


def cleanup_expired_zips() -> None:
    """
    Opportunistically deletes expired ZIP artifacts created by zip endpoints.

    Why this exists:
    - ZIP files are not deleted immediately after returning FileResponse, because the server can finish
      "sending" while the client is still receiving bytes (and reverse proxies may buffer).
      Deleting too early can break large downloads.
    - Instead, ZIPs live on disk for settings.ZIP_TTL_SECONDS and are deleted lazily when any zip-related
      endpoint runs.

    Behavior:
    - Scans settings.ZIP_DIR for:
      - "*.zip" files older than (now - settings.ZIP_TTL_SECONDS)
      - "*.tmp" files older than (now - settings.ZIP_TTL_SECONDS) from interrupted builds
    - Throttled to run at most once every 5 minutes across all workers (shared cache timestamp).
    - Uses a shared cache lock so only one worker performs deletions at a time.

    :return: None
    """
    logger.debug(f"ZIP cleanup sweep: dir={settings.ZIP_DIR}, ttl={settings.ZIP_TTL_SECONDS}s")

    now = time.time()

    # Run at most every 5 minutes across all workers.
    last = cache.get(_CLEANUP_LAST_RUN_KEY)
    if last and (now - float(last)) < 300:
        return

    # Acquire a short-lived lock across workers to avoid multiple processes deleting simultaneously.
    if not cache.add(_CLEANUP_LOCK_KEY, "1", timeout=60):
        return

    try:
        # Record that cleanup ran (even if nothing is deleted) to prevent repeated scans.
        cache.set(_CLEANUP_LAST_RUN_KEY, now, timeout=24 * 3600)

        cutoff = now - settings.ZIP_TTL_SECONDS

        # If ZIP_DIR doesn't exist (misconfig or first-run), just no-op.
        if not os.path.isdir(settings.ZIP_DIR):
            return

        deleted_zip = 0
        deleted_tmp = 0

        for name in os.listdir(settings.ZIP_DIR):
            # Only manage artifacts created by this feature.
            is_zip = name.endswith(".zip")
            is_tmp = name.endswith(".tmp")
            if not (is_zip or is_tmp):
                continue

            path = os.path.join(settings.ZIP_DIR, name)

            # File might disappear between listdir() and stat() if another worker deletes it.
            try:
                st = os.stat(path)
            except FileNotFoundError:
                continue

            # Delete files older than the TTL.
            if st.st_mtime < cutoff:
                try:
                    os.remove(path)
                    if is_zip:
                        deleted_zip += 1
                    else:
                        deleted_tmp += 1
                except FileNotFoundError:
                    # Another worker/process deleted it after our stat().
                    pass
                except Exception:
                    logger.exception(f"Failed deleting expired artifact: {path}")

        if deleted_zip or deleted_tmp:
            logger.info(
                f"Lazy cleanup deleted {deleted_zip} expired zip(s) and {deleted_tmp} expired tmp file(s) from {settings.ZIP_DIR}"
            )

    finally:
        # Always release the lock.
        cache.delete(_CLEANUP_LOCK_KEY)


def apply_zip_download_headers(response: FileResponse, download_name: str, origin: str | None = None) -> FileResponse:
    """
    Apply consistent headers for streaming a ZIP download.

    - Forces attachment download name.
    - Prevents any caching or storage by browsers and proxies.
    - Disables Nginx buffering to allow direct streaming of large files.
    - Prevents middleware/proxies from applying gzip or other content encodings.
    - Optionally sets CORS Access-Control-Allow-Origin for allowed origins.

    :param response: FileResponse already initialized with the ZIP file handle.
    :param download_name: Filename presented to the client.
    :param origin: Request Origin header value (optional).
    :return: The same response object (mutated).
    """
    if origin and origin in settings.CORS_ALLOWED_ORIGINS:
        response["Access-Control-Allow-Origin"] = origin

    response["Content-Disposition"] = f'attachment; filename="{download_name}"'

    # Do not allow browsers or proxies to store this response.
    response["Cache-Control"] = "no-store"
    response["Pragma"] = "no-cache"  # for older proxies

    # Tell Nginx NOT to buffer the file before sending it downstream.
    # This avoids Nginx holding a 1.5 GB file in memory/disk buffers, which can trigger timeouts or stall the transfer.
    response["X-Accel-Buffering"] = "no"
    response["Content-Encoding"] = "identity"  # Prevent response from being gzipped (especially ZIP files) by middleware

    return response
