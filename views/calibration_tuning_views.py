import json
import traceback

from django.db import transaction
from django.db.models import F
from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import api_view

from calibration.calibration_validators import CalibrationRunValidator, SaveTuningValidator, ModuleDataCollectionValidator
from calibration.enums import StatusEnum, CalibrationRunType
from calibration.management.commands import ngen_cal_input
from calibration.models import CalibrationRun, CalibrationFormulation, ModuleOutputVariable, Status, \
    CalibrationTuneParameter

# For testing
module_sample_data = {"modules_data": [
    {
        "name": "Noah-OWP-Modular",
        "output_variables": [
            {
                "name": "QINSUR",
                "description": "description of variable",
                "type": "double"
            },
            {
                "name": "ETRAN",
                "description": "description of variable",
                "type": "double"
            },
            {
                "name": "QSEVA",
                "description": "description of variable",
                "type": "double"
            },
        ],
        "parameters": [
            {
                "name": "parameter1",
                "type": "double",
                "initial_value": 0.0,
                "calibratable": True
            },

            {
                "name": "parameter2",
                "type": "double",
                "initial_value": 0.0,
                "calibratable": False
            },
            {
                "name": "parameter3",
                "type": "double",
                "initial_value": 0.0,
                "calibratable": True
            }

        ]
    },
]
}


