import io
import json
import logging
import os
import threading
import time
import zipfile
from datetime import datetime

from django.db.models import F, QuerySet
from django.http import HttpResponse, StreamingHttpResponse, FileResponse
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from calibration.enums import StatusEnum, ValidationMetricPeriod, ValidationType, LogCategory, LogName
from calibration.models import Iteration, NWMRetrospectiveMetrics, CalibrationRun, ValidationRun, ForecastRun
from calibration.util.calibration_validators import CalibrationRunSerializer, ErrorResponseSerializer, \
    GetCalibrationDataByIterationResponseSerializer, GetLogsResponseSerializer, ValidationRunSerializer, \
    GetLogNamesResponseSerializer, GetLogRequestSerializer, GenericMessageWithIdResponseSerializer
from calibration.util.ngen_locations import get_calibration_stdout_file, get_validation_best_stdout_file, get_validation_control_stdout_file, \
    get_validation_iteration_stdout_file, get_ngen_stdout_log_filename, get_ngen_log_path
from calibration.views.called_from import get_caller_name
from calibration.views.common import get_calibration_run, handle_exceptions, validate_response, validate_request, truncate_large_fields, \
    get_validation_run, CerfException, replace_nan_and_inf_with_none, process_worker_dirs, get_user_email, ResponseError

