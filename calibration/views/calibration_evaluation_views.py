import json
import logging

from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.enums import StatusEnum
from calibration.models import Iteration
from calibration.util.calibration_validators import CalibrationRunSerializer, IsReadyResponseSerializer, GenericResponseSerializer, \
    ErrorResponseSerializer
from calibration.views.common import get_calibration_run, handle_exceptions, validate_response, validate_request

logger = logging.getLogger(__name__)


@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: IsReadyResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Return the status of a job"
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

    result = []
    for iteration in iterations:
        iteration_data = {
            'iteration_num': iteration.iteration_num,
            'worker_name': iteration.worker_name,
            'best_params': iteration.best_params,
            # TODO Rename to objective function value
            'calibration_output_variable_value': iteration.calibration_output_variable_value,
            'parameters': [],
            'metrics': []
        }

        # Get the parameters for the iteration
        for parameter in iteration.iterationparameter_set.all():
            iteration_data['parameters'].append({
                'calibration_parameter': parameter.calibration_parameter.name,
                'tuned_value': parameter.tuned_value
            })

        # Get the metrics for the iteration
        for metric in iteration.iterationmetric_set.all():
            iteration_data['metrics'].append({
                'metric': metric.metric.name,
                'metric_value': metric.metric_value
            })

        result.append(iteration_data)

    print('reuslts', json.dumps(result, indent=3))

    response = {'message': f'Calibration Run {run.id}, data retrieve', 'calibration_run_id': run.id, 'status': run.status.name, 'data': result}

    response_validator, error_response = validate_response(GenericResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user} from get_calibration_data_by_iteration() - {response_validator.data}')
    return Response(response_validator.data)
