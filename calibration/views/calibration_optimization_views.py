import logging
from typing import List, Dict, Any

from django.core.cache import cache
from django.db import transaction
from django.db.models import F
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.enums import OptimizationEnum, StatusEnum
from calibration.models import Optimization, Metric, OptimizationInput, CalibrationOptimizationInput, CalibrationStopCriteria, CalibrationRun
from calibration.util.calibration_validators import CalibrationRunSerializer, LoadOptimizationResponseSerializer, \
    SaveOptimizationRequestSerializer, ErrorResponseSerializer, GenericResponseSerializer
from calibration.views import ngen_cal_input
from calibration.views.common import get_calibration_run, ResponseError, handle_exceptions, validate_response, validate_request
from calibration.views.read_output import get_cached_metrics

logger = logging.getLogger(__name__)


@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: LoadOptimizationResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
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
    data = request.data if request.method == 'POST' else request.query_params.dict()

    logger.debug(f'load_optimization_tab() request from {request.user.email} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=list(StatusEnum))
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
    logger.debug(f'Returning to {request.user.email} from load_optimization_tab() - {response_validator.data}')
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

        inputs = list(optimization_obj.inputs.values('name', 'description', 'data_type', 'is_active', 'default_value', 'min', 'max'))
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
        200: GenericResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Save optimization tab data"
)
@api_view(['POST'])
# @permission_classes([AllowAny])
@handle_exceptions
def save_optimization_tab(request):
    data = request.data

    logger.debug(f'save_optimization_tab() request from {request.user.email} - {data}')

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
    save_plot_iteration_frequency = validator.get('save_plot_iteration_frequency')
    save_output_iteration = validator.get('save_output_iteration')

    run, error_return = get_calibration_run(calibration_run_id, request.user)
    if error_return:
        return error_return

    if optimization_inputs and not optimization_name:
        return ResponseError('Optimization inputs cannot be specified without an optimization name')

    optimization, error_message = validate_optimizations(run, optimization_name, optimization_inputs)
    if error_message:
        return ResponseError(error_message)

    error_message = validate_objective_function(run, objective_function_name, streamflow_threshold, peak_flow_threshold)
    if error_message:
        return ResponseError(error_message)

    run.save_plot_iteration_frequency = save_plot_iteration_frequency

    # This field is not supported by UI, so if not specified, leave it alone
    if save_output_iteration is not None:
        run.save_output_iteration = save_output_iteration

    run.streamflow_threshold = streamflow_threshold
    run.peak_flow_threshold = peak_flow_threshold

    with transaction.atomic():
        if stop_criteria is not None:
            # I'm assuming for now that there is just one CalibrationStopCriteria for this run, but that might change in the future
            CalibrationStopCriteria.objects.update_or_create(calibration_run=run, defaults={"value": stop_criteria})

        write_optimization_inputs(run, optimization, optimization_inputs)

        run.save()

        ngen_cal_input.ready_to_run(run)

        response = {'message': f'Calibration Run {run.id} updated', 'calibration_run_id': run.id, 'status': run.status.name}

        response_validator, error_response = validate_response(GenericResponseSerializer, response)
        if error_response:
            return error_response
        logger.debug(f'Returning to {request.user.email} from save_optimization_tab() - {response_validator.data}')
        return Response(response_validator.data)


def validate_optimizations(run, optimization_name, optimization_inputs):
    optimization = OptimizationEnum.get_instance(optimization_name)

    run.optimization = optimization

    if optimization_inputs:
        # Retrieve cached optimization inputs
        valid_inputs_dict = {
            input_data['name']: input_data
            for input_data in get_cached_optimization_inputs(optimization_name)
        }

        optimization_inputs_to_create = []
        for o in optimization_inputs:
            name = o['name']
            value = o['value']
            optimization_input_data = valid_inputs_dict.get(name)

            if not optimization_input_data:
                return None, f"'{name}' is not a valid parameter input for '{optimization_name}'"

            # Safely retrieve min and max values
            min_value = optimization_input_data['min']
            max_value = optimization_input_data['max']

            # Convert types if necessary for validation
            if optimization_input_data['data_type'] != 'double':
                # noinspection PyTypeChecker
                min_value = int(min_value) if min_value is not None else None
                # noinspection PyTypeChecker
                max_value = int(max_value) if max_value is not None else None
                value = int(value)

            # Validate against min and max
            if min_value is not None and value < min_value:
                return None, f"'{name}' value ({value}) is below the minimum allowed ({min_value})"
            if max_value is not None and value > max_value:
                return None, f"'{name}' value ({value}) is above the maximum allowed ({max_value})"

            # Append to the list for bulk creation with the original `OptimizationInput` id
            optimization_inputs_to_create.append(
                CalibrationOptimizationInput(
                    optimization_input_id=optimization_input_data['id'],
                    calibration_run=run,
                    value=value
                )
            )

        # Bulk create inputs
        CalibrationOptimizationInput.objects.bulk_create(optimization_inputs_to_create)

    return optimization, None


def validate_objective_function(run, objective_function_name, streamflow_threshold, peak_flow_threshold):
    if objective_function_name:
        # Retrieve the cached metrics
        metrics_cache = get_cached_metrics()

        # Fetch the metric from cache, ensuring it is active
        objective_function = metrics_cache.get(objective_function_name.lower())

        if not objective_function or not objective_function.is_active:
            return f"Invalid metric specified for objective function - '{objective_function_name}'"

        run.objective_function = objective_function

        if objective_function.categorical:
            if not streamflow_threshold:
                return "Streamflow threshold must be specified for a categorical function"
            run.streamflow_threshold = streamflow_threshold

        if objective_function.event_based:
            if not peak_flow_threshold:
                return "Peak flow threshold must be specified for an event-based function"
            run.peak_flow_threshold = peak_flow_threshold

    return None


def write_optimization_inputs(run: CalibrationRun, optimization: Optimization, optimization_inputs: List[Dict[str, Any]]) -> None:
    """
    Writes optimization inputs to the database, removing any existing ones for the calibration run.

    :param run: The CalibrationRun instance.
    :param optimization: The selected Optimization instance.
    :param optimization_inputs: List of inputs with names and values.
    """

    # Delete existing optimization inputs first
    CalibrationOptimizationInput.objects.filter(calibration_run=run).delete()

    if optimization_inputs:
        cached_inputs_list = get_cached_optimization_inputs(optimization.name)
        cached_inputs = {opt['name']: opt for opt in cached_inputs_list}  # Convert to dict

        for o in optimization_inputs:
            optimization_input = cached_inputs.get(o['name'])
            if optimization_input and optimization_input['is_active']:
                CalibrationOptimizationInput.objects.create(
                    optimization_input_id=optimization_input['id'],
                    calibration_run=run,
                    value=o['value']
                )


def get_cached_optimization_inputs(optimization_name: str) -> List[Dict[str, str | int | float]]:
    """
    Retrieves optimization inputs for a given optimization name from the cache or database.

    :param optimization_name: The name of the optimization.
    :return: A list of dictionaries containing optimization input details.
    """
    cache_key = f'optimization_inputs_{optimization_name}'
    optimization_inputs = cache.get(cache_key)

    # If not in cache, query and cache the results
    if optimization_inputs is None:
        optimization_inputs = list(
            OptimizationInput.objects.filter(optimization__name=optimization_name, is_active=True).values(
                'name', 'description', 'data_type', 'default_value', 'min', 'max', 'id', 'is_active'
            )
        )

        # Cache the inputs
        cache.set(cache_key, optimization_inputs, timeout=None)

    return optimization_inputs
