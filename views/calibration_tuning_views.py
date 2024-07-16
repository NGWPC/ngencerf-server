import json
import traceback

from django.db import transaction
from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import api_view

from calibration.calibration_validators import CalibrationRunValidator, ModuleCollectionValidator, SaveTuningValidator
from calibration.enums import StatusEnum
from calibration.models import CalibrationRun, CalibrationFormulation, ModuleOutputVariable, CalibrationInitialParameter

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
                "initial_value": 0.0
            },

            {
                "name": "parameter2",
                "type": "double",
                "initial_value": 0.0
            },
            {
                "name": "parameter3",
                "type": "double",
                "initial_value": 0.0
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
            data = json.loads(request.body)
        else:
            data = request.GET

        validate = CalibrationRunValidator(data=data or {})
        validate.is_valid(raise_exception=True)

        calibration_run_id = validate.data.get('calibration_run_id')

        with transaction.atomic():
            # Do we want only SAVED?  Want to make sure it hasn't been run yet
            # Or do we want anything that's not RUNNING?
            run = CalibrationRun.objects.filter(id=calibration_run_id, status__name=StatusEnum.SAVED).first()
            if not run:
                return JsonResponse(
                    {'message': f'Calibration Run {calibration_run_id} does not exist, is already running or is not owned by {request.user}'})

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

            validator = ModuleCollectionValidator(data=module_sample_data)
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
                                                               calibration_formulation=module)  # Do we need description?

            return JsonResponse(module_data, safe=False)
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"exception": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
# @login_required
@transaction.atomic
def save_tuning_tab(request):
    try:
        print('user', request.user)
        body = json.loads(request.body)
        validate = SaveTuningValidator(data=body or {})
        validate.is_valid(raise_exception=True)

        modules = set(body.get('modules'))
        calibration_run_id = body.get('calibration_run_id')
        formulation_name = body.get('formulation_name')
        sloth_parameters = body.get('sloth_parameters')

        with transaction.atomic():
            # TODO Do we want to create a Calibration_Run if the key is not given?
            # TODO Need to filter jobs by user
            run = CalibrationRun.objects.filter(id=calibration_run_id).select_related('status').first()
            if not run:
                return JsonResponse({'message': f'Calibration Run {calibration_run_id} does not exist or is not owned by {request.user}'})
            if run.status != StatusEnum.READY and run.status != StatusEnum.SAVED:
                return JsonResponse({'message': f'Calibration Run {calibration_run_id} is not saved or ready.  Status: {run.status.name}'})


    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"exception": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
