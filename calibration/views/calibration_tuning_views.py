import io
import logging
from datetime import MAXYEAR as MAXYEAR
from datetime import MINYEAR as MINYEAR
from datetime import datetime, timezone
from pathlib import Path

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
from calibration.views.common import get_run, ResponseError, handle_exceptions, validate_response, CerfException, validate_request
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

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_run(calibration_run_id, request.user)
    if error_return:
        return error_return

    # Get the list of modules for this Run
    modules = CalibrationFormulation.objects.filter(calibration_run=run, used_by_calibration_run=True)

    time_range = get_time_range(run)

    module_list = []
    if modules and run.gage:
        # Only do this if modules have been saved in the formulation tab and we have a gage

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
    for m in modules.prefetch_related('calibrationparameter_set', 'output_variables'):
        calibration_parameters = m.calibrationparameter_set.values(
            'name', 'minimum', 'maximum', 'initial_value', 'units', 'data_type', 'description', 'user_selected_for_tuning'
        )
        output_variables = m.output_variables.values('name', 'description')
        module_entry = {
            'name': m.name,
            'parameters': list(calibration_parameters),
            'output_variables': list(output_variables)
        }
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
        if run.time_range_start != daterange.start_datetime or run.time_range_end != daterange.end_datetime:
            run.time_range_start = daterange.start_datetime
            run.time_range_end = daterange.end_datetime
            run.save(update_fields=['time_range_start', 'time_range_end'])
        return {'start_time': run.time_range_start, 'end_time': run.time_range_end}

    return {}


def get_valid_path(source, hydrofabric_path, upload_enum, get_path_func):
    job_specific_file = get_path_func()
    # print('get_valid_path', source, hydrofabric_path, upload_enum, get_path_func())

    if source:
        if source == upload_enum.from_enum(upload_enum):
            # Check job-specific path first
            if Path(job_specific_file).exists():
                return job_specific_file
        # If not found or source is different, check the hydrofabric path
        if hydrofabric_path and Path(hydrofabric_path).exists():
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

    calibration_run_id = validator.get('calibration_run_id')
    automatic_validation = validator.get('automatic_validation')
    calibration_times = validator.get('calibration_times')
    validation_times = validator.get('validation_times')
    parameters = validator.get('parameters')

    output_variable_to_calibrate = validator.get('output_variable_to_calibrate')

    run, error_return = get_run(calibration_run_id, request.user)
    if error_return:
        return error_return

    run.automatic_validation = automatic_validation

    error_message = validate_and_save_times(run, calibration_times, validation_times)
    if error_message:
        return ResponseError(error_message)

    error_message = validate_parameters(run, parameters)
    if error_message:
        return ResponseError(error_message)

    error_message = save_output_variable(run, output_variable_to_calibrate)
    if error_message:
        return ResponseError(error_message)

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
@handle_exceptions
def upload_user_parameters(request):
    data = request.data
    logger.debug(f'upload_user_parameter_file() request from {request.user} - {data}')

    validator, error_return = validate_request(UploadUserParameterFile, data, context={'request': request})
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_run(calibration_run_id, request.user)
    if error_return:
        return error_return

    files = request.FILES.getlist('user_parameter_file')

    parameter_file = files[0]
    file_contents = parameter_file.read().decode('utf-8')

    # Detect delimiter type (space or comma) by checking the first few rows
    if ',' in file_contents.splitlines()[1]:
        delimiter = ','
        logger.debug("Detected comma delimiter.")
    else:
        delimiter = r'\s+'
        logger.debug("Detected space delimiter.")

    try:
        # Handle file parsing based on detected delimiter
        df = pd.read_csv(io.StringIO(file_contents), sep=delimiter, engine='python', skipinitialspace=True)
    except pd.errors.ParserError:
        return Response({'error': 'The uploaded file could not be parsed as space-separated or comma-separated.'}, status=400)

    # Strip any leading/trailing whitespace in the column headers
    df.columns = df.columns.str.strip()

    # Log detected columns for debugging
    logger.debug(f"Detected columns: {df.columns.tolist()}")

    # Ensure that the DataFrame contains the correct columns
    required_columns = ['param', 'min', 'max', 'init', 'model']
    missing_cols = [col for col in required_columns if col not in df.columns]

    if missing_cols:
        # Log the actual DataFrame to inspect it
        logger.debug(f"DataFrame content:\n{df.head()}")
        return ResponseError(f'Missing required columns: {missing_cols}')

    # Ensure numeric columns are properly converted to floats and validate values
    invalid_values = {}
    for col in ['min', 'max', 'init']:
        df[col] = pd.to_numeric(df[col], errors='coerce')  # Coerce invalid values to NaN
        invalid_rows = df[df[col].isna()]
        if not invalid_rows.empty:
            invalid_values[col] = invalid_rows.index.tolist()

    if invalid_values:
        error_message = f"Invalid values found in columns: {invalid_values}"
        logger.debug(error_message)
        return Response({'error': error_message}, status=400)

    logger.debug(f"Parsed DataFrame after stripping and numeric conversion: \n{df}")

    # Convert DataFrame to a list of dictionaries
    parsed_data = df.to_dict(orient='records')

    run.user_parameter_filename = parameter_file.name
    run.save()

    response = {
        'message': f"Parameter file '{parameter_file.name}' saved for Calibration Run {run.id}",
        'calibration_run_id': run.id,
        'user_parameter_file': parsed_data
    }

    response_validator, error_response = validate_response(UserParameterFileUploadResponse, response)
    if error_response:
        return error_response

    logger.debug(f'Returning to {request.user} from upload_user_parameter_file() - {response_validator.data}')
    return Response(response_validator.data)


