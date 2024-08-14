import json
import logging
from json.decoder import JSONDecodeError

from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema, PolymorphicProxySerializer
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from calibration.models import NgenCalFormulation, CalibrationFormulation, CalibrationSlothParam, \
    CalibrationTuneParameter, ModuleOutputVariable
from calibration.util.calibration_validators import SaveFormulationRequestValidator, CalibrationRunValidator, ModuleHydrofabricListValidator, \
    GenericResponseSerializer, LoadFormulationResponseSerializer, ErrorResponseSerializer, ExceptionResponseSerializer, ValidationErrorSerializer, \
    ValidationExceptionSerializer
from calibration.views import ngen_cal_input
from calibration.views.common import get_run, ResponseError

logger = logging.getLogger(__name__)

SLOTH = 'SLoTH'

# For testing
module_sample_data = {"modules": [
    {
        "module_name": "GC2D",
        "description": "description of module",
        "module_version": {
            "commit_hash": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "version_url": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Glacier"
        ]
    },
    {
        "module_name": "Noah-OWP-Modular",
        "description": "description of module",
        "module_version": {
            "commit_hash": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "version_url": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Snowmelt",
            "Evapotranspiration"
        ],
    },
    {
        "module_name": "Snow-17",
        "description": "description of module",
        "module_version": {
            "commit_hash": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "version_url": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Snowmelt"
        ]
    },
    {
        "module_name": "UEB",
        "description": "description of module",
        "module_version": {
            "commit_hash": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "version_url": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Snowmelt",
            "Evapotranspiration"
        ]
    },
    {
        "module_name": "CFE-S",
        "description": "description of module",
        "module_version": {
            "commit_hash": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "version_url": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Rainfall Runoff"
        ],
    },
    {
        "module_name": "CFE-X",
        "description": "description of module",
        "module_version": {
            "commit_hash": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "version_url": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Rainfall Runoff"
        ],
    },
    {
        "module_name": "PET",
        "description": "description of module",
        "module_version": {
            "commit_hash": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "version_url": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Evapotranspiration"
        ]
    },
    {
        "module_name": "TopModel",
        "description": "description of module",
        "module_version": {
            "commit_hash": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "version_url": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Rainfall Runoff"
        ]
    },
    {
        "module_name": "Sac-SMA",
        "description": "description of module",
        "module_version": {
            "commit_hash": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "version_url": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Rainfall Runoff"
        ]
    },
    {
        "module_name": "LASAM",
        "description": "description of module",
        "module_version": {
            "commit_hash": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "version_url": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Rainfall Runoff"
        ]
    },
    {
        "module_name": "SMP",
        "description": "description of module",
        "module_version": {
            "commit_hash": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "version_url": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Soil Moisture"
        ]
    },
    {
        "module_name": "SFT",
        "description": "description of module",
        "module_version": {
            "commit_hash": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "version_url": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Snowmelt"
        ]
    },
    {
        "module_name": "T-Route",
        "description": "description of module",
        "module_version": {
            "commit_hash": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "version_url": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Routing"
        ],
    },
    {
        "module_name": "SCHISM",
        "description": "description of module",
        "module_version": {
            "commit_hash": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "version_url": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Coastal"
        ]
    },
    {
        "module_name": "SFINCS",
        "description": "description of module",
        "module_version": {
            "commit_hash": "CFE:d290f1ee-6c54-4b01-90e6-d701748f0851",
            "version_url": "https://www.acme-corp.com",
            "version_date": "2024-08-29T09:12:33.001Z"
        },
        "groups": [
            "Coastal"
        ]
    }
]
}


