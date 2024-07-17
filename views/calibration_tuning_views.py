import json
import traceback

from django.db import transaction
from django.forms import model_to_dict
from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import api_view

from calibration.calibration_validators import CalibrationRunValidator, SaveTuningValidator, ModuleDataCollectionValidator
from calibration.enums import StatusEnum, CalibrationRunType
from calibration.models import CalibrationRun, CalibrationFormulation, ModuleOutputVariable, CalibrationInitialParameter, ValidationRun, Status, \
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
@transaction.atomic
# @login_required()
def get_module_data(request):
    try:
        print('user', request.user)
        if request.method == 'POST':
            data = json.loads(request.body or '{}')
        else:
            data = request.GET

        validate = CalibrationRunValidator(data=data)
        validate.is_valid(raise_exception=True)

        calibration_run_id = validate.data.get('calibration_run_id')

        with transaction.atomic():
            run = CalibrationRun.objects.filter(id=calibration_run_id).select_related('status').first()
            if not run:
                return JsonResponse({'message': f'Calibration Run {calibration_run_id} does not exist or is not owned by {request.user}'},
                                    status=status.HTTP_400_BAD_REQUEST)
            if run.status.name != StatusEnum.READY and run.status.name != StatusEnum.SAVED:
                return JsonResponse({'message': f'Calibration Run {calibration_run_id} is not saved or ready.  Status: {run.status.name}'},
                                    status=status.HTTP_400_BAD_REQUEST)

            # Get the list of modules for this Run
            modules = CalibrationFormulation.objects.filter(calibration_run=run, used_by_calibration_run=True)
            if not modules:
                # This means that save_formulation_tab was not called to add the modules for this run
                raise Exception(f"There are no modules yet associated with with Calibration Run {calibration_run_id}")
            print('modules', modules)

            # Get this from hydrofabric
            # modules_request = {"modules":modules}
            # response = requests.post(settings.HYDROFABRIC_URL, json=modules_request)
            # module_data = response.json()

            validator = ModuleDataCollectionValidator(data=module_sample_data)
            if not validator.is_valid():
                print(validator.errors)
                raise Exception('Module data from Hydrofabric is not in the expected format')

            module_data = module_sample_data.get("modules_data")

            # Save the output variables for each module
            # TODO We need to ensure that the data from Hydrofabric contains all the modules we asked for
            for m in module_data:
                print('m', m)
                # Get the modules object from our list
                module = modules.filter(name=m.get('name')).first()
                print('module', module)

                # Save output variables
                outputs = m.get('output_variables')
                # Delete output variables for this module instance
                ModuleOutputVariable.objects.filter(calibration_formulation=module).delete()
                o: dict
                for o in outputs:
                    print('o', o)
                    ModuleOutputVariable.objects.create(name=o.get('name'), data_type=o.get('type'),
                                                        calibration_formulation=module, description=o.get('description'))
                # Save parameters
                parameters = m.get('parameters')
                print('parameters', parameters)
                # Delete parameters for this module instance
                CalibrationInitialParameter.objects.filter(calibration_formulation=module, calibration_run=run).delete()
                for p in parameters:
                    print('p', p)
                    CalibrationInitialParameter.objects.create(name=p.get('name'), data_type=p.get('type'), default_value=p.get('initial_value'),
                                                               calibration_run=run,
                                                               calibratable=p.get('calibratable'),
                                                               calibration_formulation=module)  # Do we need description?

            return JsonResponse(module_data, safe=False)
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"exception": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# TODO Not done yet
@api_view(['POST'])
# @login_required
@transaction.atomic
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

        print('calibration_run_id', calibration_run_id)
        print('automatic_validation', automatic_validation)
        print('calibration_times', calibration_times)
        print('validation_times', validation_times)
        print('parameters', parameters)

        with transaction.atomic():
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
                # TODO Need to set the owner
                ValidationRun.objects.create(validation_start_period=validation_times.get('simulation_start_time'),
                                             validation_end_period=validation_times.get('simulation_end_time'),
                                             validation_eval_start_period=validation_times.get('validation_start_time'),
                                             validation_eval_end_period=validation_times.get('validation_end_time'),
                                             is_active=True,
                                             calibration_run=run,
                                             calibration_run_pk_tune_parameters=run,
                                             status=Status.objects.get(name=StatusEnum.SAVED.value))

            # Set the type
            run.run_type = CalibrationRunType.VALID_BEST if automatic_validation else CalibrationRunType.CALIB
            run.save()

            for p in parameters:
                # Delete any previous TuneParameters for this run
                CalibrationTuneParameter.objects.filter(calibration_initial_parameter__calibration_run=run).delete()
                param = CalibrationInitialParameter.objects.filter(name=p.get('name'), calibration_run=run,
                                                                   calibration_formulation__name=p.get('module')).first()
                CalibrationTuneParameter.objects.create(minimum=p.get('min'), maximum=p.get('max'), initial=p.get('initial'),
                                                        calibration_initial_parameter=param)

            # TODO Do we need to return validation key?
            return JsonResponse({'message': f'Calibration Run {run.id} updated', 'calibration_run_key': run.id, 'status': run.status.name})

    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"exception": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
