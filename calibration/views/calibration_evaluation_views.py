import logging

from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.enums import StatusEnum, ValidationType
from calibration.models import Iteration, ValidationRun, IterationParameter
from calibration.util.calibration_validators import CalibrationRunSerializer, IsReadyResponseSerializer, ErrorResponseSerializer, \
    GetCalibrationDataByIterationResponseSerializer, GetValidationJobsResponseSerializer
from calibration.views.common import get_calibration_run, handle_exceptions, validate_response, validate_request

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
def get_calibration_data_by_iteration(request):
    data = request.data
    logger.debug(f'get_calibration_data_by_iteration() request from {request.user} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=[StatusEnum.DONE])
    if error_return:
        return error_return

    # Fetch all iterations for the calibration run, along with related parameters and metrics
    iterations = (
        Iteration.objects
        .filter(calibration_run_id=calibration_run_id)
        .prefetch_related('iterationparameter_set', 'iterationmetric_set')  # prefetch related data for parameters and metrics
        .order_by('worker_name', 'iteration_num')  # organize by worker name and iteration number
    )

    iteration_data = []
    for iteration in iterations:
        iteration_element = {
            'iteration_num': iteration.iteration_num,
            'iteration_id': iteration.id,
            'worker_name': iteration.worker_name,
            'best_params': iteration.best_params,
            # TODO Rename to objective function value
            'calibration_output_variable_value': iteration.calibration_output_variable_value,
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

    response = {'message': f'Calibration Run {run.id}, data retrieve', 'iteration_data': iteration_data}

    response_validator, error_response = validate_response(GetCalibrationDataByIterationResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user} from get_calibration_data_by_iteration() - {response_validator.data}')
    return Response(response_validator.data)


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
def get_validation_jobs(request):
    data = request.data if request.method == 'POST' else request.query_params.dict()

    logger.debug(f'get_validation_jobs() request from {request.user} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    calibration_run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=[StatusEnum.DONE])
    if error_return:
        return error_return

    # Query all validation jobs for the calibration run, excluding VALID_CONTROL types
    validation_jobs = ValidationRun.objects.filter(
        calibration_run_id=calibration_run_id,
        status__in=[StatusEnum.from_enum(StatusEnum.DONE), StatusEnum.from_enum(StatusEnum.RUNNING)]
    ).exclude(
        validation_type=ValidationType.VALID_CONTROL.value
    )

    result = []
    for validation_run in validation_jobs:
        # Get all IterationParameters related to this validation run's Iteration
        iteration_params = IterationParameter.objects.filter(iteration=validation_run.iteration)

        # Create a list of parameters for this validation run
        params_list = [
            {'name': param['calibration_parameter__name'], 'value': param['tuned_value']}
            for param in iteration_params.values('calibration_parameter__name', 'tuned_value')
        ]

        # Construct the object containing validation_run_id, run_date, and parameters list
        result.append({
            'validation_run_id': validation_run.id,
            'run_date': validation_run.run_date,
            'parameters': params_list,
            'best': validation_run.validation_type == ValidationType.VALID_BEST.value
        })

    response = {'validation_jobs': result}

    response_validator, error_response = validate_response(GetValidationJobsResponseSerializer, response)
    if error_response:
        return error_response

    logger.debug(f'Returning to {request.user} from get_validation_jobs() - {response_validator.data}')
    return Response(response_validator.data)
