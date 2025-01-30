import json
import logging

from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema, OpenApiResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.enums import StatusEnum
from calibration.models import CalibrationFormulation, CalibrationSlothParam, CalibrationParameter, ModuleOutputVariable, CalibrationRun
from calibration.util.caching import get_cached_module_by_name, get_cached_modules_with_groups, get_cached_module_groups
from calibration.util.calibration_validators import SaveFormulationRequestSerializer, CalibrationRunSerializer, LoadFormulationResponseSerializer, \
    ErrorResponseSerializer, SaveFormulationResponseSerializer
from calibration.views import ngen_cal_input
from calibration.views.common import get_calibration_run, ResponseError, handle_exceptions, validate_response, validate_request, SLOTH
from calibration.views.data_services import get_module_metadata_from_data_services, DataServicesException

logger = logging.getLogger(__name__)

MODULE_GROUPS_CACHE_KEY = 'cached_module_groups'


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
def load_formulation_tab(request) -> Response:
    """Load the formulation tab data for a specific calibration run."""

    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'load_formulation_tab() request from {request.user.email} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=list(StatusEnum))
    if error_return:
        return error_return

    # Retrieve all modules with their groups from the cache
    cached_modules = get_cached_modules_with_groups()

    # Prepare modules list as dictionaries for response serialization
    module_groups_list = [
        {
            "name": module.name,
            "is_active": module.is_active,
            "groups": [group.name for group in module.groups.order_by('order')]
        }
        for module in cached_modules.values()
    ]

    # Retrieve cached module groups
    module_groups = get_cached_module_groups()

    ngen_cal_input.ready_to_run(run)

    response = {'calibration_run_id': run.id, 'status': run.status.name, 'modules': module_groups_list, 'module_groups': module_groups}

    response_validator, error_response = validate_response(LoadFormulationResponseSerializer, response)
    if error_response:
        return error_response

    logger.debug(f'Returning to {request.user.email} from load_formulation_tab() - {json.dumps(response_validator.data)}')

    return Response(response_validator.data)


def get_sloth_parameters(run: CalibrationRun) -> list[dict[str, str]]:
    """
    Retrieve Sloth parameters for a given calibration run.

    Parameters:
        run (CalibrationRun): The calibration run instance.

    Returns:
        list[dict[str, str]]: A list of Sloth parameters formatted as dictionaries.
    """
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
def save_formulation_tab(request) -> Response:
    """Save the formulation tab data for a calibration run."""

    data = request.data
    logger.debug(f'save_formulation_tab() request from {request.user.email} - {data}')

    validator, error_return = validate_request(SaveFormulationRequestSerializer, data)
    if error_return:
        return error_return

    new_module_names = set(validator.get('modules'))
    calibration_run_id = validator.get('calibration_run_id')
    user_formulation_name = validator.get('formulation_name')
    use_sloth = validator.get('use_sloth')
    sloth_parameters = validator.get('sloth_parameters')

    run, error_return = get_calibration_run(calibration_run_id, request.user)
    if error_return:
        return error_return

    run.user_formulation_name = user_formulation_name

    # Validate modules and formulation constraints
    error_message = validate_modules(new_module_names)
    if error_message:
        return ResponseError(error_message)

    formulation_warning, nwm_warning = validate_formulation(new_module_names)

    if not use_sloth and sloth_parameters:
        return ResponseError(f'You must check the box to allow {SLOTH} parameters to be specified')

    # Set run.use_sloth and handle Sloth parameters
    run.use_sloth = use_sloth

    # Initialize the eds_errors list
    eds_errors = []

    # Fetch all formulations and determine changes
    existing_formulations_qs = CalibrationFormulation.objects.filter(
        calibration_run=run
    )
    existing_module_names = set(existing_formulations_qs.values_list('module__name', flat=True))
    # Determine which modules to delete and add
    to_be_added = new_module_names - existing_module_names
    to_be_unused = existing_module_names - new_module_names

    with transaction.atomic():
        # Delete unused formulations
        if to_be_unused:
            logger.info(f"Deleting unused modules: {to_be_unused}")
            delete_unused_formulations(to_be_unused, run)

        # Add new formulations
        for module_name in to_be_added:
            module_instance = get_cached_module_by_name(module_name)
            CalibrationFormulation.objects.get_or_create(calibration_run=run, module=module_instance)

        # Identify formulations without any calibration parameters, in case there was an error retriving them
        formulations_without_params_qs = existing_formulations_qs.filter(calibrationparameter__isnull=True)

        required_formulations_qs = existing_formulations_qs.filter(module__name__in=to_be_added) | formulations_without_params_qs

        # Retrieve metadata for required formulations
        if required_formulations_qs.exists() and run.gage:
            logger.info(f"Fetching metadata for modules: {required_formulations_qs}")
            try:
                get_module_metadata_from_data_services(run, required_formulations_qs)
            except DataServicesException as e:
                logger.exception("Error retrieving module parameter data from Data Services")
                eds_errors.append({
                    'name': 'parameters',
                    'message': str(e),
                    'status_code': e.status_code if e.status_code else None
                })

        # Delete existing Sloth params for this run and re-add them
        CalibrationSlothParam.objects.filter(calibration_run=run).delete()

        error_message = add_sloth_parameters(run, sloth_parameters, new_module_names)
        if error_message:
            logger.error(f"Error adding Sloth parameters: {error_message}")
            return ResponseError(error_message)

        run.save()

    ngen_cal_input.ready_to_run(run)

    response = {
        'message': f'Calibration Job {run.id} updated',
        'calibration_run_id': run.id,
        'status': run.status.name,
        'nwm_warning': nwm_warning
    }
    if formulation_warning:
        response['formulation_warning'] = formulation_warning
    if eds_errors:
        response['eds_errors'] = eds_errors

    response_validator, error_response = validate_response(SaveFormulationResponseSerializer, response)
    if error_response:
        return error_response

    logger.debug(f'Returning to {request.user.email} from save_formulation_tab() - {json.dumps(response_validator.data)}')
    return Response(response_validator.data)


