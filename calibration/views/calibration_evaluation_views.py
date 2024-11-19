import logging
import os
from typing import Any

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
    get_validation_iteration_stdout_file, get_ngen_stdout_log_filename, get_ngen_log_path
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

    # Construct iteration data with parameters, metrics and validation reference for each iteration
    iteration_data = []
    for iteration in iterations:
        # Find a ValidationRun with status 'Done' for this iteration
        validation_run = (
            ValidationRun.objects
            .filter(iteration=iteration, status=StatusEnum.DONE.db_instance)
            .select_related('calibration_run')
            .first()
        )

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
        .select_related('calibration_run')
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
    run_id = calibration_run_id or validation_run_id

    # Retrieve the appropriate run
    run_func = get_calibration_run if calibration_run_id else get_validation_run
    run, error_return = run_func(
        run_id,
        request.user,
        run_status=[StatusEnum.RUNNING, StatusEnum.DONE, StatusEnum.FAILED, StatusEnum.SERVER_ERROR]
    )
    if error_return:
        return error_return

    # Determine calibration and validation runs
    calibration_run = run if calibration_run_id else run.calibration_run
    validation_run = run if validation_run_id else None
    validation_type = validation_run.validation_type if validation_run else None

    response = {
        'message': f"{'Calibration' if calibration_run_id else 'Validation'} Run job {run.id} logs retrieved",
        'calibration_run_id': calibration_run.id,
        'status': calibration_run.status.name,
        'validations': []
    }

    # Fetch logs based on the run type and validation type
    if calibration_run_id or validation_type in {ValidationType.VALID_BEST.value, ValidationType.VALID_CONTROL.value}:
        # Find the Best and Control validation runs
        validations = ValidationRun.objects.filter(
            calibration_run=calibration_run,
            validation_type__in=[ValidationType.VALID_BEST.value, ValidationType.VALID_CONTROL.value]
        ).select_related('calibration_run', 'iteration')

        # Retrieve calibration logs
        response['logs'] = get_calibration_logs(calibration_run)

        # Retrieve logs for Best and Control validation types
        response['validations'].extend(get_best_and_control_validation_ngen_cal_stdout_logs(calibration_run))

        # Loop through the validation runs to add the ngen stdout log
        for v in validations:
            ngen_stdout_content = fetch_log(find_ngen_stdout_log(v), 'ngen stdout')
            if ngen_stdout_content:
                # Find the corresponding validation entry and append the ngen stdout log
                for validation_entry in response['validations']:
                    if validation_entry['validation_run_id'] == v.id:
                        # Ensure logs key exists and append the fetched logs
                        if 'logs' not in validation_entry:
                            validation_entry['logs'] = []
                        validation_entry['logs'].extend(ngen_stdout_content)
                        break
    elif validation_type == ValidationType.VALID_ITERATION.value:
        # For VALID_ITERATION type, retrieve specific validation iteration logs
        iteration_logs = fetch_log(find_ngen_stdout_log(validation_run), 'ngen stdout')
        ngen_cal_stdout_content = fetch_log(get_validation_iteration_stdout_file(calibration_run, validation_run.iteration.worker_name, validation_run.iteration.iteration_num), 'ngen-cal stdout')

        validation_entry = get_validation_iteration_logs(validation_run)
        # Ensure the logs from fetch_log are added to the existing entry
        validation_entry['logs'] = iteration_logs + ngen_cal_stdout_content if iteration_logs or ngen_cal_stdout_content else []
        response['validations'].append(validation_entry)

    # Add ngen logs to the response
    response.setdefault('logs', []).extend(get_ngen_log(calibration_run))

    response_validator, error_response = validate_response(GetLogsResponseSerializer, response)
    if error_response:
        return error_response

    logger.debug(f'Returning to {request.user.email} from get_logs() - {response_validator.data}')
    return Response(response_validator.data)


def fetch_log(file_path: str, log_key: str) -> list[dict[str, list[str]]]:
    """
    Reads a log file and returns its content as a dictionary with the given key.

    :param file_path: The path to the log file.
    :param log_key: The key under which the log content will be stored.
    :return: A list containing a dictionary with the log content, or an empty list if the file doesn't exist.
    """
    if file_path and os.path.exists(file_path):
        return [{log_key: read_file_with_null_replacement(file_path)}]
    return []


def get_calibration_logs(calibration_run: CalibrationRun) -> list[dict[str, list[str]]]:
    """
    Retrieves logs for the specified calibration run.

    :param calibration_run: The CalibrationRun object.
    :return: A list of log entries.
    """
    logs = []
    logs.extend(fetch_log(get_calibration_stdout_file(calibration_run), 'ngen_cal stdout'))
    logs.extend(fetch_log(find_ngen_stdout_log(calibration_run), 'ngen stdout'))
    return logs


def get_ngen_log(calibration_run: CalibrationRun) -> list[dict[str, list[str]]]:
    """
    Retrieves the ngen logs.

    :param calibration_run: The CalibrationRun object.
    :return: A list of log entries.
    """
    return fetch_log(get_ngen_log_path(calibration_run), 'ngen')


def read_file_with_null_replacement(file_path: str) -> list[str]:
    """
    Reads a file, replacing null characters with spaces to avoid errors.

    :param file_path: Path to the file.
    :return: List of lines with null characters replaced by spaces.
    """
    with open(file_path, 'r') as file:
        return [line.replace('\x00', ' ') for line in file]


def get_best_and_control_validation_ngen_cal_stdout_logs(calibration_run: CalibrationRun) -> list[dict[str, Any]]:
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
            if os.path.exists(stdout_file):
                logs = [{'ngen-cal stdout': read_file_with_null_replacement(stdout_file)}]
                validation_logs.append({
                    'validation_run_id': validation_run.id,
                    'status': validation_run.status.name,
                    'validation_type': validation_type,
                    'logs': logs
                })

    return validation_logs


def get_validation_iteration_logs(validation_run: ValidationRun) -> dict[str, Any]:
    """
    Retrieves logs for a specific 'valid_iteration' type validation run.

    :param validation_run: The ValidationRun instance.
    :return: A dictionary containing validation log data.
    """
    stdout_file = get_validation_iteration_stdout_file(
        validation_run.calibration_run,
        validation_run.worker_name,
        validation_run.iteration_num
    )
    logs = fetch_log(stdout_file, 'ngen-cal stdout')
    return {
        'validation_run_id': validation_run.id,
        'status': validation_run.status.name,
        'validation_type': validation_run.validation_type,
        'logs': logs
    }


def find_ngen_stdout_log(run: CalibrationRun | ValidationRun) -> str | None:
    """
    Searches the worker directories of a run to locate the ngen stdout file.

    :param run: The CalibrationRun or ValidationRun object to process.
    :return: The path of the ngen stdout file if found, otherwise None.
    """
    ngen_log_path = None

    # Custom function to check worker directories for the ngen.log file
    def check_worker(worker_dir: str, run_object: CalibrationRun | ValidationRun):
        nonlocal ngen_log_path
        potential_log_path = os.path.join(worker_dir, get_ngen_stdout_log_filename())

        # Check if ngen stdout file exists in the current worker directory
        if os.path.isfile(potential_log_path):
            ngen_log_path = potential_log_path

    # Call process_worker_dirs to iterate through the worker directories
    process_worker_dirs(run, check_worker)

    return ngen_log_path
