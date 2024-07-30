import json
import logging
from json.decoder import JSONDecodeError

from django.db import transaction
from django.http import JsonResponse
from rest_framework import serializers
from rest_framework.decorators import api_view

from calibration.calibration_validators import CalibrationRunValidator, SaveOptimizationValidator
from calibration.management.commands import ngen_cal_input
from calibration.models import Optimization, Metric, OptimizationInput, CalibrationOptimizationInput, CalibrationStopCriteria
from views.common import get_run, JsonException, JsonError, JsonValidationError

logger = logging.getLogger(__name__)


@api_view(['GET', 'POST'])
# @login_required()
def load_optimization_tab(request):
    try:
        print('user', request.user)
        if request.method == 'POST':
            data = json.loads(request.body or '{}')
        else:
            data = request.GET

        logger.debug(f'load_optimization_tab() request from {request.user} - {data}')

        validate = CalibrationRunValidator(data=data)
        validate.is_valid(raise_exception=True)

        calibration_run_id = validate.data.get('calibration_run_id')

        run, errorReturn = get_run(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn

        objective_function = run.objective_function.name if run.objective_function else None
        streamflow_threshold = run.streamflow_threshold if (run.objective_function and run.objective_function.categorical) else None
        if run.optimization:
            optimization = run.optimization.name
            optimization_inputs = OptimizationInput.objects.filter(optimization__name=run.optimization.name, is_active=True).values('name',
                                                                                                                                    'data_type',                                                                                                                    'description')
        else:
            optimization = None
            optimization_inputs = []

        metrics = Metric.objects.filter(is_active=True).only('name', 'description', 'is_active', 'categorical').values('name', 'description', 'is_active', 'categorical')

        optimizations = Optimization.objects.filter(is_active=True).only('name', 'description', 'is_active')
        optimization_list = []
        for o in optimizations:
            inputs = list(o.inputs.all().values('name', 'description', 'data_type', 'is_active'))
            optimization_list.append({'name': o.name, 'description': o.description, 'is_active': o.is_active, 'inputs': inputs})

        plot_generation_frequency = run.plot_frequency if run.plot_frequency else None

        calibration_stop_criteria = CalibrationStopCriteria.objects.filter(calibration_run=run).first()
        stop_criteria = calibration_stop_criteria.value if calibration_stop_criteria else None

        ngen_cal_input.ready_to_run(run=run)

        response = {'calibration_run_id': run.id, 'status': run.status.name,
                    'streamflow_threshold': streamflow_threshold, 'metrics': list(metrics),
                    'optimization': optimization,
                    'optimization_inputs': list(optimization_inputs),
                    'objective_function': objective_function,
                    'optimizations': optimization_list,
                    'plot_generation_frequency': plot_generation_frequency,
                    'stop_criteria': stop_criteria
                    }
        logger.debug(f'Returning to {request.user} from load_optimization_tab() - {response}')

        return JsonResponse(response, safe=False)
    except (serializers.ValidationError, JSONDecodeError) as v:
        return JsonValidationError(v)
    except Exception as e:
        return JsonException(e)


# noinspection PyUnusedLocal


@api_view(['POST'])
# @login_required
def save_optimization_tab(request):
    try:
        print('user', request.user)
        body = json.loads(request.body or '{}')
        logger.debug(f'save_optimization_tab() request from {request.user} - {body}')

        validate = SaveOptimizationValidator(data=body)
        validate.is_valid(raise_exception=True)

        calibration_run_id = validate.data.get('calibration_run_id')
        optimization_name = validate.data.get('optimization')
        objective_function_name = validate.data.get('objective_function')
        streamflow_threshold = validate.data.get('streamflow_threshold')
        optimization_inputs = validate.data.get('optimization_inputs')
        stop_criteria = validate.data.get('stop_criteria')
        plot_generation_frequency = validate.data.get('plot_generation_frequency')

        run, errorReturn = get_run(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn

        if optimization_inputs and not optimization_name:
            return JsonError('Optimization inputs cannot be specified without an optimization name')

        optimization = Optimization.objects.filter(name=optimization_name, is_active=True).first() if optimization_name else None
        if not optimization:
            return JsonError("Invalid optimization - '{}'".format(optimization_name))
        run.optimization = optimization

        if optimization_inputs:
            for o in optimization_inputs:
                name = o.get('name')
                # See if parameter is valid for this optimization
                optimization_input = OptimizationInput.objects.filter(optimization=optimization, name=name, is_active=True).first()
                if not optimization_input:
                    return JsonError("'{}' is not a valid parameter input for '{}'".format(name, optimization_name))

        if objective_function_name:
            objective_function = Metric.objects.filter(name=objective_function_name, is_active=True).first()
            if not objective_function:
                return JsonError("Invalid metric specified for objective function - '{}'".format(objective_function_name))

            run.objective_function = objective_function

            if objective_function.categorical:
                if not streamflow_threshold:
                    return JsonError("Streamflow threshold must be specified for a categorical function'")
                run.streamflow_threshold = streamflow_threshold

        run.plot_frequency = plot_generation_frequency

        with transaction.atomic():
            # I'm assuming for now that there is just one CalibrationStopCriteria for this run, but that might change in the future
            CalibrationStopCriteria.objects.update_or_create(calibration_run=run, defaults={"value": stop_criteria})

            # Delete existing optimization inputs
            CalibrationOptimizationInput.objects.filter(calibration_run=run).delete()
            if optimization_inputs:
                for o in optimization_inputs:
                    optimization_input = OptimizationInput.objects.filter(optimization=optimization, name=o.get('name'), is_active=True).first()
                    CalibrationOptimizationInput.objects.create(optimization_input=optimization_input, calibration_run=run, value=o.get('value'))

            run.save()

            ngen_cal_input.ready_to_run(run=run)

            response = {'message': f'Calibration Run {run.id} updated', 'calibration_run_key': run.id, 'status': run.status.name}
            logger.debug(f'Returning to {request.user} from save_optimization_tab() - {response}')
            return JsonResponse(response)
    except (serializers.ValidationError, JSONDecodeError) as v:
        return JsonValidationError(v)
    except Exception as e:
        return JsonException(e)
