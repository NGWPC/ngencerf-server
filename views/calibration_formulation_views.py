import json
import logging

from django.db import transaction
from django.http import JsonResponse
from rest_framework.decorators import api_view

from calibration.calibration_validators import SaveFormulationValidator, CalibrationRunValidator, ModuleHydrofabricListValidator
from calibration.management.commands import ngen_cal_input
from calibration.models import NgenCalFormulation, CalibrationFormulation, CalibrationSlothParam, \
    CalibrationTuneParameter, ModuleOutputVariable
from views.common import get_run, JsonError, JsonException

logger = logging.getLogger(__name__)


SLOTH = 'SLoTH'

# For testing
module_sample_data = {"modules_data": [
    {
        "name": "GC2D",
        "description": "description of module",
        "version": {
             "version": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
             "module_home_page": "https://www.acme-corp.com",
             "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Glacier"
        ]
    },
    {
        "name": "Noah-OWP-Modular",
        "description": "description of module",
        "version": {
            "version": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "module_home_page": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Snowmelt",
            "Evapotranspiration"
        ],
    },
    {
        "name": "Snow-17",
        "description": "description of module",
        "version": {
            "version": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "module_home_page": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Snowmelt"
        ]
    },
    {
        "name": "UEB",
        "description": "description of module",
        "version": {
            "version": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "module_home_page": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Snowmelt",
            "Evapotranspiration"
        ]
    },
    {
        "name": "CFE-S",
        "description": "description of module",
        "version": {
            "version": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "module_home_page": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Rainfall Runoff"
        ],
    },
    {
        "name": "CFE-X",
        "description": "description of module",
        "version": {
            "version": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "module_home_page": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Rainfall Runoff"
        ],
    },
    {
        "name": "PET",
        "description": "description of module",
        "version": {
            "version": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "module_home_page": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Evapotranspiration"
        ]
    },
    {
        "name": "TopModel",
        "description": "description of module",
        "version": {
            "version": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "module_home_page": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Rainfall Runoff"
        ]
    },
    {
        "name": "Sac-SMA",
        "description": "description of module",
        "version": {
            "version": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "module_home_page": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Rainfall Runoff"
        ]
    },
    {
        "name": "LASAM",
        "description": "description of module",
        "version": {
            "version": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "module_home_page": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Rainfall Runoff"
        ]
    },
    {
        "name": "SMP",
        "description": "description of module",
        "version": {
            "version": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "module_home_page": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Soil Moisture"
        ]
    },
    {
        "name": "SFT",
        "description": "description of module",
        "version": {
            "version": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "module_home_page": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Snowmelt"
        ]
    },
    {
        "name": "T-Route",
        "description": "description of module",
        "version": {
            "version": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "module_home_page": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Routing"
        ],
    },
    {
        "name": "SCHISM",
        "description": "description of module",
        "version": {
            "version": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "module_home_page": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Coastal"
        ]
    },
    {
        "name": "SFINCS",
        "description": "description of module",
        "version": {
            "version": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "module_home_page": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Coastal"
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

        run, errorReturn = get_run(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn

        user_formulation_name = run.user_formulation_name

        get_modules_from_hydrofabric(run)

        modules = (
            CalibrationFormulation.objects.filter(calibration_run=run).exclude(name=SLOTH)
            .only('name', 'groups', 'used_by_calibration_run')
            .values('name', 'groups', 'used_by_calibration_run')
        )
        # Unwrap the groups
        for m in modules:
            m['groups'] = json.loads(m['groups'])
        module_list = list(modules)

        use_sloth = run.use_sloth

        if use_sloth:
            # Get sloth parameters
            sloth_parameters = (
                CalibrationSlothParam.objects.filter(calibration_run=run)
                .only('param_name', 'param_count', 'param_type', 'param_units', 'param_location', 'param_value', 'maps_to_module',
                      'maps_to_variable_name')
                .values(
                    'param_name', 'param_count', 'param_type', 'param_units', 'param_location', 'param_value', 'maps_to_module',
                    'maps_to_variable_name')
            )
        else:
            sloth_parameters = {}

        ngen_cal_input.ready_to_run(run=run)

        return JsonResponse(
            {'calibration_run_id': run.id, 'status': run.status.name, 'formulation_name': user_formulation_name, "modules": module_list,
             'use_sloth': use_sloth,
             "sloth_parameters": list(sloth_parameters)}, safe=False)
    except Exception as e:
        return JsonException(e)


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

    validator = ModuleHydrofabricListValidator(data=module_sample_data)
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
        user_formulation_name = validate.data.get('formulation_name')
        use_sloth = validate.data.get('use_sloth')
        sloth_parameters = validate.data.get('sloth_parameters')

        run, errorReturn = get_run(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn

        # Make sure the formulation is valid
        valid_formulations = NgenCalFormulation.objects.all().only('name', 'modules').values('name', 'modules')
        valid = False
        for valid_formulation in valid_formulations:
            valid_module_set = set(json.loads(valid_formulation.get('modules')))
            if valid_module_set == new_module_names:
                valid = True
                run.ngen_formulation_name = valid_formulation.get('name')
                break
        if not valid:
            return JsonError("Invalid formulation-  '{}'".format(new_module_names))

        run.user_formulation_name = user_formulation_name

        if use_sloth:
            new_module_names.add(SLOTH)
            if not sloth_parameters:
                return JsonError("Invalid formulation -  You must enter SLoTH parameters")

        else:
            if sloth_parameters:
                return JsonError('You must check the box to allow Sloth parameters to be specified')

        # Did we get the names from Hydrofabric
        if not CalibrationFormulation.objects.filter(calibration_run_id=run.id).exists():
            return JsonError('Modules have not been received from Hydrofabric.  Should be done on load_formulation_tab')

        run.use_sloth = use_sloth

        # Get current new_module_names
        existing_module_names = set(CalibrationFormulation.objects
                                    .filter(calibration_run_id=run.id, used_by_calibration_run=True).values_list('name', flat=True))

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
                # Check that the module is valid
                if not CalibrationFormulation.objects.filter(name=s.get('maps_to_module'), calibration_run_id=run.id,
                                                             used_by_calibration_run=True).exists():
                    # error = f"Sloth parameters contain an invalid module - \'{s.get('maps_to_modules')}\'.  This module has not been added to this run"
                    # print(error)
                    return JsonError("Sloth parameters contain an invalid module - '{}'.  This module has not been added to this run".format(s.get('apps_to_modules')))

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
        return JsonException(e)