def validate_and_save_times(run, calibration_times, validation_times):
    time_range = DateTimeRange(run.time_range_start, run.time_range_end)
    if calibration_times['simulation_start_time'] not in time_range or calibration_times['simulation_end_time'] not in time_range:
        return f"Calibration simulation times must be contained without the intersection of forcing data and observational data - {time_range}"
    if validation_times['simulation_start_time'] not in time_range or validation_times['simulation_end_time'] not in time_range:
        return f"Validation simulation times must be contained without the intersection of forcing data and observational data - {time_range}"

    run.calibration_start_period = datetime.fromisoformat(calibration_times['simulation_start_time']) if calibration_times else None
    run.calibration_end_period = datetime.fromisoformat(calibration_times['simulation_end_time']) if calibration_times else None
    run.calibration_eval_start_period = datetime.fromisoformat(calibration_times['calibration_start_time']) if calibration_times else None
    run.calibration_eval_end_period = datetime.fromisoformat(calibration_times['calibration_end_time']) if calibration_times else None

    if run.automatic_validation:
        run.validation_start_period = datetime.fromisoformat(validation_times['simulation_start_time']) if validation_times else None
        run.validation_end_period = datetime.fromisoformat(validation_times['simulation_end_time']) if validation_times else None
        run.validation_eval_start_period = datetime.fromisoformat(validation_times['validation_start_time']) if validation_times else None
        run.validation_eval_end_period = datetime.fromisoformat(validation_times['validation_end_time']) if validation_times else None

    return None


def validate_parameters(run, parameters):
    if parameters:
        if not CalibrationParameter.objects.filter(calibration_formulation__calibration_run=run).exists():
            return 'Modules and/or CalibrationParameters have not been received from Hydrofabric.  Should be done on load_formulation_tab and load_tuning_tab.'
        # Make sure the parameters we are trying to save exist
        for p in parameters:
            if not CalibrationParameter.objects.filter(name=p['name'], calibration_formulation__name=p['module'], calibration_formulation__calibration_run=run).exists():
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
        parameters_to_update = []
        for p in parameters:
            calibration_param = CalibrationParameter.objects.filter(
                name=p['name'],
                calibration_formulation__name=p['module'],
                calibration_formulation__calibration_run=run
            ).first()
            if calibration_param:
                calibration_param.minimum = p['minimum']
                calibration_param.maximum = p['maximum']
                calibration_param.initial_value = p['initial_value']
                calibration_param.user_selected_for_tuning = True
                parameters_to_update.append(calibration_param)

        CalibrationParameter.objects.bulk_update(parameters_to_update, ['minimum', 'maximum', 'initial_value', 'user_selected_for_tuning'])


# Reads a CSV file and gets the date field from the first column. Then computes the min/max to construct a date range
def get_csv_daterange(file):
    try:
        if not Path(file).exists():
            raise CerfException(f"File {file} does not exist")
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
    except Exception as e:
        # This was happening in dev because people were uploading bogus files.  Shouldn't really happen in prod
        raise CerfException(f'Error reading file {file}: {e}')


def get_forcing_date_range(forcing_dir_path):
    # Get all files in the directory
    timerange = None
    for file in Path(forcing_dir_path).iterdir():
        if file.is_file():
            new_range = get_csv_daterange(Path(forcing_dir_path) / file)
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
