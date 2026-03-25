import json
import logging
import math
import os
from collections import defaultdict
from numbers import Real
from pathlib import Path

from django.db.models import F, QuerySet
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from calibration.enums import StatusEnum, ValidationMetricPeriod, ValidationType, LogCategory
from calibration.models import Iteration, NWMRetrospectiveMetrics, CalibrationRun, ValidationRun, IterationParameter, IterationMetric
from calibration.util.calibration_validators import CalibrationRunSerializer, CalibrationOrValidationOrColdStartOrForecastOrVerificationRunSerializer, \
    ErrorResponseSerializer, GetCalibrationDataByIterationResponseSerializer, GetLogsResponseSerializer, \
    GetLogNamesResponseSerializer, GetLogRequestSerializer, GetLogStatusRequestSerializer, \
    GetLogStatusResponseSerializer
from calibration.util.ngen_locations import get_calibration_stdout_file, get_validation_best_stdout_file, get_validation_control_stdout_file, \
    get_validation_iteration_stdout_file, get_ngen_stdout_log_filename, get_ngen_log_dir, get_forecast_ngen_stdout_file, \
    get_forecast_ngen_log_dir, get_cold_start_ngen_stdout_file, get_cold_start_ngen_log_dir, get_verification_stdout_file
from calibration.views.calibration_run_views import map_path_to_host
from calibration.views.called_from import get_caller_name
from calibration.views.common import get_calibration_run, handle_exceptions, validate_response, validate_request, truncate_large_fields, \
    get_validation_run, CerfException, process_worker_dirs, get_user_email, get_elapsed_str, \
    get_forecast_run, get_verification_run

logger = logging.getLogger(__name__)


