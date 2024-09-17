import json
import logging

from django.db import transaction
from django.db.models import Prefetch
from drf_spectacular.utils import OpenApiParameter, extend_schema, OpenApiResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.models import NgenCalFormulation, CalibrationFormulation, CalibrationSlothParam, CalibrationParameter, ModuleOutputVariable
from calibration.util.calibration_validators import SaveFormulationRequestSerializer, CalibrationRunSerializer, GenericResponseSerializer, \
    LoadFormulationResponseSerializer, ErrorResponseSerializer
from calibration.views import ngen_cal_input
from calibration.views.common import get_run, ResponseError, handle_exceptions, validate_response, validate_request
from calibration.views.hydrofabric import get_modules_from_hydrofabric

logger = logging.getLogger(__name__)

SLOTH = 'SLoTH'


@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: LoadFormulationResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: ErrorResponseSerializer
    },
    parameters=[
        OpenApiParameter(name='calibration_run_id', description='ID of the calibration run', required=True, type=int)
    ],
    description="Load formulation tab data"
)
@api_view(['GET', 'POST'])
@handle_exceptions
# @permission_classes([AllowAny])()
def load_formulation_tab(request):
    data = request.data if request.method == 'POST' else request.query_params

    logger.debug(f'load_formulation_tab() request from {request.user} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_run(calibration_run_id, request.user)
    if error_return:
        return error_return

    get_modules_from_hydrofabric(run)

    modules = get_all_modules(run)

    # Unwrap the groups
    for m in modules:
        m['groups'] = json.loads(m['groups'])
    module_list = list(modules)

    ngen_cal_input.ready_to_run(run)

    response = {'calibration_run_id': run.id, 'status': run.status.name, "modules": module_list}

    response = {key: value for key, value in response.items() if value not in [None, '', [], {}]}

    response_validator, error_response = validate_response(LoadFormulationResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user} from load_formulation_tab() - {response_validator.data}')

    return Response(response_validator.data)


def get_all_modules(run):
    return list(
        CalibrationFormulation.objects.filter(calibration_run=run)
        .exclude(name=SLOTH)
        .values('name', 'groups', 'used_by_calibration_run')
    )


def get_my_modules(run):
    return list(
        CalibrationFormulation.objects
        .filter(calibration_run=run, used_by_calibration_run=True)
        .exclude(name=SLOTH)
        .values_list('name', flat=True)
    )


def get_sloth_parameters(run):
    sloth_parameters = list(
        CalibrationSlothParam.objects.filter(calibration_run=run)
        .prefetch_related(Prefetch('maps_to_module', queryset=CalibrationFormulation.objects.only('name')))
        .values(
            'param_name', 'param_count', 'param_type', 'param_units', 'param_location', 'param_value', 'maps_to_module__name',
            'maps_to_variable_name')
    )
    [sloth_param.update({'maps_to_module': sloth_param.pop('maps_to_module__name')}) for sloth_param in sloth_parameters]
    return sloth_parameters


@extend_schema(
    request=SaveFormulationRequestSerializer,
    responses={
        200: GenericResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: ErrorResponseSerializer
    },
    description="Save formulation tab data"
)
@api_view(['POST'])
# @permission_classes([AllowAny])
@handle_exceptions
def save_formulation_tab(request):
    data = request.data

    logger.debug(f'save_formulation_tab() request from {request.user} - {data}')

    validator, error_return = validate_request(SaveFormulationRequestSerializer, data)
    if error_return:
        return error_return

    new_module_names = set(validator.get('modules'))
    calibration_run_id = validator.get('calibration_run_id')
    user_formulation_name = validator.get('formulation_name')
    use_sloth = validator.get('use_sloth')
    sloth_parameters = validator.get('sloth_parameters')

    run, error_return = get_run(calibration_run_id, request.user)
    if error_return:
        return error_return

    run.user_formulation_name = user_formulation_name

    # Did we get the names from Hydrofabric?
    if not CalibrationFormulation.objects.filter(calibration_run_id=run.id).exists():
        return ResponseError('Modules have not been received from Hydrofabric.  Should be done on load_formulation_tab')

    error_message = validate_modules(run, new_module_names)
    if error_message:
        return ResponseError(error_message)

    messages = validate_formulation2(run, new_module_names)
    if messages:
        return ResponseError(messages)

    if use_sloth:
        new_module_names.add(SLOTH)
        if not sloth_parameters:
            return ResponseError(f"If 'use_sloth' is checked, you must enter {SLOTH} parameters")
    else:
        if sloth_parameters:
            return ResponseError(f'You must check the box to allow {SLOTH} parameters to be specified')

    run.use_sloth = use_sloth

    # Get current new_module_names
    existing_module_names = set(CalibrationFormulation.objects
                                .filter(calibration_run_id=run.id, used_by_calibration_run=True)
                                .values_list('name', flat=True))

    print('old existing_module_names', existing_module_names)
    print('new existing_module_names', new_module_names)

    # Only if the module names have changed
    if new_module_names != existing_module_names:
        to_be_unused = existing_module_names - new_module_names
        print('to_be_unused', to_be_unused)

        with transaction.atomic():
            # Turn off `used_by_calibration_run` for unused modules
            CalibrationFormulation.objects.filter(calibration_run=run, name__in=to_be_unused).update(used_by_calibration_run=False)

            # Delete associated CalibrationParameters and ModuleOutputVariables explicitly
            CalibrationParameter.objects.filter(calibration_formulation__calibration_run=run,
                                                calibration_formulation__name__in=to_be_unused).delete()
            ModuleOutputVariable.objects.filter(calibration_formulation__name__in=to_be_unused).delete()

            # Create any new formulations
            # for name in new_module_names:
            #     CalibrationFormulation.objects.update_or_create(calibration_run=run, name=name, defaults={'used_by_calibration_run': True})
            # These objects should already exist.  Not sure why I was using update_or_create

            # Update existing formulations to set `used_by_calibration_run=True`
            CalibrationFormulation.objects.filter(
                calibration_run=run, name__in=new_module_names
            ).update(used_by_calibration_run=True)

            # Delete sloth params for this run if they've already been specified - no harm to just delete them all and re-save
            CalibrationSlothParam.objects.filter(calibration_run=run).delete()
            if use_sloth:
                error_message = add_sloth_parameters(run, sloth_parameters)
            if error_message:
                return ResponseError(error_message)

            run.save()

        ngen_cal_input.ready_to_run(run)

        response = {'message': f'Calibration Run {run.id} updated', 'calibration_run_id': run.id, 'status': run.status.name}

        response_validator, error_response = validate_response(GenericResponseSerializer, response)
        if error_response:
            return error_response

        logger.debug(f'Returning to {request.user} from save_formulation_tab() - {response_validator.data}')
        return Response(response_validator.data)


def validate_modules(run, module_names):
    # Check that all the module names are valid
    valid_names = set(CalibrationFormulation.objects.filter(calibration_run_id=run.id, name__in=module_names).values_list('name', flat=True))
    if module_names - valid_names:
        return f'Invalid modules - {module_names - valid_names}'
    return None


def validate_formulation(run, module_names):
    valid_formulations = NgenCalFormulation.objects.all().values('name', 'modules')
    valid = False
    for valid_formulation in valid_formulations:
        valid_module_set = set(json.loads(valid_formulation['modules']))
        if valid_module_set == module_names:
            valid = True
            run.ngen_formulation_name = valid_formulation['name']
            break
    return valid


formulation_validations = {
    "formulation_rules": {
        "group_requirements": {
            "Glacier": {
                "allowed_counts": [0, 1]
            },
            "Snowmelt": {
                "allowed_counts": [0, 1]
            },
            "Evapotranspiration": {
                "allowed_counts": [1]
            },
            "Rainfall Runoff": {
                "allowed_counts": [1]
            },
            "Soil Moisture": {
                "allowed_counts": [0, 2]
            },
            "Routing": {
                "allowed_counts": [1]
            }
        },
        "module_exclusions": {
            "SMP": {
                "must_have": ["CFE-S", "CFE-X", "LASAM"]
            },
            "SFT": {
                "must_have": ["CFE-S", "CFE-X", "LASAM"]
            }
        }
    }
}


def validate_formulation2(run, module_names):
    calibration_formulations = CalibrationFormulation.objects.filter(
        name__in=module_names,
        calibration_run=run
    )

    # Create the list of dicts
    formulation_dicts = []
    for formulation in calibration_formulations:
        groups = json.loads(formulation.groups)  # Parse the groups JSON string into a list
        formulation_dicts.append({
            "name": formulation.name,
            "groups": groups  # Add the parsed groups list here
        })

    # Initialize a dictionary to store the count of formulations per group
    group_counts = {group_name: 0 for group_name in formulation_validations['formulation_rules']['group_requirements']}

    # Initialize a set to track which modules exist
    module_set = set(module_names)

    # Parse the groups for each formulation once and update the group counts
    for formulation in calibration_formulations:
        groups = json.loads(formulation.groups)  # Parse the groups JSON string once
        for group_name in groups:
            if group_name in group_counts:  # Only update if the group is in group_requirements
                group_counts[group_name] += 1

    # Check for module exclusions
    messages = []
    for excluded_module, conditions in formulation_validations['formulation_rules']['module_exclusions'].items():
        if excluded_module in module_set:  # If the excluded module exists
            must_have_modules = conditions.get("must_have", [])
            # Check if any of the required modules are present
            if not any(module in module_set for module in must_have_modules):
                messages.append(
                    f"{excluded_module} module cannot exist without one of the following: {', '.join(must_have_modules)}"
                )

    # Validate group requirements
    for group_name, group_rules in formulation_validations['formulation_rules']['group_requirements'].items():
        allowed_counts = group_rules.get('allowed_counts')
        count = group_counts[group_name]

        # Validate the count against allowed_counts
        if count not in allowed_counts:
            messages.append(f"{group_name} group must have {allowed_counts} modules, but it has {count}")

    return messages


def add_sloth_parameters(run, sloth_parameters):
    modules = CalibrationFormulation.objects.filter(
        name__in=[s['maps_to_module'] for s in sloth_parameters],
        calibration_run=run,
        used_by_calibration_run=True
    )

    module_dict = {module.name: module for module in modules}

    sloth_param_objects = []
    for s in sloth_parameters:
        module = module_dict.get(s['maps_to_module'])
        if not module:
            return f"Sloth parameter \'{s['param_name']}\' contains an invalid module - \'{s['maps_to_module']}\'.  This module has not been added to this run"

        sloth_param_objects.append(
            CalibrationSlothParam(
                calibration_run=run, param_name=s['param_name'], param_count=s['param_count'],
                param_type=s['param_type'], param_units=s['param_units'], param_location=s['param_location'],
                param_value=s['param_value'], maps_to_module=module, maps_to_variable_name=s['maps_to_variable_name']
            )
        )

    CalibrationSlothParam.objects.bulk_create(sloth_param_objects)