@api_view(['GET', 'POST'])
# @login_required
def load_tuning_tab(request):
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
        run = CalibrationRun.objects.filter(id=calibration_run_id).select_related('status', 'gage').first()
        if not run:
            return JsonResponse({'message': f'Calibration Run {calibration_run_id} does not exist or is not owned by {request.user}'},
                                status=status.HTTP_400_BAD_REQUEST)
        if run.status.name != StatusEnum.READY and run.status.name != StatusEnum.SAVED:
            return JsonResponse({'message': f'Calibration Run {calibration_run_id} is not saved or ready.  Status: {run.status.name}'},
                                status=status.HTTP_400_BAD_REQUEST)

        automatic_validation = run.run_type == CalibrationRunType.VALID_BEST.value
        print('automatic_validation', automatic_validation)
        validation_times = {}
        calibration_times = {}

        # These are all or nothing.  So if this first one exists, we'll assume they all do
        if run.calibration_start_period:
            calibration_times['simulation_start_time'] = run.calibration_start_period
            calibration_times['simulation_end_time'] = run.calibration_end_period
            calibration_times['calibration_start_time'] = run.calibration_eval_start_period
            calibration_times['calibration_end_time'] = run.calibration_eval_end_period
        if automatic_validation and run.validation_start_period:
            validation_times['simulation_start_time'] = run.validation_start_period
            validation_times['simulation_end_time'] = run.validation_end_period
            validation_times['validation_start_time'] = run.validation_eval_start_period
            validation_times['validation_end_time'] = run.validation_eval_end_period

        output_variable_to_calibrate = {
            'module': run.module_output_variable.calibration_formulation.name,
            'name': run.module_output_variable.name
        } if run.module_output_variable else {}

        # Get the list of modules for this Run
        modules = CalibrationFormulation.objects.filter(calibration_run=run, used_by_calibration_run=True)

        parameter_list = []
        output_variable_list = []
        if modules:
            # Only do this if modules have been saved in the formulation tab

            print('modules', modules)
            if not run.got_module_data_from_hydrofabric:
                print('calling hydrofabric')
                get_module_data_from_hydrofabric(run, modules)

            # For each module, get the Parameters and Output Variables
            for m in modules:
                parameters = list(CalibrationTuneParameter.objects.filter(calibration_formulation=m)
                                  .only('name', 'minimum', 'maximum', 'default_value', 'initial_value', 'data_type', 'calibratable')
                                  .values('name', 'minimum', 'maximum', 'default_value', 'initial_value', 'data_type', 'calibratable',
                                          module=F('calibration_formulation__name')))

                parameter_list.extend(parameters)

                output_variable_entry = {'name': m.name,
                                         'output_variables': list(m.output_variables.all().values('name', 'description', 'data_type'))}
                output_variable_list.append(output_variable_entry)

            if ngen_cal_input.ready_to_run():
                run.status = Status.objects.get(StatusEnum.READY) if ngen_cal_input.ready_to_run() else Status.objects.get(StatusEnum.SAVED)

        return JsonResponse(
            {'calibration_run_id': run.id, 'status': run.status.name, 'parameters': parameter_list, 'module_output_variables': output_variable_list,
             'calibration_times': calibration_times,
             'validation_times': validation_times, 'automatic_validation': automatic_validation,
             'output_variable_to_calibrate': output_variable_to_calibrate}, safe=False)
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"exception": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# @login_required()
def get_module_data_from_hydrofabric(run, modules):
    try:

        # Get this from hydrofabric
        # modules_request = {"modules":modules}
        # response = requests.post(settings.HYDROFABRIC_URL, json=modules_request)
        # module_data = response.json()

        validator = ModuleDataCollectionValidator(data=module_sample_data)
        if not validator.is_valid():
            print(validator.errors)
            raise Exception('Module metadata from Hydrofabric is not in the expected format')

        module_data = module_sample_data.get("modules_data")

        # Save the output variables for each module
        # TODO We need to ensure that the data from Hydrofabric contains all the modules we asked for
        with transaction.atomic():
            for m in module_data:
                print('m', m)
                # Get the modules object from our list
                module = modules.filter(name=m.get('name')).first()
                print('module', module)

                # Save output variables
                outputs = m.get('output_variables')
                # Delete output variables for this module instance
                # ModuleOutputVariable.objects.filter(calibration_formulation=module).delete()
                o: dict
                for o in outputs:
                    print('o', o)
                    ModuleOutputVariable.objects.create(name=o.get('name'), data_type=o.get('type'),
                                                        calibration_formulation=module, description=o.get('description'))
                # Save parameters
                parameters = m.get('parameters')
                print('parameters from Hydro', parameters)
                # Delete parameters for this module instance
                # CalibrationTuneParameter.objects.filter(calibration_formulation=module, calibration_run=run).delete()
                for p in parameters:
                    print('p', p)
                    print('module', module)
                    CalibrationTuneParameter.objects.create(name=p.get('name'), data_type=p.get('type'),
                                                            default_value=p.get('initial_value'),
                                                            calibration_formulation=module,
                                                            calibratable=p.get('calibratable'))  # Do we need description?

            run.got_module_data_from_hydrofabric = True
            run.save()

        return
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"exception": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# TODO Not done yet
@api_view(['POST'])
# @login_required
def save_tuning_tab(request):
    try:
        print('user', request.user)
        body = json.loads(request.body or '{}')
        validate = SaveTuningValidator(data=body)
        validate.is_valid(raise_exception=True)

        calibration_run_id = validate.data.get('calibration_run_id')
        automatic_validation = validate.data.get('automatic_validation')
        calibration_times = validate.data.get('calibration_times')
        validation_times = validate.data.get('validation_times')
        parameters = validate.data.get('parameters')

        print('time', calibration_times)
        print('time', calibration_times.get('calibration_start_time'))
        print('time', type(calibration_times.get('calibration_start_time')))

        # print('validate', validate)
        output_variable_to_calibrate = validate.data.get('output_variable_to_calibrate')

        # print('calibration_run_id', calibration_run_id)
        # print('automatic_validation', automatic_validation)
        # print('calibration_times', calibration_times)
        # print('validation_times', validation_times)
        # print('parameters', parameters)

        # TODO Need to filter jobs by user
        run = CalibrationRun.objects.filter(id=calibration_run_id).select_related('status').first()
        if not run:
            return JsonResponse({'message': f'Calibration Run {calibration_run_id} does not exist or is not owned by {request.user}'},
                                status=status.HTTP_400_BAD_REQUEST)
        if run.status.name != StatusEnum.READY and run.status.name != StatusEnum.SAVED:
            return JsonResponse({'message': f'Calibration Run {calibration_run_id} is not saved or ready.  Status: {run.status.name}'},
                                status=status.HTTP_400_BAD_REQUEST)

        run.calibration_start_period = calibration_times.get('simulation_start_time') if calibration_times else None
        run.calibration_end_period = calibration_times.get('simulation_end_time') if calibration_times else None
        run.calibration_eval_start_period = calibration_times.get('calibration_start_time') if calibration_times else None
        run.calibration_eval_end_period = calibration_times.get('calibration_end_time') if calibration_times else None

        if automatic_validation:
            run.validation_start_period = validation_times.get('simulation_start_time') if validation_times else None
            run.validation_end_period = validation_times.get('simulation_end_time') if validation_times else None
            run.validation_eval_start_period = validation_times.get('validation_start_time') if validation_times else None
            run.validation_eval_end_period = validation_times.get('validation_end_time') if validation_times else None

        # Set the type
        run.run_type = CalibrationRunType.VALID_BEST if automatic_validation else CalibrationRunType.CALIB

        if parameters:
            if not CalibrationTuneParameter.objects.filter(calibration_formulation__calibration_run=run).exists():
                return JsonResponse({'error': 'CalibrationTuneParameters have not been loaded from Hydrofabric'},
                                    status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            # Make sure the parameters we are trying to save exist
            for p in parameters:
                if not CalibrationTuneParameter.objects.filter(name=p.get('name'), calibration_formulation__name=p.get('module')).exists():
                    return JsonResponse({'error': f"Invalid parameter {p.get('name')} specified for module {p.get('module')}"})

        # Validate the output_variable_to_calibrate
        print('output_variable_to_calibrate', output_variable_to_calibrate)
        if output_variable_to_calibrate:
            module_with_output_variable = CalibrationFormulation.objects.filter(name=output_variable_to_calibrate.get('module'),
                                                                                calibration_run=run).first()
            module_output_variable = module_with_output_variable.output_variables.all().filter(
                name=output_variable_to_calibrate.get('name')).first()
            if not module_output_variable:
                return JsonResponse({
                    'error': f"Module output variable '{output_variable_to_calibrate.get('name')}' not found in module '{output_variable_to_calibrate.get('module')}' for this run"},
                    status=status.HTTP_400_BAD_REQUEST)
            print('module_output_variable', module_output_variable)
            run.module_output_variable = module_output_variable

        with transaction.atomic():
            run.save()
            if parameters:
                for p in parameters:
                    (CalibrationTuneParameter.objects
                     .filter(name=p.get('name'), calibration_formulation__name=p.get('module'), calibration_formulation__calibration_run=run)
                     .update(minimum=p.get('min'), maximum=p.get('max'), initial_value=p.get('initial_value')))

        if ngen_cal_input.ready_to_run():
            run.status = Status.objects.get(StatusEnum.READY) if ngen_cal_input.ready_to_run() else Status.objects.get(StatusEnum.SAVED)

        return JsonResponse({'message': f'Calibration Run {run.id} updated', 'calibration_run_key': run.id, 'status': run.status.name})

    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"exception": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
