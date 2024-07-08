import json

from django.db import transaction
from django.http import JsonResponse
from rest_framework.decorators import api_view

from .calibration_validators import SaveFormulationValidator, CalibrationRunValidator
from .models import NgenCalFormulation, CalibrationRun, CalibrationFormulation

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
# @login_required()
def get_modules(request, calibration_run_id=None):
    print('user', request.user)
    if request.method == "POST":
        body = json.loads(request.body)
        validate = CalibrationRunValidator(data=body or {})
        if not validate.is_valid():
            print('Validation errors', validate.errors)
            return JsonResponse({"errors": validate.errors})
        else:
            calibration_run_id = body.get('calibration_run_id')

    run = CalibrationRun.objects.filter(id=calibration_run_id).first()
    if not run:
        return JsonResponse({'message': f'Calibration Run {calibration_run_id} does not exist'})

    # Get this from hydrofabric

    # Save the modules
    for m in module_data:
        CalibrationFormulation.objects.create(name=m.get('name'), groups=json.dumps(m.get('groups')), calibration_run=run, description="need description")

    return JsonResponse(module_data)


@api_view(['POST'])
# @login_required
@transaction.atomic
def save_formulation_tab(request):
    print('user', request.user)
    body = json.loads(request.body)
    validate = SaveFormulationValidator(data=body or {})
    if not validate.is_valid():
        print('Validation errors', validate.errors)
        return JsonResponse({"errors": validate.errors})
    modules = set(body.get('modules'))
    calibration_run_id = body.get('calibration_run_id')
    formulation_name = body.get('formulation_name')

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

    run = CalibrationRun.objects.filter(id=calibration_run_id).first()
    if not run:
        return JsonResponse({'message': f'Calibration Run {calibration_run_id} does not exist'})

    run.formulation_name = formulation_name
    run.save()
    return JsonResponse({'message': f'Calibration Run {run.id} updated', 'calibration_run_key': run.id})