@extend_schema(
    request=CalibrationRunValidator,
    responses={
        200: LoadFormulationResponseSerializer,
        400: PolymorphicProxySerializer(
            component_name='MultipleErrorResponse',
            serializers=[
                ValidationExceptionSerializer,
                ValidationErrorSerializer,
                ErrorResponseSerializer,
            ],
            resource_type_field_name=None
        ),
        500: ExceptionResponseSerializer
    },
    parameters=[
        OpenApiParameter(name='calibration_run_id', description='ID of the calibration run', required=True, type=int)
    ],
    description="Load formulation tab data"
)
@api_view(['GET', 'POST'])
# @permission_classes([AllowAny])()
def load_formulation_tab(request):
    try:
        print('user', request.user)
        if request.method == 'POST':
            data = json.loads(request.body or '{}')
        else:
            data = request.GET

        logger.debug(f'load_formulation_tab() request from {request.user} - {data}')

        validator = CalibrationRunValidator(data=data)
        validator.is_valid(raise_exception=True)

        calibration_run_id = validator.data.get('calibration_run_id')

        run, errorReturn = get_run(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn

        user_formulation_name = run.user_formulation_name

        get_modules_from_hydrofabric(run)

        modules = get_all_modules(run)

        # Unwrap the groups
        for m in modules:
            m['groups'] = json.loads(m['groups'])
        module_list = list(modules)

        use_sloth = run.use_sloth

        sloth_parameters = get_sloth_parameters(run) if use_sloth else []

        ngen_cal_input.ready_to_run(run)

        response = {'calibration_run_id': run.id, 'status': run.status.name, 'formulation_name': user_formulation_name,
                    "modules": module_list,
                    'use_sloth': use_sloth,
                    "sloth_parameters": sloth_parameters}
        response = {key: value for key, value in response.items() if value not in [None, '', [], {}]}

        serializer = LoadFormulationResponseSerializer(data=response)
        if not serializer.is_valid():
            return ResponseError(f'Data format error returning from load_formulation_tab() - {serializer.errors}',
                                 httpStatus=status.HTTP_500_INTERNAL_SERVER_ERROR)
        logger.debug(f'Returning to {request.user} from load_formulation_tab() - {serializer.data}')

        return Response(serializer.data)
    except JSONDecodeError as e:
        response = {'validation_error': 'JSON parsing error - ' + str(e)}
        serializer = ValidationErrorSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)
    except ValidationError as e:
        response = {'validation_error': str(e)}
        serializer = ValidationExceptionSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        response = {'exception': str(e)}
        serializer = ExceptionResponseSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def get_all_modules(run):
    return list(
        CalibrationFormulation.objects.filter(calibration_run=run).exclude(name=SLOTH)
        .only('name', 'groups', 'used_by_calibration_run')
        .values('name', 'groups', 'used_by_calibration_run')
    )


def get_my_modules(run):
    return list(
        CalibrationFormulation.objects.filter(calibration_run=run, used_by_calibration_run=True).exclude(name=SLOTH)
        .only('name')
        .values_list('name', flat=True)
    )


def get_sloth_parameters(run):
    sloth_parameters = list(
        CalibrationSlothParam.objects.filter(calibration_run=run)
        .only('param_name', 'param_count', 'param_type', 'param_units', 'param_location', 'param_value', 'maps_to_module',
              'maps_to_variable_name')
        .values(
            'param_name', 'param_count', 'param_type', 'param_units', 'param_location', 'param_value', 'maps_to_module__name',
            'maps_to_variable_name')
    )
    [sloth_param.update({'maps_to_module': sloth_param.pop('maps_to_module__name')}) for sloth_param in sloth_parameters]
    return sloth_parameters


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
        logger.debug(validator.errors)
        raise Exception(f'Module data from Hydrofabric is not in the expected format - {validator.errors}')

    module_data = validator.data.get('modules')
    new_modules_names = set(map(lambda mod: mod['module_name'], module_data))
    print('new_modules_names', new_modules_names)

    with transaction.atomic():
        if current_module_names != new_modules_names:
            # Only if the modules names have changed
            to_be_deleted = current_module_names - new_modules_names

            CalibrationFormulation.objects.filter(calibration_run=run, name__in=to_be_deleted).delete()

            # Create the new ones, if they don't already exist
            for m in module_data:
                CalibrationFormulation.objects.get_or_create(name=m['module_name'], calibration_run=run,
                                                             defaults={'groups': json.dumps(m['groups']),
                                                                       'description': m['description']})

        return


