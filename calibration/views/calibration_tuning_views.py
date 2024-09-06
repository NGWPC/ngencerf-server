import csv
import io
import logging
import os
from datetime import MAXYEAR as MAXYEAR
from datetime import MINYEAR as MINYEAR
from datetime import datetime, timezone

import pandas as pd
from datetimerange import DateTimeRange
from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema, OpenApiResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.enums import ObservationalSourceEnum, ForcingSourceEnum
from calibration.models import CalibrationFormulation, CalibrationParameter
from calibration.util.calibration_validators import CalibrationRunSerializer, SaveTuningRequestSerializer, LoadTuningResponseSerializer, \
    GenericResponseSerializer, ErrorResponseSerializer, UploadUserParameterFile, UserParameterFileUploadResponse
from calibration.util.ngen_locations import get_observational_file_for_job, get_forcing_dir_for_job
from calibration.views import ngen_cal_input
from calibration.views.common import get_run, ResponseError, handle_exceptions, validate_request, validate_response
from calibration.views.hydrofabric import get_module_data_from_hydrofabric

logger = logging.getLogger(__name__)

MIN_TIME = datetime(MAXYEAR, 12, 31, 11, 59, 59).replace(tzinfo=timezone.utc)
MAX_TIME = datetime(MINYEAR, 1, 1, 0, 0, 0).replace(tzinfo=timezone.utc)


@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: LoadTuningResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: ErrorResponseSerializer
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

    # Get the list of modules for this Run
    modules = CalibrationFormulation.objects.filter(calibration_run=run, used_by_calibration_run=True)

    time_range = get_time_range(run)

    module_list = []
    if modules:
        # Only do this if modules have been saved in the formulation tab

        # print('calling hydrofabric with', modules)
        get_module_data_from_hydrofabric(run, modules)

        # For each module, get the Parameters and Output Variables
        module_list = get_parameters_and_output_variables(modules)

    ngen_cal_input.ready_to_run(run)

    response = {'calibration_run_id': run.id, 'status': run.status.name, 'modules': module_list, 'time_range': time_range}

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
        calibrationParameters = (CalibrationParameter.objects.filter(calibration_formulation=m))

        parameters = list(
            calibrationParameters.values('name', 'minimum', 'maximum', 'initial_value', 'data_type', 'description', 'user_selected_for_tuning'))
        module_entry = {'name': m.name, 'parameters': parameters,
                        'output_variables': list(m.output_variables.all().only('name', 'description').values('name', 'description'))}

        module_list.append(module_entry)
        return module_list


def get_parameters_for_export(modules):
    parameter_list = []
    for m in modules:
        calibrationParameters = list(CalibrationParameter.objects.filter(calibration_formulation=m)
                                     .values('name', 'minimum', 'maximum', 'initial_value'))

        for p in calibrationParameters:
            p['module'] = m.name
            parameter_list.append(p)

    return parameter_list


def get_time_range(run):
    """
    Get data range intersection of observational and forcing data if we don't already have it
    :param run:
    :return:
    """
    observation_path = get_valid_path(run.observational_source, run.observational_hydrofabric_file_path, ObservationalSourceEnum.UPLOAD,
                                      lambda: get_observational_file_for_job(run))

    forcing_path = get_valid_path(run.forcing_source, run.forcing_hydrofabric_dir_path, ForcingSourceEnum.UPLOAD,
                                  lambda: get_forcing_dir_for_job(run))

    # If both paths are available, calculate intersection and update run
    if observation_path and forcing_path:
        daterange = get_date_range_intersection(observation_path, forcing_path)
        run.time_range_start = daterange.start_datetime
        run.time_range_end = daterange.end_datetime
        run.save()
        return {'start_time': run.time_range_start, 'end_time': run.time_range_end}

    return {}


def get_valid_path(source, hydrofabric_path, upload_enum, get_path_func):
    if source:
        if source.name == upload_enum.name:
            hydrofabric_path = get_path_func()
        if hydrofabric_path and os.path.exists(hydrofabric_path):
            return hydrofabric_path
    return None


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


@extend_schema(
    request=SaveTuningRequestSerializer,
    responses={
        200: GenericResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: ErrorResponseSerializer
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
        200: UserParameterFileUploadResponse,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: ErrorResponseSerializer
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
        if not CalibrationParameter.objects.filter(calibration_formulation__calibration_run=run).exists():
            return 'Modules and/or CalibrationParameters have not been received from Hydrofabric.  Should be done on load_formulation_tab and load_tuning_tab.'
        # Make sure the parameters we are trying to save exist
        for p in parameters:
            if not CalibrationParameter.objects.filter(name=p['name'], calibration_formulation__name=p['module']).exists():
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
            (CalibrationParameter.objects
             .filter(name=p['name'], calibration_formulation__name=p['module'], calibration_formulation__calibration_run=run)
             .update(minimum=p['minimum'], maximum=p['maximum'], initial_value=p['initial_value'], user_selected_for_tuning=True))


# Reads a CSV file and gets the date field from the first column. Then computes the min/max to construct a date range
def get_csv_daterange(file):
    # Read the CSV file, assuming the first column contains date information
    df = pd.read_csv(file, delimiter=',', parse_dates=[0])

    # Ensure the first column is datetime without timezone initially
    df.iloc[:, 0] = pd.to_datetime(df.iloc[:, 0], errors='coerce')  # Handles invalid dates gracefully

    # Find the min and max date (without timezone info)
    min_time = df.iloc[:, 0].min()
    max_time = df.iloc[:, 0].max()

    # Convert the min and max times to UTC after computation
    min_time = min_time.replace(tzinfo=timezone.utc)
    max_time = max_time.replace(tzinfo=timezone.utc)

    return DateTimeRange(min_time, max_time)


#
# # Reads a CSV file and gets the date field from the first column.  Then computes the min/max to construct a date range
# def get_csv_daterange(file):
#     logger.info(f'getting date range for file {file}')
#     max_time = MAX_TIME
#     min_time = MIN_TIME
#     with open(file, 'r', buffering=32768) as f:
#         csv_reader = csv.reader(f, delimiter=',')
#         # skip the header
#         next(csv_reader, None)
#         for row in csv_reader:
#             timestamp = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
#             max_time = max(max_time, timestamp)
#             min_time = min(min_time, timestamp)
#
#     logger.info(f'Returning date range for {file}')
#     return DateTimeRange(min_time, max_time)


def get_forcing_date_range(forcing_dir_path):
    # Get all files in the directory
    timerange = None
    for file in os.listdir(forcing_dir_path):
        new_range = get_csv_daterange(os.path.join(forcing_dir_path, file))
        if timerange:
            timerange = timerange.encompass(new_range)
        else:
            timerange = new_range

    return timerange


def get_observation_date_range(observational_filepath):
    return get_csv_daterange(observational_filepath)


def get_date_range_intersection(observational_file_path, forcing_dir_path):
    # The get latest start data and the earlier end date
    obs_range = get_observation_date_range(observational_file_path)
    logger.debug(f'obs_range: {obs_range}')
    forcing_range = get_forcing_date_range(forcing_dir_path)
    logger.debug(f'forcing_range: {forcing_range}')
    return obs_range.intersection(forcing_range)
