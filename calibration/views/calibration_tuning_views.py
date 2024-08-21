import csv
import io
import logging
import os
from datetime import MAXYEAR as MAXYEAR
from datetime import MINYEAR as MINYEAR
from datetime import datetime, timezone

from datetimerange import DateTimeRange
from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema, PolymorphicProxySerializer
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.models import CalibrationFormulation, ModuleOutputVariable, CalibrationTuneParameter
from calibration.util.calibration_validators import CalibrationRunSerializer, SaveTuningRequestSerializer, ModuleDataHydrofabricListSerializer, \
    LoadTuningResponseSerializer, GenericResponseSerializer, ErrorResponseSerializer, ExceptionResponseSerializer, \
    ValidationExceptionSerializer, UploadUserParameterFile, UserParameterFileUploadResponse
from calibration.views import ngen_cal_input
from calibration.views.common import get_run, ResponseError, handle_exceptions, validate_request, validate_response, CerfException

logger = logging.getLogger(__name__)

MIN_TIME = datetime(MAXYEAR, 12, 31, 11, 59, 59).replace(tzinfo=timezone.utc)
MAX_TIME = datetime(MINYEAR, 1, 1, 0, 0, 0).replace(tzinfo=timezone.utc)

# For testing
module_sample_data = {"modules": [
    {
        "module_name": "Noah-OWP-Modular",
        "module_output_variables": [
            {
                "name": "QINSUR",
                "description": "description of variable",
            },
            {
                "name": "ETRAN",
                "description": "description of variable",
            },
            {
                "name": "QSEVA",
                "description": "description of variable",
            },
        ],
        "module_parameters": [
            {
                "name": "parameter1",
                "data_type": "double",
                "description": "description of variable",
                "initial_value": 0.0,
                "minimum": 0.0,
                "maximum": 0.0
            },

            {
                "name": "parameter2",
                "data_type": "double",
                "description": "description of variable",
                "initial_value": 0.0,
                "minimum": 0.0,
                "maximum": 0.0
            },
            {
                "name": "parameter3",
                "data_type": "double",
                "description": "description of variable",
                # "units": "m/s",
                "initial_value": 0.0,
                "minimum": 0.0,
                "maximum": 0.0
            }

        ]
    },
]
}