logger = logging.getLogger(__name__)


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
        .only('metric__name', 'metric_value')
        .annotate(metric_name=F('metric__name'))
        .values('metric_name', 'metric_value')
    )

    retrospective_data = [{'name': 'NWM 3.0', 'data': nwm_retrospective_data}]

    iterations = get_iterations_for_calibration_job(run)

    # Prefetch validation runs for all iterations
    validation_runs = ValidationRun.objects.filter(
        iteration__in=iterations, status=StatusEnum.DONE.db_instance
    ).select_related('calibration_run')

    validation_runs_by_iteration = {vr.iteration_id: vr for vr in validation_runs}

    # Construct iteration data with parameters, metrics, and validation reference
    iteration_data = []
    for iteration in iterations:
        validation_run = validation_runs_by_iteration.get(iteration.id)

        iteration_element = {
            'iteration_num': iteration.iteration_num,
            'iteration_id': iteration.id,
            'worker_name': iteration.worker_name,
            'best_params': iteration.best_params,
            'objective_function_value': iteration.objective_function_value,
            'parameters': [
                {'parameter_name': param.calibration_parameter.name, 'parameter_value': param.tuned_value}
                for param in iteration.iterationparameter_set.all()
            ],
            'metrics': [
                {'metric_name': metric.metric.name, 'metric_value': metric.metric_value}
                for metric in iteration.iterationmetric_set.all()
            ]
        }
        if validation_run:
            iteration_element['validation_run_id'] = validation_run.id
        iteration_data.append(iteration_element)

    response = {
        'message': f'Calibration Job {run.id}, data retrieved',
        'objective_function_metric': run.objective_function.name,
        'iteration_data': iteration_data,
        'retrospective_data': retrospective_data
    }

    # Replace NaN values with None for JSON compatibility
    response = replace_nan_and_inf_with_none(response)

    response_validator, error_response = validate_response(
        GetCalibrationDataByIterationResponseSerializer,
        response,
        fields_to_truncate=['iteration_data'],
        max_length=10
    )
    if error_response:
        return error_response

    logger.debug(
        f'Returning to {get_user_email(request)} from {get_caller_name()}() - '
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
    request=ValidationRunSerializer,
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
    Retrieves a list of available log names for a specific validation run.

    - Handles request validation and user permissions.
    - Returns logs categorized by their association (calibration, validation, global, or forecast).

    :param request: The HTTP request object containing validation run ID.
    :return: JSON response with log names or error details.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {data}')

    validator, error_return = validate_request(ValidationRunSerializer, data)
    if error_return:
        return error_return

    validation_run_id = validator.get('validation_run_id')

    validation_run, error_return = get_validation_run(
        validation_run_id,
        request.user,
        run_status=[StatusEnum.RUNNING, StatusEnum.DONE, StatusEnum.FAILED, StatusEnum.SERVER_ERROR]
    )
    if error_return:
        return error_return

    # Define available log categories and names
    log_names = [
        {LogCategory.CALIBRATION.value: ['ngen stdout', 'ngen-cal stdout']},
        {LogCategory.VALIDATION.value: ['ngen-cal stdout']},
        {LogCategory.GLOBAL.value: ['ngen']},
    ]
    # Include forecast logs if applicable
    if ForecastRun.objects.filter(calibration_run=validation_run.calibration_run).exists():
        log_names.append({LogCategory.FORECAST.value: ['ngen stdout', 'forecast stdout']})

    response = {'log_names': log_names}

    response_validator, error_response = validate_response(GetLogNamesResponseSerializer, response)
    if error_response:
        return error_response

    logger.debug(f'Returning to {get_user_email(request)} from {get_caller_name()}() - {json.dumps(response_validator.data)}')
    return Response(response_validator.data)


VALID_LOG_NAMES = {
    LogCategory.CALIBRATION: [LogName.NGEN_CAL_STDOUT, LogName.NGEN_STDOUT],
    LogCategory.VALIDATION: [LogName.NGEN_CAL_STDOUT, LogName.NGEN_STDOUT],
    LogCategory.FORECAST: [LogName.FORECAST_STDOUT, LogName.NGEN_STDOUT],
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
    valid_logs = VALID_LOG_NAMES.get(log_category)

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
    Retrieves a specific log file for a validation run and its associated calibration run.

    - Supports pagination for large log files.
    - Validates log category and log name.

    :param request: The HTTP request object containing validation run and log information.
    :return: JSON response with log file content or error details.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {data}')

    validator, error_return = validate_request(GetLogRequestSerializer, data)
    if error_return:
        return error_return

    validation_run_id = validator.get('validation_run_id')
    log_category = LogCategory(validator.get('log_category'))
    log_name = LogName(validator.get('log_name'))
    start = validator.get('start')
    limit = validator.get('limit')

    # Validate log category and log name
    try:
        validate_log_name(log_category, log_name)
    except ValueError as e:
        raise CerfException(str(e))

    validation_run, error_return = get_validation_run(
        validation_run_id,
        request.user,
        run_status=[StatusEnum.RUNNING, StatusEnum.DONE, StatusEnum.FAILED, StatusEnum.SERVER_ERROR]
    )
    if error_return:
        return error_return

    match log_category:
        case LogCategory.CALIBRATION:
            log_path = get_calibration_log(validation_run.calibration_run, log_name)
        case LogCategory.VALIDATION:
            log_path = get_validation_log(validation_run, log_name)
        case LogCategory.GLOBAL:
            log_path = get_global_log(validation_run, log_name)
        case _:
            raise CerfException(f"Unknown log category '{log_category.value}'")

    # Check if the log file exists
    if not os.path.exists(log_path):
        raise CerfException(f"Log file not found: {log_path}")

    # Count the total number of lines in the file for pagination metadata
    total_lines = sum(1 for _ in open(log_path, 'r'))

    # Read the requested lines from the log file with null replacement
    paginated_lines = []
    with open(log_path, 'r') as file:
        for current_line_number, line in enumerate(file):
            if start <= current_line_number < start + limit:
                # Replace null characters in each line
                paginated_lines.append(line.replace('\x00', ' '))
            if current_line_number >= start + limit:
                break

    pagination_metadata = {
        'start': start,
        'limit': limit,
        'count': total_lines
    }

    response = {
        'message': f"{log_category.value.capitalize()} {log_name.value} log file retrieved",
        'log_data': paginated_lines,
        'log_path': log_path,
        'pagination_metadata': pagination_metadata
    }

    response_validator, error_response = validate_response(GetLogsResponseSerializer, response)
    if error_response:
        return error_response

    logger.debug(f'Returning to {get_user_email(request)} from {get_caller_name()}() - {json.dumps(response_validator.data)}')
    return Response(response_validator.data)


def get_calibration_log(calibration_run: CalibrationRun, log_name: LogName):
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


def get_validation_log(validation_run: ValidationRun, log_name: LogName):
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


def get_global_log(validation_run: ValidationRun, log_name: LogName):
    """
    Retrieves the global log file, if applicable.

    - Only supports `ngen` logs currently.

    :param validation_run: The ValidationRun object associated with the log.
    :param log_name: The LogName enum specifying the log type.
    :return: The path to the global log file.
    """
    if log_name == LogName.NGEN:
        return get_ngen_log_path(validation_run.calibration_run)


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
        if os.path.isfile(potential_log_path):
            ngen_log_path = potential_log_path

    # Call process_worker_dirs to iterate through the worker directories
    process_worker_dirs(run, check_worker)

    return ngen_log_path

    
downloadable_statuses = [s for s in StatusEnum if s not in {StatusEnum.READY, StatusEnum.SAVED}]



# Track zip status and paths in memory (can also use DB or cache if needed)
zip_status_map = {}  # calibration_run_id -> {"status": "pending|done|error", "path": "zipfile.zip"}


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
    Starts the process to zip calibration job files in a background thread.
    Returns immediately with a job ID (calibration_run_id).
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    downloadable_statuses = [s for s in StatusEnum if s not in {StatusEnum.READY, StatusEnum.SAVED}]
    run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=downloadable_statuses)
    if error_return:
        return error_return

    existing_status = zip_status_map.get(calibration_run_id)
    if existing_status and existing_status["status"] == "pending":
        logger.info(f"Zip job already in progress for Calibration Job {calibration_run_id}")
        return Response({
            "message": "Zip job already in progress",
            "status": existing_status["status"],
            "calibration_run_id": calibration_run_id
        })
    # Mark status as pending
    zip_status_map[calibration_run_id] = {
        "status": "pending",
        "path": None,
        "started_at": datetime.now().isoformat()
    }

    # Launch zip process in background
    def zip_job():
        start_time = datetime.now()
        try:
            job_data_dir = run.job_data_dir
            zip_name = f"{os.path.basename(job_data_dir)}_{run.user_formulation_name}"
            zip_path = f"/tmp/{zip_name}.zip"

            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for root, _, files in os.walk(job_data_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arc_name = os.path.relpath(file_path, job_data_dir)
                        try:
                            zip_file.write(file_path, arc_name)
                        except FileNotFoundError:
                            logger.warning(f"File not found during zipping: {arc_name}")

            # Mark the zip job as complete
            zip_status_map[calibration_run_id] = {
                "status": "done",
                "path": zip_path,
                "started_at": zip_status_map[calibration_run_id]["started_at"]
            }

            duration = datetime.now() - start_time
            logger.info(f"Zip job completed for Calibration Job {run.id} in {duration.total_seconds():.2f} seconds")

        except Exception as e:
            zip_status_map[calibration_run_id] = {
                "status": "error",
                "path": None,
                "started_at": zip_status_map[calibration_run_id].get("started_at")
            }
            duration = datetime.now() - start_time
            logger.exception(f"Failed to zip Calibration Job {run.id} after {duration.total_seconds():.2f} seconds: {e}")

    threading.Thread(target=zip_job).start()

    response = ({"message": "Zip job started", "calibration_run_id": calibration_run_id})

    response_validator, error_response = validate_response(GenericMessageWithIdResponseSerializer, response)
    if error_response:
        return error_response

    logger.debug(f'Returning to {get_user_email(request)} from {get_caller_name()}() - {json.dumps(response_validator.data)}')
    return Response(response_validator.data)


@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: OpenApiResponse(description="Server-Sent Events stream with zip job status updates"),
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Streams zip status updates in real time via Server-Sent Events (SSE)"
)
@api_view(['GET'])
@handle_exceptions
def get_zip_status(request: Request, calibration_run_id: int) -> StreamingHttpResponse:
    """
    SSE (Server-Sent Events) endpoint that streams the status of a background zip job.

    - Streams status updates (e.g., "pending", "done", "error") to the client.
    - Closes the connection once the job is complete or encounters an error.
    - Useful for notifying the UI in real time without polling.

    :param request: HTTP request object.
    :param calibration_run_id: The ID of the calibration job being zipped.
    :return: StreamingHttpResponse with real-time status updates.
    """

    def event_stream():
        start_time = datetime.now()
        logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} for Calibration Run id {calibration_run_id}')

        # Stream loop: keep checking the job status until it is "done" or "error"
        while True:
            # Retrieve the current zip status from in-memory map
            status = zip_status_map.get(calibration_run_id, {"status": "not_found"})

            # Format the status as an SSE-compatible message
            yield f"data: {json.dumps(status)}\n\n"

            # If job has finished or failed, stop the stream (connection closes)
            if status["status"] in ["done", "error"]:
                duration = datetime.now() - start_time
                logger.debug(
                    f'{get_caller_name()}() streaming complete for {get_user_email(request)} - calibration_run_id={calibration_run_id} - status={status["status"]} - '
                    f'duration={duration.total_seconds():.2f}s'
                )
                break

            # Sleep before checking again (keeps CPU usage low and reduces frequency)
            time.sleep(1)

    # Return a streaming HTTP response using the generator function above
    return StreamingHttpResponse(event_stream(), content_type="text/event-stream")