def normalize_float(value):
    """
    Normalize numeric values for JSON serialization.

    Behavior:
    - None -> None
    - Any real numeric type (float, int, numpy floats/ints, Decimal):
        - Converted to float
        - If non-finite (NaN, +inf, -inf) -> None
        - Otherwise -> finite float
    - All non-numeric values (str, dict, list, etc.) pass through unchanged

    Rationale:
    - PostgreSQL can store NaN/±Infinity in float columns.
    - JSON cannot represent NaN/±Infinity.
    - This function is applied ONLY at API response construction time,
      not at DB write time, to preserve raw numeric fidelity in storage
      while guaranteeing JSON-safe output.
    """

    # Preserve None as-is
    if value is None:
        return None

    # bool is a subclass of int; don't treat it as numeric here
    if isinstance(value, Real) and not isinstance(value, bool):
        f = float(value)
        return f if math.isfinite(f) else None

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

    for row in nwm_retrospective_data:
        row['metric_value'] = normalize_float(row.get('metric_value'))
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
            'parameter_value': p['tuned_value']
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
            'metric_value': m['metric_value']
        })

    # Construct iteration data with parameters, metrics, and validation reference
    iteration_data = []
    for iteration in iterations:
        validation_run = validation_runs_by_iteration.get(iteration.id)

        raw_params = params_by_iter.get(iteration.id, [])
        raw_metrics = metrics_by_iter.get(iteration.id, [])

        iteration_element = {
            'iteration_num': iteration.iteration_num,
            'iteration_id': iteration.id,
            'worker_name': iteration.worker_name,
            'best_params': iteration.best_params,
            'objective_function_value': normalize_float(iteration.objective_function_value),
            'parameters': [
                {
                    'parameter_name': p['parameter_name'],
                    'parameter_value': normalize_float(p['parameter_value']),
                }
                for p in raw_params
            ],
            'metrics': [
                {
                    'metric_name': m['metric_name'],
                    'metric_display_name': m['metric_display_name'],
                    'metric_value': normalize_float(m['metric_value']),
                }
                for m in raw_metrics
            ],
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


def resolve_log_context(
        *,
        calibration_run_id: int | None,
        validation_run_id: int | None,
        forecast_run_id: int | None,
        verification_run_id: int | None,
        user,
):
    """
    Shared run-resolution logic for log-related endpoints

    Returns:
        (ctx, error_return)

    ctx keys:
        - calibration_run
        - validation_run
        - forecast_run
        - cold_start_run
        - verification_run
    """
    ACTIVE_STATUSES = [
        StatusEnum.RUNNING,
        StatusEnum.SUBMITTED,
        StatusEnum.DONE,
        StatusEnum.FAILED,
        StatusEnum.CANCELLED,
        StatusEnum.SERVER_ERROR,
    ]

    validation_run = None
    forecast_run = None
    cold_start_run = None
    verification_run = None

    if validation_run_id:
        validation_run, error_return = get_validation_run(
            validation_run_id,
            user,
            run_status=ACTIVE_STATUSES,
        )
        if error_return:
            return None, error_return
        calibration_run = validation_run.calibration_run

    elif forecast_run_id:
        forecast_run, error_return = get_forecast_run(
            forecast_run_id,
            user,
            # Allow SAVED in case we are looking for cold start logs
            run_status=[*ACTIVE_STATUSES, StatusEnum.SAVED],
        )
        if error_return:
            return None, error_return
        calibration_run = forecast_run.calibration_run
        cold_start_run = forecast_run.cold_start_run

    elif verification_run_id:
        verification_run, error_return = get_verification_run(
            verification_run_id,
            user,
            run_status=ACTIVE_STATUSES,
        )
        if error_return:
            return None, error_return
        calibration_run = verification_run.forecast_run.calibration_run

    else:
        calibration_run, error_return = get_calibration_run(
            calibration_run_id,
            user,
            run_status=ACTIVE_STATUSES,
        )
        if error_return:
            return None, error_return

    return {
        "calibration_run": calibration_run,
        "validation_run": validation_run,
        "forecast_run": forecast_run,
        "cold_start_run": cold_start_run,
        "verification_run": verification_run,
    }, None


#
# def resolve_log_path(ctx: dict, log_category: LogCategory, log_name: LogName) -> str:
#     """
#     Shared match/case mapping (category, name, ctx) -> filesystem path.
#     """
#     calibration_run = ctx["calibration_run"]
#     validation_run = ctx["validation_run"]
#     forecast_run = ctx["forecast_run"]
#     cold_start_run = ctx["cold_start_run"]
#     verification_run = ctx["verification_run"]
#
#     match log_category:
#         case LogCategory.CALIBRATION:
#             return get_calibration_log(calibration_run, log_name)
#
#         case LogCategory.VALIDATION:
#             if not validation_run:
#                 raise CerfException(f"Log category '{log_category.value}' not applicable for validation run")
#             return get_validation_log(validation_run, log_name)
#
#         case LogCategory.FORECAST:
#             if not forecast_run:
#                 raise CerfException(f"Log category '{log_category.value}' not applicable for forecast run")
#             return get_forecast_log(forecast_run, log_name)
#
#         case LogCategory.COLD_START:
#             if not (forecast_run and cold_start_run):
#                 raise CerfException(f"Log category '{log_category.value}' not applicable for cold start run")
#             return get_cold_start_log(cold_start_run, log_name)
#
#         case LogCategory.VERIFICATION:
#             if not verification_run:
#                 raise CerfException(f"Log category '{log_category.value}' not applicable for verification run")
#             return get_verification_log(verification_run, log_name)
#
#         case LogCategory.GLOBAL:
#             return get_global_log(validation_run or calibration_run, log_name)
#

# def get_status_name_for_log(ctx: dict, log_category: LogCategory) -> str:
#     """
#     Centralizes the 'status' you return.
#
#     Preserves your current behavior:
#       - COLD_START status comes from cold_start_run.status, not forecast_run.status.
#     """
#     calibration_run = ctx["calibration_run"]
#     validation_run = ctx["validation_run"]
#     forecast_run = ctx["forecast_run"]
#     cold_start_run = ctx["cold_start_run"]
#     verification_run = ctx["verification_run"]
#
#     match log_category:
#         case LogCategory.VALIDATION:
#             return (validation_run or calibration_run).status.name
#         case LogCategory.FORECAST:
#             return (forecast_run or calibration_run).status.name
#         case LogCategory.COLD_START:
#             return (cold_start_run or calibration_run).status.name
#         case LogCategory.VERIFICATION:
#             return (verification_run or calibration_run).status.name
#         case _:
#             return calibration_run.status.name


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
    description="Retrieve available log names for a calibration, validation, forecast, or verification run"
)
@api_view(['POST', 'GET'])
@handle_exceptions
def get_log_names(request: Request) -> Response:
    """
    Retrieves a list of available log names for a specific calibration, validation, forecast, or verification run.

    - Handles request validation and user permissions.
    - Returns log files as a list where each entry is a single-key object
      mapping one log category to its list of log files.
    - Within each category, files are sorted by filename only, not full path.

    :param request: The HTTP request object containing one run ID.
    :return: JSON response with log names or error details.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {data}')

    validator, error_return = validate_request(
        CalibrationOrValidationOrColdStartOrForecastOrVerificationRunSerializer,
        data
    )
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    validation_run_id = validator.get('validation_run_id')
    forecast_run_id = validator.get('forecast_run_id')
    verification_run_id = validator.get('verification_run_id')

    logs_by_category, error_return = get_allowed_logs_for_request(
        calibration_run_id=calibration_run_id,
        validation_run_id=validation_run_id,
        forecast_run_id=forecast_run_id,
        verification_run_id=verification_run_id,
        user=request.user,
    )
    if error_return:
        return error_return

    category_order = {
        'Calibration': 0,
        'Validation': 1,
        'Cold Start': 2,
        'Forecast': 3,
    }

    sorted_categories = sorted(
        logs_by_category.items(),
        key=lambda item: (category_order.get(item[0], 999), item[0].lower())
    )

    response = {
        'log_names': [
            {
                log_category: sorted(
                    log_paths,
                    key=lambda path: os.path.basename(path).lower()
                )
            }
            for log_category, log_paths in sorted_categories
            if log_paths
        ]
    }

    response_validator, error_response = validate_response(GetLogNamesResponseSerializer, response)
    if error_response:
        return error_response

    logger.debug(
        f'Returning to {get_user_email(request)} from {get_caller_name()}(){get_elapsed_str(request)} - '
        f'{json.dumps(response_validator.data)}'
    )
    return Response(response_validator.data)


def get_allowed_logs_for_request(
        *,
        calibration_run_id: int | None,
        validation_run_id: int | None,
        forecast_run_id: int | None,
        verification_run_id: int | None,
        user,
) -> tuple[dict[str, list[str]] | None, Response | None]:
    """
    Builds the set of logs the authenticated user is allowed to access
    for the specified run.

    - Resolves the requested run in user context.
    - Collects the applicable logs for that run.
    - Normalizes all returned paths to canonical absolute paths before returning.

    :return:
        A tuple of (logs, error_return), where logs is a dict keyed by
        log category value and each value is a list of normalized absolute paths.
    """
    ctx, error_return = resolve_log_context(
        calibration_run_id=calibration_run_id,
        validation_run_id=validation_run_id,
        forecast_run_id=forecast_run_id,
        verification_run_id=verification_run_id,
        user=user,
    )
    if error_return:
        return None, error_return

    calibration_run = ctx["calibration_run"]
    validation_run = ctx["validation_run"]
    forecast_run = ctx["forecast_run"]
    cold_start_run = ctx["cold_start_run"]
    verification_run = ctx["verification_run"]

    logs: dict[str, list[str]] = {}

    if validation_run:
        logs[LogCategory.CALIBRATION.value] = get_calibration_logs(calibration_run)

        validation_logs = []
        validation_type = validation_run.validation_type

        if validation_type == ValidationType.VALID_CONTROL.value:
            file = get_validation_control_stdout_file(calibration_run)
            if os.path.exists(file):
                validation_logs.append(file)
        elif validation_type == ValidationType.VALID_BEST.value:
            file = get_validation_best_stdout_file(calibration_run)
            if os.path.exists(file):
                validation_logs.append(file)
        else:
            file = get_validation_iteration_stdout_file(
                calibration_run,
                validation_run.worker_name,
                validation_run.iteration_num
            )
            if os.path.exists(file):
                validation_logs.append(file)

        file = find_ngen_stdout_log(validation_run)
        if file and os.path.exists(file):
            validation_logs.append(file)

        logs[LogCategory.VALIDATION.value] = validation_logs

    elif forecast_run:
        forecast_logs = []
        file = get_forecast_ngen_stdout_file(forecast_run)
        if os.path.exists(file):
            forecast_logs.append(file)

        ngen_log_dir = get_forecast_ngen_log_dir(forecast_run)
        forecast_logs.extend([str(p) for p in Path(ngen_log_dir).glob("*.log")])
        logs[LogCategory.FORECAST.value] = forecast_logs

        if cold_start_run:
            cold_start_logs = []
            file = get_cold_start_ngen_stdout_file(cold_start_run)
            if os.path.exists(file):
                cold_start_logs.append(file)

            ngen_log_dir = get_cold_start_ngen_log_dir(cold_start_run)
            cold_start_logs.extend([str(p) for p in Path(ngen_log_dir).glob("*.log")])
            logs[LogCategory.COLD_START.value] = cold_start_logs

    elif verification_run:
        verification_logs = []
        file = get_verification_stdout_file(verification_run)
        if os.path.exists(file):
            verification_logs.append(file)

        logs[LogCategory.VERIFICATION.value] = verification_logs

    else:
        logs[LogCategory.CALIBRATION.value] = get_calibration_logs(calibration_run)

    normalized_logs = {
        category: [normalize_log_path(path) for path in paths]
        for category, paths in logs.items()
    }

    return normalized_logs, None


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
    description="Retrieve a specific allowed log file with pagination support"
)
@api_view(['GET', 'POST'])
@handle_exceptions
def get_log(request: Request) -> Response:
    """
    Retrieves a specific log file for a calibration, validation, forecast, cold start, or verification run.

    - Supports pagination for large log files.
    - Validates that the requested log path is one of the allowed logs
      for the authenticated user and requested run.

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
    log_name = validator.get('log_name')
    start = validator.get('start')
    limit = validator.get('limit')

    logs, error_return = get_allowed_logs_for_request(
        calibration_run_id=calibration_run_id,
        validation_run_id=validation_run_id,
        forecast_run_id=forecast_run_id,
        verification_run_id=verification_run_id,
        user=request.user,
    )
    if error_return:
        return error_return

    requested_log_name = normalize_log_path(log_name)
    allowed_logs = {
        path
        for paths in logs.values()
        for path in paths
    }

    if requested_log_name not in allowed_logs:
        raise CerfException(f"Log file not valid for this run: {log_name}")

    # Check if the log file exists
    if not os.path.exists(requested_log_name):
        raise CerfException(f"Log file not found: {requested_log_name}")

    # Get the file size in bytes
    file_size = os.path.getsize(requested_log_name)

    # Count the total number of lines in the file for pagination metadata
    with open(requested_log_name, 'r') as f:
        total_lines = sum(1 for _ in f)

    # Read the requested lines from the log file with null replacement
    with open(requested_log_name, 'r') as file:
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
        'message': f"Log file {requested_log_name} retrieved",
        'log_data': paginated_lines,
        'log_name': map_path_to_host(requested_log_name),
        'byte_offset': file_size,
        'pagination_metadata': pagination_metadata,
        # 'status': get_status_name_for_log(ctx, log_category),
    }

    response_validator, error_response = validate_response(
        GetLogsResponseSerializer,
        response,
        fields_to_truncate=['log_data'], max_length=10
    )
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
    description="Check whether a specific allowed log file has changed"
)
@api_view(['GET', 'POST'])
@handle_exceptions
def get_log_status(request: Request) -> Response:
    """
    Checks whether a specific log file has been updated since it was last requested.

    - Validates that the requested log path is one of the allowed logs
      for the authenticated user and requested run.
    - Uses byte_offset to compare the previously returned file size
      to the current file size on disk.

    :param request: The HTTP request object containing run and log information.
    :return: JSON response indicating whether the log file has changed.

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
    # log_category = LogCategory(validator.get('log_category'))
    log_name = validator.get('log_name')
    byte_offset = validator.get('byte_offset')

    logs, error_return = get_allowed_logs_for_request(
        calibration_run_id=calibration_run_id,
        validation_run_id=validation_run_id,
        forecast_run_id=forecast_run_id,
        verification_run_id=verification_run_id,
        user=request.user,
    )
    if error_return:
        return error_return

    requested_log_name = normalize_log_path(log_name)
    allowed_logs = {
        path
        for paths in logs.values()
        for path in paths
    }

    if requested_log_name not in allowed_logs:
        raise CerfException(f"Log file not valid for this run: {log_name}")

    # Get the file size in bytes
    file_size = os.path.getsize(requested_log_name) if os.path.exists(requested_log_name) else 0

    response = {
        'message': f"Log file {map_path_to_host(requested_log_name)} has " +
                   ("changed" if file_size != byte_offset else "not changed"),
        'file_updated': (file_size != byte_offset),
        # 'status': get_status_name_for_log(ctx, log_category)
    }

    response_validator, error_response = validate_response(GetLogStatusResponseSerializer, response)
    if error_response:
        return error_response

    logger.debug(
        f'Returning to {get_user_email(request)} from {get_caller_name()}(){get_elapsed_str(request)} - {json.dumps(response_validator.data)}'
    )
    return Response(response_validator.data)


def get_calibration_logs(calibration_run: CalibrationRun) -> list[str]:
    """
    Collects available calibration log files for a calibration run.

    Includes:
    - the calibration stdout log
    - the ngen stdout log, if present
    - any *.log files in the calibration log directory

    :param calibration_run: The calibration run whose logs should be collected.
    :return: A list of log file paths.
    """
    logs = []

    file = get_calibration_stdout_file(calibration_run)
    if os.path.exists(file):
        logs.append(file)

    file = find_ngen_stdout_log(calibration_run)
    if file and os.path.exists(file):
        logs.append(file)

    ngen_log_dir = get_ngen_log_dir(calibration_run)
    # Find all log files in this directory
    base_path = Path(ngen_log_dir)
    files = [str(p) for p in base_path.glob("*.log")]
    logs.extend(files)

    return logs


def find_ngen_stdout_log(run: CalibrationRun | ValidationRun) -> str | None:
    """
    Searches for the `ngen.stdout` log file in worker directories of a given run.

    - Iterates over worker directories using `process_worker_dirs`.
    - Returns the path to the log file if found, otherwise returns None.

    :param run: The CalibrationRun or ValidationRun object.
    :return: The path of the `ngen.stdout` log file, or None if not found.
    """
    ngen_log_path = None

    # Custom function to check worker directories for the ngen log file
    def check_worker(worker_dir: str, _run: CalibrationRun | ValidationRun) -> bool:
        nonlocal ngen_log_path
        potential_log_path = os.path.join(worker_dir, get_ngen_stdout_log_filename())

        # Check if ngen stdout file exists in the current worker directory
        if potential_log_path and os.path.isfile(potential_log_path):
            ngen_log_path = potential_log_path
            return True  # stop searching

        return False  # keep searching

    # Call process_worker_dirs to iterate through the worker directories
    process_worker_dirs(run, check_worker)

    return ngen_log_path


def normalize_log_path(path: str) -> str:
    """
    Normalizes a log path to a canonical absolute path for reliable comparison.

    - Resolves relative segments such as '.' and '..'.
    - Uses strict=False so normalization does not fail solely because the file
      does not exist at the time of normalization.

    :param path: The input filesystem path.
    :return: A normalized absolute path string.
    """
    return str(Path(path).resolve(strict=False))
