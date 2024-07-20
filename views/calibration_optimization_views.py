import json
import traceback

from django.db import transaction
from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import api_view

from calibration.calibration_validators import CalibrationRunValidator, SaveOptimizationValidator
from calibration.enums import StatusEnum
from calibration.management.commands import ngen_cal_input
from calibration.models import Optimization, Metric, CalibrationRun, Status, OptimizationInput, CalibrationOptimizationInput, CalibrationStopCriteria


@api_view(['GET', 'POST'])
# @login_required()
def load_optimization_tab(request):
    try:
        print('user', request.user)
        if request.method == 'POST':
            data = json.loads(request.body or '{}')
        else:
            data = request.GET

        validate = CalibrationRunValidator(data=data)
        validate.is_valid(raise_exception=True)

        calibration_run_id = validate.data.get('calibration_run_id')

        # TODO Need to filter jobs by user
        run = CalibrationRun.objects.filter(id=calibration_run_id).select_related('status').first()
        if not run:
            return JsonResponse({'error': f'Calibration Run {calibration_run_id} does not exist or is not owned by {request.user}'},
                                status=status.HTTP_400_BAD_REQUEST)
        if run.status.name != StatusEnum.READY and run.status.name != StatusEnum.SAVED:
            return JsonResponse({'error': f'Calibration Run {calibration_run_id} is not saved or ready.  Status: {run.status.name}'},
                                status=status.HTTP_400_BAD_REQUEST)

        objective_function = run.objective_function.name if run.objective_function else None
        streamflow_threshold = run.streamflow_threshold if (run.objective_function and run.objective_function.categorical) else None
        if run.optimization:
            optimization = run.optimization.name
            optimization_inputs = OptimizationInput.objects.filter(optimization__name=run.optimization.name).values()
        else:
            optimization = None
            optimization_inputs = []

        metrics = Metric.objects.filter(is_active=True).only('name', 'description', 'categorical').values('name', 'description', 'categorical')

        optimizations = Optimization.objects.filter(is_active=True).only('name', 'description')
        optimization_list = []
        for o in optimizations:
            inputs = list(o.inputs.all().values('name', 'description', 'data_type'))
            optimization_list.append({'name': o.name, 'description': o.description, 'inputs': inputs})

        plot_generation_frequency = run.plot_frequency if run.plot_frequency else None

        calibration_stop_criteria = CalibrationStopCriteria.objects.filter(calibration_run=run).first()
        stop_criteria = calibration_stop_criteria.value if calibration_stop_criteria else None

        if ngen_cal_input.ready_to_run():
            run.status = Status.objects.get(StatusEnum.READY) if ngen_cal_input.ready_to_run() else Status.objects.get(StatusEnum.SAVED)

        return JsonResponse(
            {'calibration_run_id': run.id, 'status': run.status.name,
             'streamflow_threshold': streamflow_threshold, 'metrics': list(metrics),
             'optimization': optimization,
             'optimization_inputs': list(optimization_inputs),
             'objective_function': objective_function,
             'optimizations': optimization_list,
             'plot_generation_frequency': plot_generation_frequency,
             'stop_criteria': stop_criteria
             },
            safe=False)
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"exception": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# noinspection PyUnusedLocal


@api_view(['POST'])
# @login_required
def save_optimization_tab(request):
    try:
        print('user', request.user)
        body = json.loads(request.body or '{}')
        validate = SaveOptimizationValidator(data=body)
        validate.is_valid(raise_exception=True)

        calibration_run_id = validate.data.get('calibration_run_id')
        optimization_name = validate.data.get('optimization')
        objective_function_name = validate.data.get('objective_function')
        streamflow_threshold = validate.data.get('streamflow_threshold')
        optimization_inputs = validate.data.get('optimization_inputs')
        stop_criteria = validate.data.get('stop_criteria')
        plot_generation_frequency = validate.data.get('plot_generation_frequency')

        # TODO Need to filter jobs by user
        run = CalibrationRun.objects.filter(id=calibration_run_id).select_related('status').first()
        if not run:
            return JsonResponse({'error': f'Calibration Run {calibration_run_id} does not exist or is not owned by {request.user}'},
                                status=status.HTTP_400_BAD_REQUEST)
        if run.status.name != StatusEnum.READY and run.status.name != StatusEnum.SAVED:
            return JsonResponse({'error': f'Calibration Run {calibration_run_id} is not saved or ready.  Status: {run.status.name}'},
                                status=status.HTTP_400_BAD_REQUEST)

        if optimization_inputs and not optimization_name:
            return JsonResponse({'error': 'Optimization inputs cannot be specified without an optimization name'},
                                status=status.HTTP_400_BAD_REQUEST)

        optimization = Optimization.objects.filter(name=optimization_name).first() if optimization_name else None
        if not optimization:
            return JsonResponse({'error': f"Invalid optimization - '{optimization_name}'"})
        run.optimization = optimization

        if optimization_inputs:
            # Check if  parameter is valid for this optimization
            valid_optimization_inputs = OptimizationInput.objects.filter(optimization=optimization).only('name').values_list('name', flat=True)
            for o in optimization_inputs:
                if o not in valid_optimization_inputs:
                    name = o.get('name')
                    return JsonResponse({'error': f"'{name}' is not a valid parameter input for '{optimization_name}'"})
                CalibrationOptimizationInput.objects.create(value=o.get('value'), optimization=optimization, calibration_run=run)

        if objective_function_name:
            objective_function = Metric.objects.filter(name=objective_function_name).first()
            if not objective_function:
                return JsonResponse({'error': f"Invalid metric specified for objective function - '{objective_function_name}'"})

            run.objective_function = objective_function

            if objective_function.categorical:
                if not streamflow_threshold:
                    return JsonResponse({'error': f"Streamflow threshold must be specified for a categorical function'"})
                run.streamflow_threshold = streamflow_threshold

        run.plot_frequency = plot_generation_frequency

        CalibrationStopCriteria.objects.update_or_create(calibration_run=run, defaults={"value": stop_criteria, "ordinal": 0})

        with transaction.atomic():
            # Delete existing optimization inputs
            CalibrationOptimizationInput.objects.filter(calibration_run=run).delete()
            if optimization_inputs:
                for o in optimization_inputs:
                    CalibrationOptimizationInput.objects.create(value=o.get('value'), optimization=optimization, calibration_run=run)

            run.save()

            if ngen_cal_input.ready_to_run():
                run.status = Status.objects.get(StatusEnum.READY) if ngen_cal_input.ready_to_run() else Status.objects.get(StatusEnum.SAVED)

            return JsonResponse({'message': f'Calibration Run {run.id} updated', 'calibration_run_key': run.id, 'status': run.status.name})
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"exception": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
