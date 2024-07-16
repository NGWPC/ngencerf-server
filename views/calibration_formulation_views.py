import json
import traceback

from django.db import transaction
from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import api_view

from calibration.calibration_validators import SaveFormulationValidator, CalibrationRunValidator, ModuleCollectionValidator
from calibration.enums import StatusEnum
from calibration.management.commands import ngen_cal_input
from calibration.models import NgenCalFormulation, CalibrationRun, CalibrationFormulation, CalibrationSlothParam, \
    Status

# For testing
module_sample_data = {"modules_data": [
    {
        "name": "GC2D",
        "description": "description of module",
        "groups": [
            "Glacier"
        ]
    },
    {
        "name": "Noah-OWP-Modular",
        "description": "description of module",
        "groups": [
            "Snowmelt",
            "Evapotranspiration"
        ],
    },
    {
        "name": "Snow-17",
        "description": "description of module",
        "groups": [
            "Snowmelt"
        ]
    },
    {
        "name": "UEB",
        "description": "description of module",
        "groups": [
            "Snowmelt",
            "Evapotranspiration"
        ]
    },
    {
        "name": "CFE-S",
        "description": "description of module",
        "groups": [
            "Rainfall Runoff"
        ],
    },
    {
        "name": "CFE-X",
        "description": "description of module",
        "groups": [
            "Rainfall Runoff"
        ],
    },
    {
        "name": "PET",
        "description": "description of module",
        "groups": [
            "Evapotranspiration"
        ]
    },
    {
        "name": "TopModel",
        "description": "description of module",
        "groups": [
            "Rainfall Runoff"
        ]
    },
    {
        "name": "Sac-SMA",
        "description": "description of module",
        "groups": [
            "Rainfall Runoff"
        ]
    },
    {
        "name": "LASAM",
        "description": "description of module",
        "groups": [
            "Rainfall Runoff"
        ]
    },
    {
        "name": "SMP",
        "description": "description of module",
        "groups": [
            "Soil Moisture"
        ]
    },
    {
        "name": "SFT",
        "description": "description of module",
        "groups": [
            "Snowmelt"
        ]
    },
    {
        "name": "T-Route",
        "description": "description of module",
        "groups": [
            "Routing"
        ],
    },
    {
        "name": "SCHISM",
        "description": "description of module",
        "groups": [
            "Coastal"
        ]
    },
    {
        "name": "SFINCS",
        "description": "description of module",
        "groups": [
            "Coastal"
        ]
    },
    {
        "name": "Sloth",
        "description": "description of module",
        "groups": [
            "Inject"
        ]
    }
]
}


@api_view(['GET', 'POST'])
@transaction.atomic
# @login_required()
def get_modules(request):
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
            run = CalibrationRun.objects.filter(id=calibration_run_id).select_related('status').first()

            if not run:
                return JsonResponse({'message': f'Calibration Run {calibration_run_id} does not exist or is not owned by {request.user}'},
                                    status=status.HTTP_400_BAD_REQUEST)
            if run.status != StatusEnum.READY and run.status != StatusEnum.SAVED:
                return JsonResponse({'message': f'Calibration Run {calibration_run_id} is not saved or ready.  Status: {run.status.name}'},
                                    status=status.HTTP_400_BAD_REQUEST)

            # Get this from hydrofabric
            # modules_request = {}
            # response = requests.post(settings.HYDROFABRIC_URL, json=modules_request)
            # module_data = response.json()

            # TODO Need to update this validator.  Not the same one as get_module_data
            validator = ModuleCollectionValidator(data=module_sample_data)
            if not validator.is_valid():
                print(validator.errors)
                raise Exception('Module data from Hydrofabric is not in the expected format')

            module_data = module_sample_data.get("modules_data")

            # Delete modules for this run, if they've already been specified
            CalibrationFormulation.objects.filter(calibration_run=run).delete()
            # Save the modules
            for m in module_data:
                module = CalibrationFormulation.objects.create(name=m.get('name'), groups=json.dumps(m.get('groups')),
                                                               calibration_run=run,
                                                               description=m.get('description'))
                # outputs = m.get('output_variables')
                # # Delete output variables for this module instance
                # ModuleOutputVariable.objects.filter(calibration_formulation=module).delete()
                # if outputs:
                #     o: dict
                #     for o in outputs:
                #         ModuleOutputVariable.objects.create(name=o.get('name'), data_type=o.get('type'),
                #                                             calibration_formulation=module, description=o.get('description'))

            return JsonResponse(module_data, safe=False)
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"exception": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
# @login_required
@transaction.atomic
def save_formulation_tab(request):
    try:
        print('user', request.user)
        body = json.loads(request.body or '{}')
        validate = SaveFormulationValidator(data=body)
        validate.is_valid(raise_exception=True)

        modules = set(validate.data.get('modules'))
        calibration_run_id = validate.data.get('calibration_run_id')
        formulation_name = validate.data.get('formulation_name')
        sloth_parameters = validate.data.get('sloth_parameters')

        # Make sure the formulation is valid
        valid_formulations = NgenCalFormulation.objects.all().values_list('modules', flat=True)
        valid = False
        for valid_formulation in valid_formulations:
            valid_module_set = set(json.loads(valid_formulation))
            if valid_module_set == modules:
                valid = True
                break
        if not valid:
            return JsonResponse({"error": f"Invalid formulation - {modules}"})

        with transaction.atomic():
            # TODO Do we want to create a Calibration_Run if the key is not given?
            # TODO Need to filter jobs by user
            run = CalibrationRun.objects.filter(id=calibration_run_id).select_related('status').first()
            if not run:
                return JsonResponse({'message': f'Calibration Run {calibration_run_id} does not exist or is not owned by {request.user}'}, status=status.HTTP_400_BAD_REQUEST)
            if run.status != StatusEnum.READY and run.status != StatusEnum.SAVED:
                return JsonResponse({'message': f'Calibration Run {calibration_run_id} is not saved or ready.  Status: {run.status.name}'}, status=status.HTTP_400_BAD_REQUEST)

            run.formulation_name = formulation_name

            # Indicate that the modules are now in use
            for name in modules:
                # Find the modules for this run
                count = CalibrationFormulation.objects.filter(name=name, calibration_run_id=run.id).update(used_by_calibration_run=True)
                if count == 0:
                    # This means that get_modules was not called to add the modules for this run
                    raise Exception(f"Cannot find module '{name}' associated with Calibration Run {calibration_run_id}")

            # Delete params for this run if they've already been specified
            CalibrationSlothParam.objects.filter(calibration_run=run).delete()
            for s in sloth_parameters:
                # Need to also set the module
                module = CalibrationFormulation.objects.filter(name=s.get('module'), calibration_run_id=run.id).first()
                if not module:
                    error = f"Sloth parameters contain an invalid module - \'{s.get('module')}\'.  This module has not been added to this run"
                    print(error)
                    return JsonResponse({"error": error})
                CalibrationSlothParam.objects.create(calibration_run=run, param_name=s.get('name'), param_count=s.get('count'),
                                                     param_type=s.get('type'),
                                                     param_units=s.get('units'), param_location=s.get('location'),
                                                     param_value=s.get('value'), maps_to_module=module,
                                                     maps_to_variable_name=s.get('module_param'))
                
            if ngen_cal_input.ready_to_run():
                run.status = Status.objects.get(StatusEnum.READY) if ngen_cal_input.ready_to_run() else Status.objects.get(StatusEnum.SAVED)
            run.save()

            return JsonResponse({'message': f'Calibration Run {run.id} updated', 'calibration_run_key': run.id, 'status': run.status.name})
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"exception": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
