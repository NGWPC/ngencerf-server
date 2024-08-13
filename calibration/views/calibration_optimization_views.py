import json
import logging
from json.decoder import JSONDecodeError

from django.db import transaction
from django.db.models import F
from drf_spectacular.utils import extend_schema, OpenApiParameter, PolymorphicProxySerializer
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from calibration.models import Optimization, Metric, OptimizationInput, CalibrationOptimizationInput, CalibrationStopCriteria
from calibration.util.calibration_validators import CalibrationRunValidator, LoadOptimizationResponseSerializer, \
    SaveOptimizationRequestValidator, SaveOptimizationResponseSerializer, ErrorResponseSerializer, ExceptionResponseSerializer, \
    ValidationErrorSerializer, ValidationExceptionSerializer
from calibration.views import ngen_cal_input
from calibration.views.common import get_run, ResponseError

logger = logging.getLogger(__name__)


@extend_schema(
    request=CalibrationRunValidator,
    responses={
        200: LoadOptimizationResponseSerializer,
        400: PolymorphicProxySerializer(
            component_name='MultipleErrorResponse',
            serializers=[
                ValidationExceptionSerializer,
                ValidationErrorSerializer,
                ErrorResponseSerializer,
            ],
            resource_type_field_name=None
        ),
        500: ExceptionResponseSerializer
    },
    parameters=[
        OpenApiParameter(name='calibration_run_id', description='ID of the calibration run', required=True, type=int)
    ],
    description="Load optimization tab data"
)
@api_view(['GET', 'POST'])
# @permission_classes([AllowAny])()
def load_optimization_tab(request):
    try:
        print('user', request.user)
        if request.method == 'POST':
            data = json.loads(request.body or '{}')
        else:
            data = request.GET

        logger.debug(f'load_optimization_tab() request from {request.user} - {data}')

        validator = CalibrationRunValidator(data=data)
        validator.is_valid(raise_exception=True)

        calibration_run_id = validator.data.get('calibration_run_id')

        run, errorReturn = get_run(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn

        objective_function = run.objective_function.name if run.objective_function else None
        streamflow_threshold = run.streamflow_threshold if (run.objective_function and run.objective_function.categorical) else None
        peak_flow_threshold = run.peak_flow_threshold if (run.objective_function and run.objective_function.event_based) else None
        optimization, optimization_inputs = get_user_optimization(run)

        metrics = get_metrics()

        optimization_list = get_static_optimizations()

        plot_generation_frequency = run.plot_frequency if run.plot_frequency else None

        calibration_stop_criteria = CalibrationStopCriteria.objects.filter(calibration_run=run).first()
        stop_criteria = calibration_stop_criteria.value if calibration_stop_criteria else None

        ngen_cal_input.ready_to_run(run)
        response = {'calibration_run_id': run.id, 'status': run.status.name,
                    'streamflow_threshold': streamflow_threshold,
                    'peak_flow_threshold': peak_flow_threshold,
                    'metrics': metrics,
                    'optimization': optimization,
                    'optimization_inputs': optimization_inputs,
                    'objective_function': objective_function,
                    'optimizations': optimization_list,
                    'plot_generation_frequency': plot_generation_frequency,
                    'stop_criteria': stop_criteria
                    }

        response = {key: value for key, value in response.items() if value not in [None, '', [], {}]}

        serializer = LoadOptimizationResponseSerializer(data=response)
        if not serializer.is_valid():
            return ResponseError(f'Data format error returning from load_optimization_tab() - {serializer.errors}',
                                 httpStatus=status.HTTP_500_INTERNAL_SERVER_ERROR)
        logger.debug(f'Returning to {request.user} from load_optimization_tab() - {serializer.data}')

        return Response(serializer.data)
    except JSONDecodeError as e:
        response = {'validation_error': 'JSON parsing error - ' + str(e)}
        serializer = ValidationErrorSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)
    except ValidationError as e:
        response = {'validation_error': str(e)}
        serializer = ValidationExceptionSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        response = {'exception': str(e)}
        serializer = ExceptionResponseSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def get_user_optimization(run):
    if run.optimization:
        optimization = run.optimization.name
        optimization_inputs = list(
            CalibrationOptimizationInput.objects.filter(calibration_run=run).select_related('optimization_input')
            .only('optimization_input__name', 'value')
            .values('value', name=F('optimization_input__name')))
    else:
        optimization = None
        optimization_inputs = []

    return optimization, optimization_inputs