@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: LoadTuningResponseSerializer,
        400: PolymorphicProxySerializer(
            component_name='MultipleErrorResponse',
            serializers=[
                ValidationExceptionSerializer,
                ErrorResponseSerializer,
            ],
            resource_type_field_name=None
        ),
        500: ExceptionResponseSerializer
    },
    parameters=[
        OpenApiParameter(name='calibration_run_id', description='ID of the calibration run', required=True, type=int)
    ],
    description="Load tuning tab data"
)
@api_view(['GET', 'POST'])
@handle_exceptions
# @permission_classes([AllowAny])
def load_tuning_tab(request):
    data = request.data if request.method == 'POST' else request.query_params

    logger.debug(f'load_tuning_tab() request from {request.user} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.data.get('calibration_run_id')

    run, errorReturn = get_run(calibration_run_id, request.user)
    if errorReturn:
        return errorReturn

    calibration_times, validation_times = get_times(run)

    output_variable_to_calibrate = get_output_variable_to_calibrate(run)

    # Get the list of modules for this Run
    modules = CalibrationFormulation.objects.filter(calibration_run=run, used_by_calibration_run=True)

    module_list = []
    if modules:
        # Only do this if modules have been saved in the formulation tab

        # print('calling hydrofabric with', modules)
        get_module_data_from_hydrofabric(run, modules)

        # For each module, get the Parameters and Output Variables
        module_list = get_parameters_and_output_variables(modules)

    time_range = get_time_range(run)

    ngen_cal_input.ready_to_run(run)

    response = {'calibration_run_id': run.id, 'status': run.status.name,
                'modules': module_list,
                'user_parameter_filename': run.user_parameter_filename,
                'calibration_times': calibration_times,
                'validation_times': validation_times, 'automatic_validation': run.automatic_validation,
                'time_range': time_range,
                'output_variable_to_calibrate': output_variable_to_calibrate}
    response = {key: value for key, value in response.items() if value not in [None, '', [], {}]}

    response_validator, error_response = validate_response(LoadTuningResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user} from load_tuning_tab() - {response_validator.data}')

    return Response(response_validator.data)


def get_output_variable_to_calibrate(run):
    return {
        'module': run.module_output_variable.calibration_formulation.name,
        'name': run.module_output_variable.name
    } if run.module_output_variable else None


def get_parameters_and_output_variables(modules):
    module_list = []
    for m in modules:
        calibrationTuneParameters = (CalibrationTuneParameter.objects.filter(calibration_formulation=m))

        parameters = list(calibrationTuneParameters.values('name', 'minimum', 'maximum', 'initial_value', 'data_type', 'description'))
        module_entry = {'name': m.name, 'parameters': parameters,
                        'output_variables': list(m.output_variables.all().only('name', 'description').values('name', 'description'))}

        module_list.append(module_entry)
        return module_list


def get_parameters_for_export(modules):
    parameter_list = []
    for m in modules:
        calibrationTuneParameters = list(CalibrationTuneParameter.objects.filter(calibration_formulation=m)
                                         .only('name', 'minimum', 'maximum', 'initial_value')
                                         .values('name', 'minimum', 'maximum', 'initial_value'))

        for p in calibrationTuneParameters:
            p['module'] = m.name
            parameter_list.append(p)

    return parameter_list


def get_time_range(run):
    # Get data range intersection of observational and forcing data if we don't already have it
    time_range = None
    if (run.observational_file_path and run.forcing_dir_path
            and run.time_range_start and run.time_range_end):
        daterange = get_date_range_intersection(run.observational_file_path, run.forcing_dir_path)
        run.time_range_start = daterange.start_datetime
        run.time_range_end = daterange.end_datetime
        time_range = {'start_time': run.time_range_start, 'end_time': run.time_range_end}
        run.save()

    return time_range


def get_times(run):
    calibration_times = {}
    validation_times = {}
    # These are all or nothing.  So if this first one exists, we'll assume they all do
    if run.calibration_start_period:
        calibration_times['simulation_start_time'] = run.calibration_start_period
        calibration_times['simulation_end_time'] = run.calibration_end_period
        calibration_times['calibration_start_time'] = run.calibration_eval_start_period
        calibration_times['calibration_end_time'] = run.calibration_eval_end_period
    if run.automatic_validation and run.validation_start_period:
        validation_times['simulation_start_time'] = run.validation_start_period
        validation_times['simulation_end_time'] = run.validation_end_period
        validation_times['validation_start_time'] = run.validation_eval_start_period
        validation_times['validation_end_time'] = run.validation_eval_end_period
    return calibration_times, validation_times


# @permission_classes([AllowAny])()
def get_module_data_from_hydrofabric(run, modules):
    # Get this from hydrofabric
    # modules_request = {"modules":modules}
    # response = requests.post(settings.HYDROFABRIC_URL, json=modules_request)
    # module_data = response.json()

    validator = ModuleDataHydrofabricListSerializer(data=module_sample_data)
    if not validator.is_valid():
        logger.error(validator.errors)
        raise CerfException(f'Module metadata from Hydrofabric is not in the expected format - {validator.errors}')

    # print('getting metadata from hydrofabric')
    module_data = module_sample_data.get("modules")

    # Save the output variables and parameters for each module
    # TODO We need to ensure that the data from Hydrofabric contains all the modules we asked for
    with transaction.atomic():
        for m in module_data:
            # Get the modules object from our list
            module = modules.filter(name=m['module_name']).first()
            # print('module', module)

            # Save output variables
            outputs = m['module_output_variables']
            o: dict
            for o in outputs:
                ModuleOutputVariable.objects.update_or_create(name=o['name'], calibration_formulation=module,
                                                              defaults={'description': o['description']})
            # Save parameters
            # print('getting parameters for', m)
            parameters = m['module_parameters']
            # print('parameters from Hydro', parameters)
            for p in parameters:
                CalibrationTuneParameter.objects.update_or_create(name=p['name'], calibration_formulation=module,
                                                                  defaults={'data_type': p['data_type'],
                                                                            'description': p['description'], 'minimum': p['minimum'],
                                                                            'maximum': p['maximum']})

        # run.got_module_data_from_hydrofabric = True
        run.save()

    return


@extend_schema(
    request=SaveTuningRequestSerializer,
    responses={
        200: GenericResponseSerializer,
        400: PolymorphicProxySerializer(
            component_name='MultipleErrorResponse',
            serializers=[
                ValidationExceptionSerializer,
                ErrorResponseSerializer,
            ],
            resource_type_field_name=None
        ),
        500: ExceptionResponseSerializer
    },
    description="Save tuning tab data"
)
@api_view(['POST'])
# @permission_classes([AllowAny])
@handle_exceptions
def save_tuning_tab(request):
    data = request.data
    logger.debug(f'save_tuning_tab() request from {request.user} - {data}')

    validator, error_return = validate_request(SaveTuningRequestSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.data.get('calibration_run_id')
    automatic_validation = validator.data.get('automatic_validation')
    calibration_times = validator.data.get('calibration_times')
    validation_times = validator.data.get('validation_times')
    parameters = validator.data.get('parameters')

    output_variable_to_calibrate = validator.data.get('output_variable_to_calibrate')

    run, errorReturn = get_run(calibration_run_id, request.user)
    if errorReturn:
        return errorReturn

    run.automatic_validation = automatic_validation

    save_times(run, calibration_times, validation_times)

    print('parameters', parameters)
    message = validate_parameters(run, parameters)
    if message is not None:
        return ResponseError(message)

    message = save_output_variable(run, output_variable_to_calibrate)
    if message is not None:
        return ResponseError(message)

    with transaction.atomic():
        run.save()
        save_parameters(run, parameters)

    ngen_cal_input.ready_to_run(run)

    response = {'message': f'Calibration Run {run.id} updated', 'calibration_run_id': run.id, 'status': run.status.name}

    response_validator, error_response = validate_response(GenericResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user} from save_tuning_tab() - {response_validator.data}')
    return Response(response_validator.data)


@extend_schema(
    request=UploadUserParameterFile,
    responses={
        200: GenericResponseSerializer,
        400: PolymorphicProxySerializer(
            component_name='MultipleErrorResponse',
            serializers=[
                ValidationExceptionSerializer,
                ErrorResponseSerializer,
            ],
            resource_type_field_name=None
        ),
        500: ExceptionResponseSerializer
    },
    description="Allow user to upload observational data"
)
@api_view(['POST'])
# @permission_classes([AllowAny])
@handle_exceptions
def upload_user_parameters(request):
    data = request.data
    logger.debug(f'upload_user_parameter_file() request from {request.user} - {data}')

    validator, error_return = validate_request(UploadUserParameterFile, data, context={'request': request})
    if error_return:
        return error_return

    calibration_run_id = validator.data.get('calibration_run_id')

    run, errorReturn = get_run(calibration_run_id, request.user)
    if errorReturn:
        return errorReturn

    files = request.FILES.getlist('user_parameter_file')

    parameter_file = files[0]
    file_contents = parameter_file.read().decode('utf-8')

    # Strip trailing whitespace from each line
    file_contents = "\n".join([line.strip() for line in file_contents.splitlines()])

    # Read the CSV data
    parsed_data = list(csv.DictReader(io.StringIO(file_contents), delimiter=' ', skipinitialspace=True))

    run.user_parameter_filename = parameter_file.name
    run.save()

    response = {'message': f"Parameter file '{parameter_file.name}' saved for Calibration Run {run.id}", 'calibration_run_id': run.id,
                'user_parameter_file': list(parsed_data)}

    response_validator, error_response = validate_response(UserParameterFileUploadResponse, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user} from upload_user_parameter_file() - {response_validator.data}')
    return Response(response_validator.data)


def save_times(run, calibration_times, validation_times):
    run.calibration_start_period = datetime.fromisoformat(calibration_times['simulation_start_time']) if calibration_times else None
    run.calibration_end_period = datetime.fromisoformat(calibration_times['simulation_end_time']) if calibration_times else None
    run.calibration_eval_start_period = datetime.fromisoformat(calibration_times['calibration_start_time']) if calibration_times else None
    run.calibration_eval_end_period = datetime.fromisoformat(calibration_times['calibration_end_time']) if calibration_times else None

    if run.automatic_validation:
        run.validation_start_period = datetime.fromisoformat(validation_times['simulation_start_time']) if validation_times else None
        run.validation_end_period = datetime.fromisoformat(validation_times['simulation_end_time']) if validation_times else None
        run.validation_eval_start_period = datetime.fromisoformat(validation_times['validation_start_time']) if validation_times else None
        run.validation_eval_end_period = datetime.fromisoformat(validation_times['validation_end_time']) if validation_times else None


def validate_parameters(run, parameters):
    if parameters:
        if not CalibrationTuneParameter.objects.filter(calibration_formulation__calibration_run=run).exists():
            return 'Modules and/or CalibrationTuneParameters have not been received from Hydrofabric.  Should be done on load_formulation_tab and load_tuning_tab.'
        # Make sure the parameters we are trying to save exist
        for p in parameters:
            if not CalibrationTuneParameter.objects.filter(name=p['name'], calibration_formulation__name=p['module']).exists():
                return "Invalid parameter '{}' specified for module '{}'".format(p['name'], p['module'])
    return None


def save_output_variable(run, output_variable_to_calibrate):
    if output_variable_to_calibrate:
        module_with_output_variable = CalibrationFormulation.objects.filter(name=output_variable_to_calibrate['module'],
                                                                            calibration_run=run).first()
        if not module_with_output_variable:
            return "Module '{}' is not part of calibration run {}".format(output_variable_to_calibrate['module'], run.id)
        module_output_variable = module_with_output_variable.output_variables.all().filter(
            name=output_variable_to_calibrate['name']).first()
        if not module_output_variable:
            return "Module output variable '{}' not found in module '{}' for this run".format(
                output_variable_to_calibrate['name'], output_variable_to_calibrate['module'])

        run.module_output_variable = module_output_variable
        return None


def save_parameters(run, parameters):
    if parameters:
        for p in parameters:
            (CalibrationTuneParameter.objects
             .filter(name=p['name'], calibration_formulation__name=p['module'], calibration_formulation__calibration_run=run)
             .update(minimum=p['minimum'], maximum=p['maximum'], initial_value=p['initial_value']))


# Reads a CSV file and gets the date field from the first column.  Then computes the min/max to construct a date range
def get_csv_daterange(file):
    max_time = MAX_TIME
    min_time = MIN_TIME
    with open(file, 'r') as f:
        csv_reader = csv.reader(f, delimiter=',')
        # skip the header
        next(csv_reader, None)
        for row in csv_reader:
            timestamp = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
            max_time = max(max_time, timestamp)
            min_time = min(min_time, timestamp)

    return DateTimeRange(min_time, max_time)


def get_forcing_date_range(forcing_dir_path):
    # dir = '/home/peter.a.kronenberg/ngen-cal-work/forcing/Gage_01123000/'
    # Get all files in the dir
    timerange = None
    for file in os.listdir(forcing_dir_path):
        new_range = get_csv_daterange(os.path.join(forcing_dir_path, file))
        if timerange:
            timerange = timerange.encompass(new_range)
        else:
            timerange = new_range

    return timerange


def get_observation_date_range(observational_filepath):
    # obs_file = '/home/peter.a.kronenberg/ngen-cal-work/observation/01123000_hourly_discharge.csv'
    return get_csv_daterange(observational_filepath)


def get_date_range_intersection(observational_file_path, forcing_dir_path):
    # The get latest start data and the earlier end date
    obs_range = get_observation_date_range(observational_file_path)
    logger.debug(f'obs_range: {obs_range}')
    forcing_range = get_forcing_date_range(forcing_dir_path)
    logger.debug(f'forcing_range: {forcing_range}')
    return obs_range.intersection(forcing_range)