@extend_schema(
    request=SaveFormulationRequestValidator,
    responses={
        200: GenericResponseSerializer,
        400: PolymorphicProxySerializer(
            component_name='MultipleErrorResponse',
            serializers=[
                ValidationExceptionSerializer,
                ValidationErrorSerializer,
                ErrorResponseSerializer,
            ],
            resource_type_field_name=None
        ),
        500: ExceptionResponseSerializer
    },
    description="Save formulation tab data"
)
@api_view(['POST'])
# @permission_classes([AllowAny])
def save_formulation_tab(request):
    try:
        print('user', request.user)
        body = json.loads(request.body or '{}')
        logger.debug(f'save_formulation_tab() request from {request.user} - {body}')

        validator = SaveFormulationRequestValidator(data=body)
        validator.is_valid(raise_exception=True)

        new_module_names = set(validator.data.get('modules'))
        calibration_run_id = validator.data.get('calibration_run_id')
        user_formulation_name = validator.data.get('formulation_name')
        use_sloth = validator.data.get('use_sloth')
        sloth_parameters = validator.data.get('sloth_parameters')

        run, errorReturn = get_run(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn

        message = validate_modules(run, new_module_names)
        if message:
            return ResponseError(message)


        if not validate_formulation(run, new_module_names):
            return ResponseError(f'Invalid formulation -  {new_module_names}')

        run.user_formulation_name = user_formulation_name

        if use_sloth:
            new_module_names.add(SLOTH)
            if not sloth_parameters:
                return ResponseError("Invalid formulation -  You must enter SLoTH parameters")

        else:
            if sloth_parameters:
                return ResponseError('You must check the box to allow Sloth parameters to be specified')

        # Did we get the names from Hydrofabric
        if not CalibrationFormulation.objects.filter(calibration_run_id=run.id).exists():
            return ResponseError('Modules have not been received from Hydrofabric.  Should be done on load_formulation_tab')

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
                if not CalibrationFormulation.objects.filter(name=s['maps_to_module'], calibration_run_id=run.id,
                                                             used_by_calibration_run=True).exists():
                    return ResponseError(
                        "Sloth parameters contain an invalid module - '{}'.  This module has not been added to this run".format(s['apps_to_modules']))

            run.save()
            for s in sloth_parameters:
                # Get the new_module_names, so we can set it
                module = CalibrationFormulation.objects.filter(name=s['maps_to_module'], calibration_run_id=run.id).first()
                CalibrationSlothParam.objects.create(calibration_run=run, param_name=s['param_name'], param_count=s['param_count'],
                                                     param_type=s['param_type'],
                                                     param_units=s['param_units'], param_location=s['param_location'],
                                                     param_value=s['param_value'], maps_to_module=module,
                                                     maps_to_variable_name=s['maps_to_variable_name'])

            ngen_cal_input.ready_to_run(run)

            response = {'message': f'Calibration Run {run.id} updated', 'calibration_run_id': run.id, 'status': run.status.name}
            serializer = GenericResponseSerializer(data=response)
            if not serializer.is_valid():
                return ResponseError(f'Data format error returning from save_formulation_tab() - {serializer.errors}',
                                     httpStatus=status.HTTP_500_INTERNAL_SERVER_ERROR)
            logger.debug(f'Returning to {request.user} from save_formulation_tab() - {serializer.data}')
            return Response(serializer.data)
    except JSONDecodeError as e:
        response = {'validation_error': 'JSON parsing error - ' + str(e)}
        serializer = ValidationErrorSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)
    except ValidationError as e:
        response = {'validation_error': str(e)}
        serializer = ValidationExceptionSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        response = {'exception': str(e)}
        serializer = ExceptionResponseSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def validate_modules(run, module_names):
    # Check that all the module names are valid
    valid_names = set(CalibrationFormulation.objects.filter(calibration_run_id=run.id, name__in=module_names).values_list('name', flat=True))
    print('valid_names', valid_names)
    if module_names - valid_names:
        return f'Invalid modules - {module_names - valid_names}'
    return None


def validate_formulation(run, module_names):
    valid_formulations = NgenCalFormulation.objects.all().only('name', 'modules').values('name', 'modules')
    valid = False
    for valid_formulation in valid_formulations:
        valid_module_set = set(json.loads(valid_formulation['modules']))
        if valid_module_set == module_names:
            valid = True
            run.ngen_formulation_name = valid_formulation['name']
            break
    return valid
    # if not valid:
    #     return ResponseError("Invalid formulation-  '{}'".format(module_names))
