import json
import traceback

from django.db import transaction
from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import api_view

from .calibration_validators import SaveFormulationValidator, CalibrationRunValidator
from .models import NgenCalFormulation, CalibrationRun, CalibrationFormulation, CalibrationSlothParam, StatusEnum, Status

# For testing
module_data = [
    {
        "name": "GC2D",
        "groups": [
            "Glacier"
        ]
    },
    {
        "name": "Noah-OWP-Modular",
        "groups": [
            "Snowmelt",
            "Evapotranspiration"
        ]
    },
    {
        "name": "Snow-17",
        "groups": [
            "Snowmelt"
        ]
    },
    {
        "name": "UEB",
        "groups": [
            "Snowmelt",
            "Evapotranspiration"
        ]
    },
    {
        "name": "CFE-S",
        "groups": [
            "Rainfall Runoff"
        ]
    },
    {
        "name": "CFE-X",
        "groups": [
            "Rainfall Runoff"
        ]
    },
    {
        "name": "PET",
        "groups": [
            "Evapotranspiration"
        ]
    },
    {
        "name": "TopModel",
        "groups": [
            "Rainfall Runoff"
        ]
    },
    {
        "name": "Sac-SMA",
        "groups": [
            "Rainfall Runoff"
        ]
    },
    {
        "name": "LASAM",
        "groups": [
            "Rainfall Runoff"
        ]
    },
    {
        "name": "SMP",
        "groups": [
            "Soil Moisture"
        ]
    },
    {
        "name": "SFT",
        "groups": [
            "Snowmelt"
        ]
    },
    {
        "name": "T-Route",
        "groups": [
            "Routing"
        ]
    },
    {
        "name": "SCHISM",
        "groups": [
            "Coastal"
        ]
    },
    {
        "name": "SFINCS",
        "groups": [
            "Coastal"
        ]
    },
    {
        "name": "Sloth",
        "groups": [
            "Inject"
        ]
    }
]


@api_view(['GET', 'POST'])
@transaction.atomic
# @login_required()
def get_modules(request, calibration_run_id=None):
    try:
        print('user', request.user)
        if request.method == "POST":
            body = json.loads(request.body)
            validate = CalibrationRunValidator(data=body or {})
            if not validate.is_valid():
                print('Validation errors', validate.errors)
                return JsonResponse({"errors": validate.errors})
            else:
                calibration_run_id = body.get('calibration_run_id')

        with transaction.atomic():
            # Do we want only SAVED?  Want to make sure it hasn't been run yet
            run = CalibrationRun.objects.filter(id=calibration_run_id, status=Status.objects.get(name=StatusEnum.SAVED.value)).first()
            if not run:
                return JsonResponse({'message': f'Calibration Run {calibration_run_id} does not exist or has already run'})

            # Get this from hydrofabric

            # Delete modules for this run, if they've already been specified
            CalibrationFormulation.objects.filter(calibration_run=run).delete()
            # Save the modules
            for m in module_data:
                CalibrationFormulation.objects.create(name=m.get('name'), groups=json.dumps(m.get('groups')), calibration_run=run,
                                                      description="need description")

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
        body = json.loads(request.body)
        validate = SaveFormulationValidator(data=body or {})
        if not validate.is_valid():
            print('Validation errors', validate.errors)
            return JsonResponse({"errors": validate.errors})
        modules = set(body.get('modules'))
        calibration_run_id = body.get('calibration_run_id')
        formulation_name = body.get('formulation_name')
        sloth_parameters = body.get('sloth_parameters')

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
            # Do we want only SAVED?  Want to make sure it hasn't been run yet
            run = CalibrationRun.objects.filter(id=calibration_run_id, status=Status.objects.get(name=StatusEnum.SAVED.value)).first()
            if not run:
                return JsonResponse({'message': f'Calibration Run {calibration_run_id} does not exist or has already run'})

            run.formulation_name = formulation_name
            run.save()

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

            return JsonResponse({'message': f'Calibration Run {run.id} updated', 'calibration_run_key': run.id})
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"exception": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
