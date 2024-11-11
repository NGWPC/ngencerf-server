import logging
import os

from django.db.models import F, QuerySet
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from calibration.enums import StatusEnum, ValidationMetricPeriod, ValidationType
from calibration.models import Iteration, NWMRetrospectiveMetrics, CalibrationRun, ValidationRun
from calibration.util.calibration_validators import CalibrationRunSerializer, ErrorResponseSerializer, \
    GetCalibrationDataByIterationResponseSerializer, GetValidationJobsResponseSerializer, CalibrationOrValidationRunSerializer, \
    GetLogsResponseSerializer
from calibration.util.ngen_locations import get_calibration_stdout_file, get_validation_best_stdout_file, get_validation_control_stdout_file, \
    get_validation_iteration_stdout_file
from calibration.views.calibration_landing_views import get_validation_jobs_internal
from calibration.views.common import get_calibration_run, handle_exceptions, validate_response, validate_request, truncate_large_fields, \
    replace_nan_with_none, get_validation_run
from calibration.views.read_output import process_worker_dirs

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
    description="Return metrics and parameters by iteration"
)
@api_view(['GET', 'POST'])
@handle_exceptions
def get_calibration_data_by_iteration(request: Request) -> Response:
    """
    Handles requests for retrieving calibration data by iteration for a specific calibration run.

    :param request: The HTTP request object containing calibration run data.
    :return: JSON response with calibration data or error information.
    """
    data = request.data
    logger.debug(f'get_calibration_data_by_iteration() request from {request.user.email} - {data}')

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
        .annotate(metric_name=F('metric__name'))
        .values('metric_name', 'metric_value')
    )

    retrospective_data = [{'name': 'NWM 3.0', 'data': nwm_retrospective_data}]

    iterations = get_iterations_for_calibration_job(run)

    # Construct iteration data with parameters and metrics for each iteration
    iteration_data = []
    for iteration in iterations:
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
        iteration_data.append(iteration_element)

    response = {
        'message': f'Calibration Run {run.id}, data retrieved',
        'objective_function_metric': run.objective_function.name,
        'iteration_data': iteration_data,
        'retrospective_data': retrospective_data
    }

    # Replace NaN values with None for JSON compatibility
    response = replace_nan_with_none(response)

    response_validator, error_response = validate_response(
        GetCalibrationDataByIterationResponseSerializer,
        response,
        fields_to_truncate=['iteration_data'],
        max_length=10
    )
    if error_response:
        return error_response

    logger.debug(
        f'Returning to {request.user.email} from get_calibration_data_by_iteration() - {truncate_large_fields(response_validator.data, fields_to_truncate=["iteration_data"], max_length=10)}')

    return Response(response_validator.data)


def get_iterations_for_calibration_job(calibration_run: CalibrationRun) -> QuerySet[Iteration]:
    """
    Fetches all iterations for the calibration run, along with related parameters and metrics.

    :param calibration_run: The CalibrationRun instance for which to fetch iterations.
    :return: A queryset of Iteration objects associated with the calibration run.
    """
    return (
        Iteration.objects
        .filter(calibration_run=calibration_run)
        .prefetch_related('iterationparameter_set__calibration_parameter', 'iterationmetric_set')
        .order_by('worker_name', 'iteration_num')  # organize by worker name and iteration number
    )