@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: OpenApiResponse(description="ZIP file ready for download"),
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Returns the zipped calibration job if ready. Automatically deletes the file after sending."
)
@api_view(['GET', 'POST'])
@handle_exceptions
def download_calibration_zip(request: Request) -> FileResponse | Response:
    """
    Serves the zipped calibration job data for download after it has been prepared.

    - Extracts calibration_run_id from POST or GET parameters.
    - Validates that the zip process has completed.
    - Returns the ZIP file as an attachment if available.
    - Returns an error response if the file is not ready or missing.

    :param request: The HTTP request object.
    :return: HTTP response with the ZIP file or a formatted error response.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {data}')

    validator, error_response = validate_request(CalibrationRunSerializer, data)
    if error_response:
        return error_response

    calibration_run_id = validator.get("calibration_run_id")

    status_info = zip_status_map.get(calibration_run_id)
    if not status_info:
        return ResponseError(f"Zip job not found for Calibration Job {calibration_run_id}")

    if status_info["status"] != "done":
        return ResponseError(f"Zip file for Calibration Job {calibration_run_id} is not ready yet")

    zip_path = status_info.get("path")
    if not zip_path or not os.path.exists(zip_path):
        return ResponseError(f"Zip file is missing for Calibration Job {calibration_run_id}")

    try:
        response = FileResponse(open(zip_path, 'rb'), content_type='application/zip')
        filename = os.path.basename(zip_path)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        def cleanup():
            try:
                os.remove(zip_path)
                logger.info(f"Deleted zip file after download: {zip_path}")
            except Exception as ex:
                logger.warning(f"Failed to delete zip file {zip_path}: {ex}")
            zip_status_map.pop(calibration_run_id, None)

        # Hook into response close for cleanup
        response.close = (lambda original_close=response.close:
                          lambda: (cleanup(), original_close())[1])()

        logger.debug(f'Returning zip for Calibration Job {calibration_run_id} to {get_user_email(request)} from {get_caller_name()}()')
        return response

    except IOError as e:
        logger.exception(f"Failed to read zip file for Calibration Job {calibration_run_id}: {e}")
        return ResponseError(f"Failed to read zip file for Calibration Job {calibration_run_id}")
