import logging

from django.core.cache import cache
from django.db import transaction
from django.db.models import F
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.enums import OptimizationEnum
from calibration.models import Optimization, Metric, OptimizationInput, CalibrationOptimizationInput, CalibrationStopCriteria
from calibration.util.calibration_validators import CalibrationRunSerializer, LoadOptimizationResponseSerializer, \
    SaveOptimizationRequestSerializer, SaveOptimizationResponseSerializer, ErrorResponseSerializer
from calibration.views import ngen_cal_input
from calibration.views.common import get_run, ResponseError, handle_exceptions, validate_response, validate_request

logger = logging.getLogger(__name__)


@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: LoadOptimizationResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: ErrorResponseSerializer
    },
    parameters=[
        OpenApiParameter(name='calibration_run_id', description='ID of the calibration run', required=True, type=int)
    ],
    description="Load optimization tab data"
)
@api_view(['GET', 'POST'])
# @permission_classes([AllowAny])()
@handle_exceptions
def load_optimization_tab(request):
    data = request.data if request.method == 'POST' else request.query_params

    logger.debug(f'load_optimization_tab() request from {request.user} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_run(calibration_run_id, request.user)
    if error_return:
        return error_return

    metrics = get_metrics()

    optimization_list = get_static_optimizations()

    ngen_cal_input.ready_to_run(run)
    response = {'calibration_run_id': run.id, 'status': run.status.name,
                'metrics': metrics,
                'optimizations': optimization_list
                }

    response = {key: value for key, value in response.items() if value not in [None, '', [], {}]}

    response_validator, error_response = validate_response(LoadOptimizationResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user} from load_optimization_tab() - {response_validator.data}')
    return Response(response_validator.data)


def get_user_optimization(run):
    if run.optimization:
        optimization = run.optimization.name
        optimization_inputs = list(
            CalibrationOptimizationInput.objects.filter(calibration_run=run).select_related('optimization_input')
            .values('value', name=F('optimization_input__name')))
    else:
        optimization = None
        optimization_inputs = []

    return optimization, optimization_inputs


def get_static_optimizations():
    optimization_list = OptimizationEnum.active_choices_with_fields(
        fields=['name', 'description', 'is_active']
    )

    for optimization in optimization_list:
        optimization_obj: Optimization = OptimizationEnum.get_instance(optimization['name'])

        inputs = list(optimization_obj.inputs.values('name', 'description', 'data_type', 'is_active'))
        optimization['inputs'] = inputs

    return optimization_list


def get_metrics():
    cache_key = 'active_metrics'
    metrics = cache.get(cache_key)
    if metrics is None:
        # Fetch metrics from the database if not cached
        metrics = list(Metric.objects.filter(is_active=True).values(
            'name', 'description', 'is_active', 'categorical', 'event_based'
        ))
        cache.set(cache_key, metrics, timeout=None)
    return metrics


# noinspection PyUnusedLocal
@extend_schema(
    request=SaveOptimizationRequestSerializer,
    responses={
        200: SaveOptimizationResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: ErrorResponseSerializer
    },
    description="Save optimization tab data"
)
@api_view(['POST'])
# @permission_classes([AllowAny])
@handle_exceptions
def save_optimization_tab(request):
    data = request.data

    logger.debug(f'save_optimization_tab() request from {request.user} - {data}')

    validator, error_return = validate_request(SaveOptimizationRequestSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    optimization_name = validator.get('optimization')
    objective_function_name = validator.get('objective_function')
    streamflow_threshold = validator.get('streamflow_threshold')
    peak_flow_threshold = validator.get('peak_flow_threshold')
    optimization_inputs = validator.get('optimization_inputs')
    stop_criteria = validator.get('stop_criteria')
    plot_frequency = validator.get('plot_frequency')

    run, error_return = get_run(calibration_run_id, request.user)
    if error_return:
        return error_return

    if optimization_inputs and not optimization_name:
        return ResponseError('Optimization inputs cannot be specified without an optimization name')

    optimization, message = validate_optimizations(run, optimization_name, optimization_inputs)
    if message:
        return ResponseError(message)

    message = validate_objective_function(run, objective_function_name, streamflow_threshold, peak_flow_threshold)
    if message:
        return ResponseError(message)

    run.plot_frequency = plot_frequency
    run.streamflow_threshold = streamflow_threshold
    run.peak_flow_threshold = peak_flow_threshold

    with transaction.atomic():
        # I'm assuming for now that there is just one CalibrationStopCriteria for this run, but that might change in the future
        CalibrationStopCriteria.objects.update_or_create(calibration_run=run, defaults={"value": stop_criteria})

        write_optimization_inputs(run, optimization, optimization_inputs)

        run.save()

        ngen_cal_input.ready_to_run(run)

        response = {'message': f'Calibration Run {run.id} updated', 'calibration_run_id': run.id, 'status': run.status.name}

        response_validator, error_response = validate_response(SaveOptimizationResponseSerializer, response)
        if error_response:
            return error_response
        logger.debug(f'Returning to {request.user} from save_optimization_tab() - {response_validator.data}')
        return Response(response_validator.data)


def validate_optimizations(run, optimization_name, optimization_inputs):
    optimization = Optimization.objects.filter(name=optimization_name, is_active=True).first() if optimization_name else None
    if not optimization:
        return None, "Invalid optimization - '{}'".format(optimization_name)

    run.optimization = optimization

    if optimization_inputs:
        valid_inputs = OptimizationInput.objects.filter(
            optimization=optimization, name__in=[o['name'] for o in optimization_inputs], is_active=True
        )
        valid_inputs_dict = {input.name: input for input in valid_inputs}

        optimization_inputs_to_create = []
        for o in optimization_inputs:
            name = o['name']
            optimization_input = valid_inputs_dict.get(name)
            if not optimization_input:
                return None, "'{}' is not a valid parameter input for '{}'".format(name, optimization_name)
            optimization_inputs_to_create.append(
                CalibrationOptimizationInput(optimization_input=optimization_input, calibration_run=run, value=o['value'])
            )

        CalibrationOptimizationInput.objects.bulk_create(optimization_inputs_to_create)

    return optimization, None


def validate_objective_function(run, objective_function_name, streamflow_threshold, peak_flow_threshold):
    if objective_function_name:
        objective_function = Metric.objects.filter(name=objective_function_name, is_active=True).first()
        if not objective_function:
            return "Invalid metric specified for objective function - '{}'".format(objective_function_name)

        run.objective_function = objective_function

        if objective_function.categorical:
            if not streamflow_threshold:
                return "Streamflow threshold must be specified for a categorical function'"
            run.streamflow_threshold = streamflow_threshold

        if objective_function.event_based:
            if not streamflow_threshold:
                return "Peak flow threshold must be specified for an event_based function'"
            run.peak_flow_threshold = peak_flow_threshold
    return None


def write_optimization_inputs(run, optimization, optimization_inputs):
    # Delete existing optimization inputs first
    CalibrationOptimizationInput.objects.filter(calibration_run=run).delete()
    if optimization_inputs:
        for o in optimization_inputs:
            optimization_input = OptimizationInput.objects.get(optimization=optimization, name=o['name'], is_active=True)
            CalibrationOptimizationInput.objects.create(optimization_input=optimization_input, calibration_run=run, value=o['value'])