def delete_unused_formulations(to_delete_modules: set[str], run: CalibrationRun) -> None:
    """Delete unused formulations and related parameters for a given calibration run."""

    formulations_to_delete = CalibrationFormulation.objects.filter(
        calibration_run=run,
        module__name__in=to_delete_modules
    )

    # Check if the current module_output_variable references a formulation to be deleted
    if run.module_output_variable and run.module_output_variable.calibration_formulation in formulations_to_delete:
        run.module_output_variable = None
        run.save(update_fields=["module_output_variable"])

    # Delete CalibrationParameters related to the formulations_to_delete
    CalibrationParameter.objects.filter(calibration_formulation__in=formulations_to_delete).delete()

    # Delete ModuleOutputVariables related to the formulations_to_delete
    ModuleOutputVariable.objects.filter(calibration_formulation__in=formulations_to_delete).delete()

    # Finally, delete the formulations
    formulations_to_delete.delete()


def validate_modules(module_names: set[str]) -> str | None:
    """Validate that all the provided module names exist in the cached modules."""

    valid_names = {name for name in module_names if get_cached_module_by_name(name)}
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
                "expected_counts": [0]  # Change back to [0, 1], once Topoflow is allowed
            },
            "Snowmelt": {
                "expected_counts": [0, 1]
            },
            "Evapotranspiration": {
                "expected_counts": [1]
            },
            "Rainfall Runoff": {
                "expected_counts": [1]
            },
            "Soil Moisture": {
                "expected_counts": [0, 2]
            },
            "Routing": {
                "expected_counts": [1]
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


def validate_formulation(module_names: set[str]) -> tuple[dict | None, bool]:
    """Validate formulation rules based on group requirements and exclusions."""

    if not module_names:
        return None, False

    # Filter cached modules to match the given module names
    my_modules = [get_cached_module_by_name(module_name) for module_name in module_names]

    # Initialize a dictionary to store the count of modules per group
    group_counts = {group_name: 0 for group_name in formulation_validations['formulation_rules']['group_requirements']}

    # Parse the groups for each module once and update the group counts
    for module in my_modules:
        for group in module.groups.all():
            if group.name in group_counts:  # Only count groups that are in the group_requirements
                group_counts[group.name] += 1

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
                msg = f"{excluded_module} module cannot exist without one of the following: {', '.join(must_have_modules)}"
                logger.warning(msg)
                messages.append(msg)
                formulation_validation_json['excluded_modules'].append(
                    {'module_name': excluded_module, 'must_have': must_have_modules}
                )

    # Validate group requirements
    for group_name, group_rules in formulation_validations['formulation_rules']['group_requirements'].items():
        expected_counts = group_rules.get('expected_counts')
        count = group_counts.get(group_name, 0)

        # Validate the count against expected_counts
        if count not in expected_counts:
            msg = f"{group_name} group is expected to have {expected_counts} modules, but it has {count}"
            logger.warning(msg)
            messages.append(msg)
            formulation_validation_json['group_requirements'].append(
                {'group_name': group_name, 'expected_counts': expected_counts, 'has_count': count}
            )

    nwm_warning = False

    # Check that required groups have at least one module
    required_groups = formulation_validations['formulation_rules']['nwm_required_groups']
    for required_group in required_groups:
        if group_counts.get(required_group, 0) == 0:  # If a required group has no modules, set nwm_warning to True
            nwm_warning = True
            break  # No need to continue checking if one required group is missing

    # Return the messages, validation details, and the NWM warning status
    if messages:
        formulation_validation_json['messages'] = messages
        return formulation_validation_json, nwm_warning
    else:
        return None, nwm_warning


def add_sloth_parameters(run: CalibrationRun, sloth_parameters: list[dict], module_names: set[str]) -> str | None:
    """Add Sloth parameters to a calibration run, validating module associations."""

    sloth_param_objects = []
    if sloth_parameters is not None:
        for s in sloth_parameters:
            module = get_cached_module_by_name(s['maps_to_module'])
            if not module or module.name not in module_names:
                return f"Sloth parameter '{s['param_name']}' has an invalid module - '{s['maps_to_module']}'.  This module has not been added to this run"

            sloth_param_objects.append(
                CalibrationSlothParam(
                    calibration_run=run, param_name=s['param_name'], param_count=s['param_count'],
                    param_type=s['param_type'], param_units=s['param_units'], param_location=s['param_location'],
                    param_value=s['param_value'], maps_to_module=module, maps_to_variable_name=s['maps_to_variable_name']
                )
            )

        CalibrationSlothParam.objects.bulk_create(sloth_param_objects)