def get_static_optimizations():
    optimizations = Optimization.objects.filter(is_active=True).only('name', 'description', 'is_active')
    optimization_list = []
    for o in optimizations:
        inputs = list(o.inputs.all().values('name', 'description', 'data_type', 'is_active'))
        optimization_list.append({'name': o.name, 'description': o.description, 'is_active': o.is_active, 'inputs': inputs})
    return optimization_list


def get_metrics():
    return list(Metric.objects.filter(is_active=True).only('name', 'description', 'is_active', 'categorical', 'event_based')
                .values('name', 'description', 'is_active', 'categorical', 'event_based'))


# noinspection PyUnusedLocal
@extend_schema(
    request=SaveOptimizationRequestValidator,
    responses={
        200: SaveOptimizationResponseSerializer,
        400: PolymorphicProxySerializer(
            component_name='MultipleErrorResponse',
            serializers=[
                ValidationExceptionSerializer,
                ValidationErrorSerializer,
                ErrorResponseSerializer,
            ],
            resource_type_field_name=None
        ),
        500: ExceptionResponseSerializer
    },
    description="Save optimization tab data"
)
@api_view(['POST'])
# @permission_classes([AllowAny])
def save_optimization_tab(request):
    try:
        print('user', request.user)
        body = json.loads(request.body or '{}')
        logger.debug(f'save_optimization_tab() request from {request.user} - {body}')

        validator = SaveOptimizationRequestValidator(data=body)
        validator.is_valid(raise_exception=True)

        calibration_run_id = validator.data.get('calibration_run_id')
        optimization_name = validator.data.get('optimization')
        objective_function_name = validator.data.get('objective_function')
        streamflow_threshold = validator.data.get('streamflow_threshold')
        peak_flow_threshold = validator.data.get('peak_flow_threshold')
        optimization_inputs = validator.data.get('optimization_inputs')
        stop_criteria = validator.data.get('stop_criteria')
        plot_generation_frequency = validator.data.get('plot_generation_frequency')

        run, errorReturn = get_run(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn

        if optimization_inputs and not optimization_name:
            return ResponseError('Optimization inputs cannot be specified without an optimization name')

        optimization, message = validate_optimizations(run, optimization_name, optimization_inputs)
        if message:
            return ResponseError(message)

        message = validate_objective_function(run, objective_function_name, streamflow_threshold, peak_flow_threshold)
        if message:
            return ResponseError(message)

        run.plot_frequency = plot_generation_frequency
        run.streamflow_threshold = streamflow_threshold
        run.peak_flow_threshold = peak_flow_threshold

        with transaction.atomic():
            # I'm assuming for now that there is just one CalibrationStopCriteria for this run, but that might change in the future
            CalibrationStopCriteria.objects.update_or_create(calibration_run=run, defaults={"value": stop_criteria})

            write_optimization_inputs(run, optimization, optimization_inputs)

            run.save()

            ngen_cal_input.ready_to_run(run)

            response = {'message': f'Calibration Run {run.id} updated', 'calibration_run_id': run.id, 'status': run.status.name}
            serializer = SaveOptimizationResponseSerializer(data=response)
            if not serializer.is_valid():
                return ResponseError(f'Data format error returning from save_optimization_tab() - {serializer.errors}',
                                     httpStatus=status.HTTP_500_INTERNAL_SERVER_ERROR)
            logger.debug(f'Returning to {request.user} from save_optimization_tab() - {serializer.data}')
            return Response(serializer.data)
    except JSONDecodeError as e:
        response = {'validation_error': 'JSON parsing error - ' + str(e)}
        serializer = ValidationErrorSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)
    except ValidationError as e:
        response = {'validation_error': str(e)}
        serializer = ValidationExceptionSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        response = {'exception': str(e)}
        serializer = ExceptionResponseSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def validate_optimizations(run, optimization_name, optimization_inputs):
    optimization = Optimization.objects.filter(name=optimization_name, is_active=True).first() if optimization_name else None
    if not optimization:
        return None, "Invalid optimization - '{}'".format(optimization_name)
    run.optimization = optimization

    if optimization_inputs:
        for o in optimization_inputs:
            name = o['name']
            # See if parameter is valid for this optimization
            optimization_input = OptimizationInput.objects.filter(optimization=optimization, name=name, is_active=True).first()
            if not optimization_input:
                return None, "'{}' is not a valid parameter input for '{}'".format(name, optimization_name)
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
            optimization_input = OptimizationInput.objects.filter(optimization=optimization, name=o['name'], is_active=True).first()
            CalibrationOptimizationInput.objects.create(optimization_input=optimization_input, calibration_run=run, value=o['value'])
