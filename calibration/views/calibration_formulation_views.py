import logging
from typing import Set

from django.core.cache import cache
from django.db import transaction
from django.db.models import Prefetch
from drf_spectacular.utils import OpenApiParameter, extend_schema, OpenApiResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.models import CalibrationFormulation, CalibrationSlothParam, CalibrationParameter, ModuleOutputVariable, CalibrationRun
from calibration.models.module import Module
from calibration.models.module_group import ModuleGroup
from calibration.util.calibration_validators import SaveFormulationRequestSerializer, CalibrationRunSerializer, LoadFormulationResponseSerializer, \
    ErrorResponseSerializer, SaveFormulationResponseSerializer
from calibration.views import ngen_cal_input
from calibration.views.common import get_run, ResponseError, handle_exceptions, validate_response, validate_request, SLOTH

logger = logging.getLogger(__name__)


@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: LoadFormulationResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
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
    data = request.data if request.method == 'POST' else request.query_params.dict()

    logger.debug(f'load_formulation_tab() request from {request.user} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_run(calibration_run_id, request.user)
    if error_return:
        return error_return

    modules = Module.objects.prefetch_related('groups')
    module_groups_list = [
        {
            "name": module.name,
            "is_active": module.is_active,
            "groups": [group.name for group in module.groups.all()]
        }
        for module in modules
    ]

    # hydrofabric_errors = []
    #
    # # Do we already have modules?
    # have_modules = CalibrationFormulation.objects.filter(calibration_run=run).exists()
    #
    # if not have_modules:
    #     try:
    #         get_modules_from_hydrofabric(run)
    #     except HydrofabricException as e:
    #         logger.error(f"Error retrieving module data from Hydrofabric: {traceback.format_exc()}")
    #         hydrofabric_errors.append({'name': 'modules', 'message': str(e), 'status_code': e.status_code if e.status_code else '5xx'})
    #
    # modules = get_all_modules(run)
    #
    # # Unwrap the groups
    # for m in modules:
    #     m['groups'] = json.loads(m['groups'])
    # module_list = list(modules)

    ngen_cal_input.ready_to_run(run)

    response = {'calibration_run_id': run.id, 'status': run.status.name, 'modules': module_groups_list}
    # if hydrofabric_errors:
    #     response['hydrofabric_errors'] = hydrofabric_errors

    response_validator, error_response = validate_response(LoadFormulationResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user} from load_formulation_tab() - {response_validator.data}')

    return Response(response_validator.data)


def get_my_modules(run):
    return list(
        CalibrationFormulation.objects
        .filter(calibration_run=run,)
        .values_list('module__name', flat=True)
    )


def get_sloth_parameters(run):
    sloth_parameters = list(
        CalibrationSlothParam.objects.filter(calibration_run=run)
        .select_related('maps_to_module')
        .values(
            'param_name', 'param_count', 'param_type', 'param_units', 'param_location', 'param_value',
            'maps_to_module__name', 'maps_to_variable_name')
    )
    for sloth_param in sloth_parameters:
        sloth_param['maps_to_module'] = sloth_param.pop('maps_to_module__name')

    return sloth_parameters


@extend_schema(
    request=SaveFormulationRequestSerializer,
    responses={
        200: SaveFormulationResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Save formulation tab data"
)
@api_view(['POST'])
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

    error_message = validate_modules(new_module_names)
    if error_message:
        return ResponseError(error_message)

    messages, formulation_validation_json, nwm_warning = validate_formulation(new_module_names)
    if messages:
        return ResponseError(messages, validation_errors=formulation_validation_json, response_type='formulation_error')

    if use_sloth:
        if not sloth_parameters:
            return ResponseError(f"If 'use_sloth' is checked, you must enter {SLOTH} parameters")
    else:
        if sloth_parameters:
            return ResponseError(f'You must check the box to allow {SLOTH} parameters to be specified')

    run.use_sloth = use_sloth

    # Get current new_module_names
    existing_module_names = set(CalibrationFormulation.objects
                                .filter(calibration_run_id=run.id)
                                .values_list('module__name', flat=True))

    print('old existing_module_names', existing_module_names)
    print('new existing_module_names', new_module_names)

    # Only if the module names have changed
    if new_module_names != existing_module_names:
        to_be_unused = existing_module_names - new_module_names
        print('to_be_unused', to_be_unused)

        with transaction.atomic():
            # Delete modules that are no longer used, as well as associated CalibrationParameters and ModuleOutputVariables
            CalibrationFormulation.objects.filter(calibration_run=run, module__name__in=to_be_unused).delete()
            CalibrationParameter.objects.filter(calibration_formulation__calibration_run=run,
                                                calibration_formulation__module__name__in=to_be_unused).delete()
            ModuleOutputVariable.objects.filter(calibration_formulation__module__name__in=to_be_unused).delete()

            for m_name in new_module_names:
                module_instance = get_cached_module_by_name(m_name)
                CalibrationFormulation.objects.get_or_create(calibration_run=run, module=module_instance)

            # Delete sloth params for this run if they've already been specified since they might refer to modules no longer in use
            # Easier to just delete them all and then re-validate  and re-save
            CalibrationSlothParam.objects.filter(calibration_run=run).delete()
            if use_sloth:
                error_message = add_sloth_parameters(run, sloth_parameters)
            if error_message:
                return ResponseError(error_message)

            run.save()

    ngen_cal_input.ready_to_run(run)
    response = {'message': f'Calibration Run {run.id} updated', 'calibration_run_id': run.id, 'status': run.status.name, 'nwm_warning': nwm_warning}

    response_validator, error_response = validate_response(SaveFormulationResponseSerializer, response)
    if error_response:
        return error_response

    logger.debug(f'Returning to {request.user} from save_formulation_tab() - {response_validator.data}')
    return Response(response_validator.data)


def validate_modules(module_names):
    """
    Validate that all the provided module names exist in the cached modules.
    """
    # Check that all the module names are valid
    valid_names = set(module_name for module_name in module_names if get_cached_module_by_name(module_name))

    if module_names - valid_names:
        return f'Invalid modules - {module_names - valid_names}'
    return None


formulation_validations = {
    "formulation_rules": {
        "nwm_required_groups": [
            "Glacier"
        ],
        "group_requirements": {
            "Glacier": {
                "allowed_counts": [0]  # Change back to [0, 1], once Topoflow is allowed
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


def validate_formulation(module_names: Set[str]):
    # modules = get_cached_modules()

    # Filter cached modules to match the given module names
    my_modules = [get_cached_module_by_name(module_name) for module_name in module_names if get_cached_module_by_name(module_name)]

    print('my_modules', my_modules)

    # Initialize a dictionary to store the count of modules per group
    group_counts = {group_name: 0 for group_name in formulation_validations['formulation_rules']['group_requirements']}

    # Initialize a set to track which modules exist
    # module_set = set(module_names)

    # Parse the groups for each module once and update the group counts
    for module in my_modules:
        for group in module.groups.all():
            if group.name in group_counts:  # Only count groups that are in the group_requirements
                group_counts[group.name] += 1
    print('group_counts', group_counts)

    # Check for module exclusions
    messages = []
    formulation_validation_json = {
        "excluded_modules": [],
        "group_requirements": []
    }

    # Validate excluded modules based on conditions
    for excluded_module, conditions in formulation_validations['formulation_rules']['module_exclusions'].items():
        if excluded_module in module_names:  # If the excluded module exists
            must_have_modules = conditions.get("must_have", [])
            # Check if any of the required modules are present
            if not any(module in module_names for module in must_have_modules):
                messages.append(
                    f"{excluded_module} module cannot exist without one of the following: {', '.join(must_have_modules)}"
                )
                formulation_validation_json['excluded_modules'].append(
                    {'module_name': excluded_module, 'must_have': must_have_modules}
                )

    # Validate group requirements
    for group_name, group_rules in formulation_validations['formulation_rules']['group_requirements'].items():
        allowed_counts = group_rules.get('allowed_counts')
        count = group_counts.get(group_name, 0)

        # Validate the count against allowed_counts
        if count not in allowed_counts:
            messages.append(f"{group_name} group must have {allowed_counts} modules, but it has {count}")
            formulation_validation_json['group_requirements'].append(
                {'group_name': group_name, 'required_count': allowed_counts, 'has_count': count}
            )

    nwm_warning = False

    # Check that required groups have at least one module
    required_groups = formulation_validations['formulation_rules']['nwm_required_groups']
    for required_group in required_groups:
        if group_counts.get(required_group, 0) == 0:  # If a required group has no modules, set nwm_warning to True
            nwm_warning = True
            break  # No need to continue checking if one required group is missing

    # Return the messages, validation details, and the NWM warning status
    return messages, formulation_validation_json, nwm_warning


def add_sloth_parameters(run: CalibrationRun, sloth_parameters):
    sloth_param_objects = []
    for s in sloth_parameters:
        module = get_cached_module_by_name(s['maps_to_module'])
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


MODULE_CACHE_KEY = 'module_cache_by_name'


def get_cached_module_by_name(module_name):
    # Check if the cache already has the module dictionary
    cached_modules = cache.get(MODULE_CACHE_KEY)

    # If not cached, retrieve the modules from the database and cache them
    if cached_modules is None:
        # Prefetch related groups when querying for modules
        modules = Module.objects.prefetch_related(
            Prefetch('groups', queryset=ModuleGroup.objects.only('name'))  # Fix: Replace with ModuleGroup
        )
        cached_modules = {module.name: module for module in modules}
        cache.set(MODULE_CACHE_KEY, cached_modules, None)

    # Return the module instance for the given name or None if not found
    return cached_modules.get(module_name)
