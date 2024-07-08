import json

from django.db import transaction
from django.db.models import Prefetch
from django.http import JsonResponse
from rest_framework.decorators import api_view

from .calibration_validators import SaveFormulationValidator
from .models import Module, ModuleGroup, NgenCalFormulation, CalibrationRun


@api_view(['GET', 'POST'])
# @login_required()
def get_modules(request):
    modules = Module.objects.filter(is_active=True).prefetch_related(
        Prefetch('groups', queryset=ModuleGroup.objects.only('name').filter(is_active=True)))

    result = []
    for module in modules:
        groups = [group.name for group in module.groups.all()]
        result.append({
            'name': module.name,
            'groups': groups
        })

    return JsonResponse(result, safe=False)


@api_view(['POST'])
# @login_required
@transaction.atomic
def save_formulation_tab(request):
    print('user', request.user)
    body = json.loads(request.body)
    validate = SaveFormulationValidator(data=body)
    print('validate', validate)
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
