import json
import traceback

from django.db import transaction
from django.db.models import F
from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import api_view

from calibration.calibration_validators import SaveFormulationValidator, CalibrationRunValidator, ModuleCollectionValidator
from calibration.enums import StatusEnum
from calibration.management.commands import ngen_cal_input
from calibration.models import NgenCalFormulation, CalibrationRun, CalibrationFormulation, CalibrationSlothParam, \
    CalibrationTuneParameter, ModuleOutputVariable

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
# @login_required()
def load_formulation_tab(request):
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

        formulation_name = run.formulation_name

        get_modules_from_hydrofabric(run)

        modules = (
            CalibrationFormulation.objects.filter(calibration_run=run)
            .only('name', 'groups', 'used_by_calibration_run')
            .values('name', 'groups', 'used_by_calibration_run')
        )
        # Unwrap the groups
        for m in modules:
            m['groups'] = json.loads(m['groups'])

        # Get sloth parameters
        sloth_parameters = (
            CalibrationSlothParam.objects.filter(calibration_run=run)
            .only('param_name', 'param_count', 'param_type', 'param_units', 'param_location', 'param_value', 'maps_to_module',
                  'maps_to_variable_name')
            .values(
                'param_name', 'param_count', 'param_type', 'param_units', 'param_location', 'param_value', 'maps_to_module', 'maps_to_variable_name')
        )
        print('sloth', sloth_parameters)

        ngen_cal_input.ready_to_run(run=run)

        return JsonResponse(
            {'calibration_run_id': run.id, 'status': run.status.name, 'formulation_name': formulation_name, "modules": list(modules),
             "sloth_parameters": list(sloth_parameters)}, safe=False)
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"exception": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def get_modules_from_hydrofabric(run):
    print('calling hydrofabric')

    # Get this from hydrofabric
    # modules_request = {}
    # response = requests.post(settings.HYDROFABRIC_URL, json=modules_request)
    # module_data = response.json()

    current_module_names = set(
        CalibrationFormulation.objects.filter(calibration_run=run)
        .only('name')
        .values_list('name', flat=True)
    )

    print('current_module_names', current_module_names)

    validator = ModuleCollectionValidator(data=module_sample_data)
    if not validator.is_valid():
        print(validator.errors)
        raise Exception('Module data from Hydrofabric is not in the expected format')

    module_data = module_sample_data.get("modules_data")
    new_modules_names = set(map(lambda mod: mod.get('name'), module_data))
    print('new_modules_names', new_modules_names)

    with transaction.atomic():
        if current_module_names != new_modules_names:
            # Only if the modules names have changed
            to_be_deleted = current_module_names - new_modules_names

            CalibrationFormulation.objects.filter(calibration_run=run, name__in=to_be_deleted).delete()

            # Create the new ones, if they don't already exist
            for m in module_data:
                CalibrationFormulation.objects.get_or_create(name=m.get('name'), calibration_run=run,
                                                             defaults={'groups': json.dumps(m.get('groups')),
                                                                       'description': m.get('description')})

        return


@api_view(['POST'])
# @login_required
def save_formulation_tab(request):
    try:
        print('user', request.user)
        body = json.loads(request.body or '{}')
        validate = SaveFormulationValidator(data=body)
        validate.is_valid(raise_exception=True)

        new_module_names = set(validate.data.get('modules'))
        calibration_run_id = validate.data.get('calibration_run_id')
        formulation_name = validate.data.get('formulation_name')
        sloth_parameters = validate.data.get('sloth_parameters')

        # Make sure the formulation is valid
        valid_formulations = NgenCalFormulation.objects.all().values_list('modules', flat=True)
        valid = False
        for valid_formulation in valid_formulations:
            valid_module_set = set(json.loads(valid_formulation))
            if valid_module_set == new_module_names:
                valid = True
                break
        if not valid:
            return JsonResponse({"error": f"Invalid formulation - {new_module_names}"})

        # TODO Need to filter jobs by user
        run = CalibrationRun.objects.filter(id=calibration_run_id).select_related('status').first()
        if not run:
            return JsonResponse({'error': f'Calibration Run {calibration_run_id} does not exist or is not owned by {request.user}'},
                                status=status.HTTP_400_BAD_REQUEST)
        if run.status.name != StatusEnum.READY and run.status.name != StatusEnum.SAVED:
            return JsonResponse({'error': f'Calibration Run {calibration_run_id} is not saved or ready.  Status: {run.status.name}'},
                                status=status.HTTP_400_BAD_REQUEST)

        run.formulation_name = formulation_name

        # Get current new_module_names
        existing_module_names = set(
            CalibrationFormulation.objects.filter(calibration_run_id=run.id, used_by_calibration_run=True).values_list('name', flat=True))

        print('old existing_module_names', existing_module_names)
        print('new existing_module_names', new_module_names)

        with transaction.atomic():
            # Only if the module names have changed
            if new_module_names != existing_module_names:
                to_be_unused = existing_module_names - new_module_names
                print('to_be_unused', to_be_unused)

                # Set them to be unused and delete any parameters and output variables
                CalibrationFormulation.objects.filter(calibration_run=run, name__in=to_be_unused).update(used_by_calibration_run=False)
                CalibrationTuneParameter.objects.all().filter(calibration_formulation__calibration_run=run,
                                                              calibration_formulation__name__in=to_be_unused).delete()
                ModuleOutputVariable.objects.all().filter(calibration_formulation__name__in=to_be_unused).delete()

                # Create any new formulations
                for name in new_module_names:
                    CalibrationFormulation.objects.update_or_create(calibration_run=run, name=name, defaults={'used_by_calibration_run': True})

            # Delete sloth params for this run if they've already been specified - no harm to just delete them all and re-save
            CalibrationSlothParam.objects.filter(calibration_run=run).delete()
            for s in sloth_parameters:
                print('s', s)
                # Check that the module is valid
                if not CalibrationFormulation.objects.filter(name=s.get('maps_to_module'), calibration_run_id=run.id,
                                                             used_by_calibration_run=True).exists():
                    error = f"Sloth parameters contain an invalid module - \'{s.get('maps_to_modules')}\'.  This module has not been added to this run"
                    print(error)
                    return JsonResponse({"error": error}, status=status.HTTP_400_BAD_REQUEST)

            run.save()
            for s in sloth_parameters:
                # Get the new_module_names, so we can set it
                module = CalibrationFormulation.objects.filter(name=s.get('maps_to_module'), calibration_run_id=run.id).first()
                CalibrationSlothParam.objects.create(calibration_run=run, param_name=s.get('param_name'), param_count=s.get('param_count'),
                                                     param_type=s.get('param_type'),
                                                     param_units=s.get('param_units'), param_location=s.get('param_location'),
                                                     param_value=s.get('param_value'), maps_to_module=module,
                                                     maps_to_variable_name=s.get('maps_to_variable_name'))

            ngen_cal_input.ready_to_run(run=run)

            return JsonResponse({'message': f'Calibration Run {run.id} updated', 'calibration_run_key': run.id, 'status': run.status.name})
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"exception": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
