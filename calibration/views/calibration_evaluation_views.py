import logging

from django.db.models import F, QuerySet
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from calibration.enums import StatusEnum, ValidationMetricPeriod
from calibration.models import Iteration, NWMRetrospectiveMetrics, CalibrationRun
from calibration.util.calibration_validators import CalibrationRunSerializer, ErrorResponseSerializer, \
    GetCalibrationDataByIterationResponseSerializer, GetValidationJobsResponseSerializer
from calibration.views.calibration_landing_views import get_validation_jobs_internal
from calibration.views.common import get_calibration_run, handle_exceptions, validate_response, validate_request, truncate_large_fields, \
    replace_nan_with_none

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
            'parameters': [],
            'metrics': []
        }

        # Get the parameters for the iteration
        for parameter in iteration.iterationparameter_set.all():
            iteration_element['parameters'].append({
                'parameter_name': parameter.calibration_parameter.name,
                'parameter_value': parameter.tuned_value
            })

        # Get the metrics for the iteration
        for metric in iteration.iterationmetric_set.all():
            iteration_element['metrics'].append({
                'metric_name': metric.metric.name,
                'metric_value': metric.metric_value
            })

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
    iterations = (
        Iteration.objects
        .filter(calibration_run=calibration_run)
        .prefetch_related('iterationparameter_set__calibration_parameter', 'iterationmetric_set')
        .order_by('worker_name', 'iteration_num')  # organize by worker name and iteration number
    )
    return iterations


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

    # Use helper to get detailed validation job information
    validation_jobs = get_validation_jobs_internal(calibration_run_id, return_ids_only=False)

    response = {'validation_jobs': validation_jobs}
    response_validator, error_response = validate_response(GetValidationJobsResponseSerializer, response)
    if error_response:
        return error_response

    logger.debug(f'Returning to {request.user.email} from get_validation_jobs() - {response_validator.data}')
    return Response(response_validator.data)