@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: GetValidationJobsResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Get validation jobs with starting parameter values"
)
@api_view(['POST', 'GET'])
@handle_exceptions
def get_validation_jobs(request: Request) -> Response:
    """
    Retrieves validation jobs for a specific calibration run with initial parameter values.

    :param request: The HTTP request object containing calibration run data.
    :return: JSON response with validation jobs or error information.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'get_validation_jobs() request from {request.user.email} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    calibration_run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=[StatusEnum.DONE])
    if error_return:
        return error_return

    # Retrieve validation jobs using internal helper
    validation_jobs = get_validation_jobs_internal(calibration_run_id, return_ids_only=False)

    response = {'validation_jobs': validation_jobs}
    response_validator, error_response = validate_response(GetValidationJobsResponseSerializer, response)
    if error_response:
        return error_response

    logger.debug(f'Returning to {request.user.email} from get_validation_jobs() - {response_validator.data}')
    return Response(response_validator.data)


@extend_schema(
    request=CalibrationOrValidationRunSerializer,
    responses={
        200: GetValidationJobsResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Get logs for a completed job"
)
@api_view(['POST', 'GET'])
@handle_exceptions
def get_logs(request: Request) -> Response:
    """
    Retrieves logs for a calibration or validation job, depending on the provided identifiers.

    :param request: The HTTP request object containing job identifiers.
    :return: JSON response with job logs or error information.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'get_logs() request from {request.user.email} - {data}')

    validator, error_return = validate_request(CalibrationOrValidationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    validation_run_id = validator.get('validation_run_id')

    # Determine job type and run function
    run_func = get_calibration_run if calibration_run_id else get_validation_run
    run_id = calibration_run_id or validation_run_id

    run, error_return = run_func(
        run_id,
        request.user,
        run_status=[StatusEnum.RUNNING, StatusEnum.DONE, StatusEnum.FAILED, StatusEnum.SERVER_ERROR]
    )
    if error_return:
        return error_return

    # Get the calibration run and determine if this is a validation run case
    calibration_run = run if calibration_run_id else run.calibration_run
    validation_run = run if validation_run_id else None
    validation_type = validation_run.validation_type if validation_run else None

    validations: list[dict] = []

    response = {
        'message': f"{'Calibration' if calibration_run_id else 'Validation'} Run job {run.id} logs retrieved",
        'calibration_run_id': calibration_run.id,
        'status': run.status.name,
        'validations': validations
    }

    if validation_run_id:
        response['validation_run_id'] = validation_run_id

    # If this is a calibration run or a validation with type valid_best or valid_control, include logs
    if calibration_run_id or (validation_type in {ValidationType.VALID_BEST.value, ValidationType.VALID_CONTROL.value}):
        logs = get_calibration_logs(calibration_run)
        validations.extend(get_best_and_control_validation_logs(calibration_run))
        response['logs'] = logs

    # If the request is for a specific validation iteration, fetch only its logs without calibration logs
    elif validation_type == ValidationType.VALID_ITERATION.value:
        validation_logs = get_validation_iteration_logs(validation_run)
        validations.append(validation_logs)

    # Validate and respond
    response_validator, error_response = validate_response(GetLogsResponseSerializer, response)
    if error_response:
        return error_response

    logger.debug(f'Returning to {request.user.email} from get_logs() - {response_validator.data}')
    return Response(response_validator.data)


def get_calibration_logs(calibration_run: CalibrationRun) -> list[dict[str, list[str]]]:
    """
    Retrieves logs for the specified calibration run.

    :param calibration_run: The CalibrationRun object.
    :return: A list of log entries.
    """
    logs = []

    stdout_file = get_calibration_stdout_file(calibration_run)
    if os.path.exists(stdout_file):
        logs.append({'ngen_cal': read_file_with_null_replacement(stdout_file)})

    ngen_log = find_ngen_log(calibration_run)
    if ngen_log and os.path.exists(ngen_log):
        logs.append({'ngen': read_file_with_null_replacement(ngen_log)})

    return logs


def read_file_with_null_replacement(file_path: str) -> list[str]:
    """
    Reads a file, replacing null characters with spaces to avoid errors.

    :param file_path: Path to the file.
    :return: List of lines with null characters replaced by spaces.
    """
    with open(file_path, 'r') as file:
        return [line.replace('\x00', ' ') for line in file]


def get_best_and_control_validation_logs(calibration_run: CalibrationRun) -> list[dict]:
    """
    Retrieves logs for 'valid_best' and 'valid_control' validation types for a calibration run.

    :param calibration_run: The CalibrationRun instance.
    :return: A list of validation log entries.
    """
    validation_logs = []

    for validation_type, get_file_func in [
        (ValidationType.VALID_BEST.value, get_validation_best_stdout_file),
        (ValidationType.VALID_CONTROL.value, get_validation_control_stdout_file)
    ]:
        validation_run = calibration_run.validations.filter(validation_type=validation_type).first()
        if validation_run:
            stdout_file = get_file_func(calibration_run)
            log_data = {
                'validation_job_id': validation_run.id,
                'status': validation_run.status.name,
                'validation_type': validation_type,
                'log': read_file_with_null_replacement(stdout_file) if os.path.exists(stdout_file) else []
            }
            validation_logs.append(log_data)

    return validation_logs


def get_validation_iteration_logs(validation_run: ValidationRun) -> dict[str, list[str]]:
    """
    Retrieves logs for a specific 'valid_iteration' type validation run.

    :param validation_run: The ValidationRun instance.
    :return: A dictionary containing validation log data.
    """
    stdout_file = get_validation_iteration_stdout_file(
        validation_run.calibration_run,
        validation_run.iteration.worker_name,
        validation_run.iteration.iteration_num
    )
    return {
        'validation_job_id': validation_run.id,
        'status': validation_run.status.name,
        'validation_type': validation_run.validation_type,
        'log': read_file_with_null_replacement(stdout_file) if os.path.exists(stdout_file) else []
    }


def find_ngen_log(calibration_run: CalibrationRun) -> str | None:
    """
    Searches the worker directories of a calibration run to locate the 'ngen.log' file.

    :param calibration_run: The calibration run object to process.
    :return: The path of the 'ngen.log' file if found, otherwise None.
    """
    ngen_log_path = None

    # Custom function to check worker directories for the ngen.log file
    def check_worker(worker_dir: str, run: CalibrationRun):
        nonlocal ngen_log_path
        potential_log_path = os.path.join(worker_dir, 'ngen.log')

        # Check if 'ngen.log' exists in the current worker directory
        if os.path.isfile(potential_log_path):
            ngen_log_path = potential_log_path

    # Call process_worker_dirs to iterate through the worker directories
    process_worker_dirs(calibration_run, check_worker)

    return ngen_log_path
