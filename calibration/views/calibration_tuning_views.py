import io
import logging
from datetime import MAXYEAR as MAXYEAR
from datetime import MINYEAR as MINYEAR
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List, Tuple

import pandas as pd
from datetimerange import DateTimeRange
from django.db import transaction
from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiParameter, extend_schema, OpenApiResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.enums import ObservationalSourceEnum, ForcingSourceEnum, StatusEnum
from calibration.models import CalibrationFormulation, CalibrationParameter, CalibrationRun, ModuleOutputVariable
from calibration.util.caching import get_cached_module_by_name
from calibration.util.calibration_validators import CalibrationRunSerializer, SaveTuningRequestSerializer, LoadTuningResponseSerializer, \
    GenericResponseSerializer, ErrorResponseSerializer, UploadUserParameterFile, UserParameterFileUploadResponse
from calibration.util.ngen_locations import get_observational_file_for_job, get_forcing_dir_for_job
from calibration.views import ngen_cal_input
from calibration.views.common import get_calibration_run, ResponseError, handle_exceptions, validate_response, CerfException, validate_request, \
    get_valid_path, format_datetime

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
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
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
    data = request.data if request.method == 'POST' else request.query_params.dict()

    logger.debug(f'load_tuning_tab() request from {request.user.email} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=list(StatusEnum))
    if error_return:
        return error_return

    time_range = get_time_range(run)

    # Get the list of modules for this Run
    formulations = CalibrationFormulation.objects.filter(calibration_run=run).prefetch_related(
        'calibrationparameter_set', 'output_variables'
    )

    # For each module, get the Parameters and Output Variables
    module_list = get_parameters_and_output_variables(formulations)

    ngen_cal_input.ready_to_run(run)

    response = {'calibration_run_id': run.id, 'status': run.status.name, 'modules': module_list, 'time_range': time_range}

    response_validator, error_response = validate_response(LoadTuningResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user.email} from load_tuning_tab() - {response_validator.data}')

    return Response(response_validator.data)


def has_user_selected_tuning_parameters(modules: QuerySet[CalibrationFormulation]) -> bool:
    for m in modules.prefetch_related('calibrationparameter_set'):
        if m.calibrationparameter_set.exists():
            return True
    return False


def get_parameters_and_output_variables(modules: QuerySet[CalibrationFormulation]) -> List[Dict[str, str | List[Dict[str, str | float | int]]]]:
    module_list = []

    for formulation in modules.prefetch_related('calibrationparameter_set', 'output_variables'):
        module = get_cached_module_by_name(formulation.module.name)

        if module:
            calibration_parameters = formulation.calibrationparameter_set.values(
                'name', 'minimum', 'maximum', 'initial_value', 'units', 'data_type', 'description', 'user_selected_for_tuning'
            )
            output_variables = formulation.output_variables.values('name', 'description')
            module_entry = {
                'name': formulation.module.name,
                'parameters': list(calibration_parameters),
                'output_variables': list(output_variables)
            }
            module_list.append(module_entry)
    return module_list


def get_parameters_for_export(modules: QuerySet[CalibrationFormulation]) -> List[Dict[str, str | float]]:
    parameter_list = []
    for m in modules:
        calibrationParameters = list(CalibrationParameter.objects.filter(calibration_formulation=m, user_selected_for_tuning=True)
                                     .values('name', 'minimum', 'maximum', 'initial_value'))

        for p in calibrationParameters:
            p['module'] = m.module.name
            parameter_list.append(p)

    return parameter_list


def get_time_range(run: CalibrationRun) -> Dict[str, datetime | None]:
    """
    Get data range intersection of observational and forcing data if we don't already have it
    :param run:
    :return:
    """
    observation_path = get_valid_path(run.observational_source, run.observational_hydrofabric_file_path,
                                      ObservationalSourceEnum.UPLOAD,
                                      lambda: get_observational_file_for_job(run))

    forcing_path = get_valid_path(run.forcing_source, run.forcing_hydrofabric_dir_path,
                                  ForcingSourceEnum.UPLOAD,
                                  lambda: get_forcing_dir_for_job(run))

    # If both paths are available, calculate intersection and update run
    if observation_path and forcing_path:
        daterange = get_date_range_intersection(observation_path, forcing_path)
        logger.debug(f'New date range: {daterange}')
        if daterange:
            # Only update if it has changed
            if run.time_range_start != daterange.start_datetime or run.time_range_end != daterange.end_datetime:
                run.time_range_start = daterange.start_datetime
                run.time_range_end = daterange.end_datetime
                run.save(update_fields=['time_range_start', 'time_range_end'])
        return {'start_time': run.time_range_start, 'end_time': run.time_range_end}
    else:
        # We don't have the data,
        return {}


def get_times(run: CalibrationRun) -> Tuple[Dict[str, datetime], Dict[str, datetime]]:
    calibration_times = {}
    validation_times = {}
    # These are all or nothing.  So if this first one exists, we'll assume they all do
    if run.calibration_start_period:
        calibration_times = {
            'simulation_start_time': run.calibration_start_period,
            'simulation_end_time': run.calibration_end_period,
            'calibration_start_time': run.calibration_eval_start_period,
            'calibration_end_time': run.calibration_eval_end_period
        }
    if run.automatic_validation and run.validation_start_period:
        validation_times = {
            'simulation_start_time': run.validation_start_period,
            'simulation_end_time': run.validation_end_period,
            'validation_start_time': run.validation_eval_start_period,
            'validation_end_time': run.validation_eval_end_period
        }
    return calibration_times, validation_times


@extend_schema(
    request=SaveTuningRequestSerializer,
    responses={
        200: GenericResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Save tuning tab data"
)
@api_view(['POST'])
# @permission_classes([AllowAny])f
@handle_exceptions
def save_tuning_tab(request):
    data = request.data
    logger.debug(f'save_tuning_tab() request from {request.user.email} - {data}')

    validator, error_return = validate_request(SaveTuningRequestSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    automatic_validation = validator.get('automatic_validation')
    calibration_times = validator.get('calibration_times')
    validation_times = validator.get('validation_times')
    parameters = validator.get('parameters')

    output_variable_to_calibrate = validator.get('output_variable_to_calibrate')

    run, error_return = get_calibration_run(calibration_run_id, request.user)
    if error_return:
        return error_return

    run.automatic_validation = automatic_validation

    error_message = validate_and_save_times(run, calibration_times, validation_times)
    if error_message:
        return ResponseError(error_message)

    if (parameters or output_variable_to_calibrate) and not run.gage:
        return ResponseError('Parameters and output variable cannot be specified without a gage')

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
    logger.debug(f'Returning to {request.user.email} from save_tuning_tab() - {response_validator.data}')
    return Response(response_validator.data)


@extend_schema(
    request=UploadUserParameterFile,
    responses={
        200: UserParameterFileUploadResponse,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Allow user to upload a starting parameter file"
)
@api_view(['POST'])
@handle_exceptions
def upload_user_parameters(request):
    data = request.data
    logger.debug(f'upload_user_parameter_file() request from {request.user.email} - {data}')

    validator, error_return = validate_request(UploadUserParameterFile, data, context={'request': request})
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_calibration_run(calibration_run_id, request.user)
    if error_return:
        return error_return

    files = request.FILES.getlist('user_parameter_file')

    parameter_file = files[0]
    file_contents = parameter_file.read().decode('utf-8')

    # Detect delimiter type by checking the first few rows
    first_line = file_contents.splitlines()[0]

    if ',' in first_line:
        delimiter = ','
        logger.debug("Detected comma delimiter.")
    elif '\t' in first_line:
        delimiter = '\t'
        logger.debug("Detected tab delimiter.")
    else:
        delimiter = r'\s+'
        logger.debug("Detected space delimiter.")

    try:
        # Handle file parsing based on detected delimiter
        df = pd.read_csv(io.StringIO(file_contents), sep=delimiter, engine='python', skipinitialspace=True)
    except pd.errors.ParserError:
        return Response({'error': 'The uploaded file could not be parsed with the detected delimiter.'}, status=400)

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
    run.save(update_fields=['user_parameter_filename'])

    response = {
        'message': f"Parameter file '{parameter_file.name}' saved for Calibration Run {run.id}",
        'calibration_run_id': run.id,
        'user_parameter_file': parsed_data
    }

    response_validator, error_response = validate_response(UserParameterFileUploadResponse, response)
    if error_response:
        return error_response

    logger.debug(f'Returning to {request.user.email} from upload_user_parameter_file() - {response_validator.data}')
    return Response(response_validator.data)


def validate_simulation_within_range(
        data_start: datetime,
        data_end: datetime,
        simulation_start: datetime,
        simulation_end: datetime,
        label: str
) -> Optional[str]:
    """
    Validates that a given simulation period is within a specified data range.
    """
    if simulation_start < data_start or simulation_end > data_end:
        return (
            f"{label} simulation times must be within the intersection of forcing data and "
            f"observational data - {format_datetime(data_start)} to {format_datetime(data_end)}"
        )
    return None


def validate_time_range_against_data(
        run: CalibrationRun,
        calibration_times: Optional[Dict[str, datetime]] = None,
        validation_times: Optional[Dict[str, datetime]] = None
) -> Optional[str]:
    """
    Validates that calibration and validation times are within the forcing and observational data range from `run`.

    :param run: The CalibrationRun instance.
    :param calibration_times: Dictionary with calibration start and end times.
    :param validation_times: Dictionary with validation start and end times.
    :return: Error message if validation fails, otherwise None.
    """
    if not (run.time_range_start and run.time_range_end):
        return None

    data_start, data_end = run.time_range_start, run.time_range_end

    # Retrieve calibration period from either dict or `run`
    calibration_start = calibration_times.get('simulation_start_time') if calibration_times else run.calibration_start_period
    calibration_end = calibration_times.get('simulation_end_time') if calibration_times else run.calibration_end_period

    if calibration_start and calibration_end:
        error_message = validate_simulation_within_range(data_start, data_end, calibration_start, calibration_end, "Calibration")
        if error_message:
            return error_message

    # Retrieve validation period from either dict or `run`
    validation_start = validation_times.get('simulation_start_time') if validation_times else run.validation_start_period
    validation_end = validation_times.get('simulation_end_time') if validation_times else run.validation_end_period

    if run.automatic_validation and validation_start and validation_end:
        return validate_simulation_within_range(data_start, data_end, validation_start, validation_end, "Validation")

    return None


def validate_and_save_times(run: CalibrationRun, calibration_times: Dict[str, datetime], validation_times: Dict[str, datetime]) -> List[str]:
    messages = []

    # Validation against forcing and obs data intersection
    error_message = validate_time_range_against_data(run, calibration_times, validation_times)
    if error_message:
        messages.append(error_message)

    if calibration_times:
        error_message, calibration_simulation_range = validate_time_range(
            calibration_times.get('simulation_start_time'),
            calibration_times.get('simulation_end_time'),
            'calibration simulation'
        )
        if error_message:
            messages.append(error_message)

        error_message, calibration_evaluation_range = validate_time_range(
            calibration_times.get('calibration_start_time'),
            calibration_times.get('calibration_end_time'),
            'calibration evaluation'
        )
        if error_message:
            messages.append(error_message)
    else:
        calibration_simulation_range = None
        calibration_evaluation_range = None

    if validation_times:
        error_message, validation_simulation_range = validate_time_range(
            validation_times.get('simulation_start_time'),
            validation_times.get('simulation_end_time'),
            'validation simulation'
        )
        if error_message:
            messages.append(error_message)

        error_message, validation_evaluation_range = validate_time_range(
            validation_times.get('validation_start_time'),
            validation_times.get('validation_end_time'),
            'validation evaluation'
        )
        if error_message:
            messages.append(error_message)
    else:
        validation_simulation_range = None
        validation_evaluation_range = None

    # If any of the ranges are invalid, return messages immediately
    if messages:
        return messages

    # Define full_evaluation_start_date and full_evaluation_end_date for validation simulation range
    full_evaluation_start_date: datetime | None = None
    full_evaluation_end_date: datetime | None = None

    # Define the expanded evaluation range from the minimum and maximum evaluation start/end times
    if validation_evaluation_range and calibration_evaluation_range:
        full_evaluation_start_date, full_evaluation_end_date = get_full_evaluation_date_range_from_ranges(calibration_evaluation_range,
                                                                                                          validation_evaluation_range)

    # Ensure the calibration simulation range contains the calibration evaluation range
    if calibration_evaluation_range and calibration_simulation_range:
        start_outside_range = calibration_evaluation_range[0] < calibration_simulation_range[0]
        end_outside_range = calibration_evaluation_range[1] > calibration_simulation_range[1]

        if start_outside_range or end_outside_range:
            messages.append(
                f'Calibration simulation range from {format_datetime(calibration_simulation_range[0])} to '
                f'{format_datetime(calibration_simulation_range[1])} must contain the calibration evaluation range from '
                f'{format_datetime(calibration_evaluation_range[0])} to {format_datetime(calibration_evaluation_range[1])}.'
            )

    # Ensure the validation simulation range contains both the calibration and validation evaluation ranges
    if validation_simulation_range:
        valid_simulation_start, valid_simulation_end = validation_simulation_range

        if full_evaluation_start_date is not None and full_evaluation_end_date is not None:
            if valid_simulation_start > full_evaluation_start_date or valid_simulation_end < full_evaluation_end_date:
                messages.append(
                    f'Validation simulation range from {format_datetime(valid_simulation_start)} to '
                    f'{format_datetime(valid_simulation_end)} must contain the calibration and validation evaluation ranges from '
                    f'{format_datetime(full_evaluation_start_date)} to {format_datetime(full_evaluation_end_date)}.'
                )

    # Check for overlap between calibration and validation evaluation ranges
    if validation_evaluation_range and calibration_evaluation_range:
        overlap_exists = (
                validation_evaluation_range[0] <= calibration_evaluation_range[1] and
                validation_evaluation_range[1] >= calibration_evaluation_range[0]
        )

        if overlap_exists:
            messages.append(
                f"Calibration evaluation range from {format_datetime(calibration_evaluation_range[0])} to "
                f"{format_datetime(calibration_evaluation_range[1])} cannot intersect the validation evaluation range from "
                f"{format_datetime(validation_evaluation_range[0])} to {format_datetime(validation_evaluation_range[1])}."
            )

    # Save times if no errors
    if not messages:
        if calibration_times:
            run.calibration_start_period = calibration_times.get('simulation_start_time')
            run.calibration_end_period = calibration_times.get('simulation_end_time')
            run.calibration_eval_start_period = calibration_times.get('calibration_start_time')
            run.calibration_eval_end_period = calibration_times.get('calibration_end_time')

        if run.automatic_validation and validation_times:
            run.validation_start_period = validation_times.get('simulation_start_time')
            run.validation_end_period = validation_times.get('simulation_end_time')
            run.validation_eval_start_period = validation_times.get('validation_start_time')
            run.validation_eval_end_period = validation_times.get('validation_end_time')

    return messages


def get_full_evaluation_date_range_from_ranges(
        calibration_evaluation_range: Tuple[datetime, datetime],
        validation_evaluation_range: Tuple[datetime, datetime]
) -> Tuple[datetime, datetime]:
    start_date = min(calibration_evaluation_range[0], validation_evaluation_range[0])
    end_date = max(calibration_evaluation_range[1], validation_evaluation_range[1])
    return start_date, end_date


def get_full_evaluation_date_range(
        calibration_evaluation_start_time: datetime,
        calibration_evaluation_end_time: datetime,
        validation_evaluation_start_time: datetime,
        validation_evaluation_end_time: datetime
) -> Tuple[datetime, datetime]:
    # Calculate the full evaluation date range using min and max directly
    start_date = min(calibration_evaluation_start_time, validation_evaluation_start_time)
    end_date = max(calibration_evaluation_end_time, validation_evaluation_end_time)

    return start_date, end_date


# TODO Do woe need allow_empty?
def validate_time_range(
        start_time: datetime | None,
        end_time: datetime | None,
        field_name: str,
        allow_empty: bool = True
) -> tuple[str | None, tuple[datetime | None, datetime | None] | None]:
    # Check for empty range if allowed
    if allow_empty and (start_time is None or end_time is None):
        return None, (start_time, end_time)

    # Check if both start and end times are provided
    if start_time is None or end_time is None:
        return f'{field_name.capitalize()} requires both start and end times', None

    # Check if start time is earlier than or equal to end time
    if start_time > end_time:
        return (f'{field_name.capitalize()} must have a start time earlier than or equal to the end time - '
                f'{format_datetime(start_time)} > {format_datetime(end_time)}'), None

    # If all validations pass, return the valid range
    return None, (start_time, end_time)


def validate_parameters(run: CalibrationRun, parameters: List[Dict[str, str | float]]) -> str | None:
    if not parameters:
        return None

    # Fetch all CalibrationParameters for the given calibration run and related modules in one query
    existing_parameters = CalibrationParameter.objects.filter(
        calibration_formulation__calibration_run=run
    ).select_related('calibration_formulation__module')

    # Create a lookup dictionary for existing parameters by module name and parameter name
    parameter_lookup = {
        (param.calibration_formulation.module.name, param.name): param
        for param in existing_parameters
    }

    # Validate each parameter in the input
    invalid_parameters = []
    invalid_modules = []
    for p in parameters:
        key = (p['module'], p['name'])
        if key not in parameter_lookup:
            # Determine if the module exists in the cache
            (invalid_parameters if get_cached_module_by_name(p['module']) else invalid_modules).append(key)

    # If any invalid parameters or modules are found, create an error message
    if invalid_parameters or invalid_modules:
        invalid_param_list = [f"Invalid parameter '{name}' for module '{module}'" for module, name in invalid_parameters]
        invalid_module_list = [f"Invalid module '{module}' for parameter '{name}'" for module, name in invalid_modules]
        return ", ".join(invalid_param_list + invalid_module_list)

    return None


def save_output_variable(run: CalibrationRun, output_variable_to_calibrate: Dict[str, str]) -> str | None:
    if output_variable_to_calibrate:
        # Retrieve the cached module by name
        module = get_cached_module_by_name(output_variable_to_calibrate['module'])

        if not module:
            return f"Module '{output_variable_to_calibrate['module']}' not found in the database."

        try:
            # Check if the module is part of the calibration run
            module_with_output_variable = CalibrationFormulation.objects.get(
                module=module,
                calibration_run=run
            )
        except CalibrationFormulation.DoesNotExist:
            return f"Module '{output_variable_to_calibrate['module']}' is not part of calibration run {run.id}"

        try:
            # Get the output variable from the module's output variables
            module_output_variable = module_with_output_variable.output_variables.get(
                name=output_variable_to_calibrate['name']
            )
        except ModuleOutputVariable.DoesNotExist:
            return f"Module output variable '{output_variable_to_calibrate['name']}' not found in module '{output_variable_to_calibrate['module']}' for this run"

        # Set the run's module output variable
        run.module_output_variable = module_output_variable
        return None


def save_parameters(run: CalibrationRun, parameters: List[Dict[str, str | float]], no_override: bool = False) -> None:
    if parameters:
        parameters_to_update = []

        # Fetch all CalibrationParameters for the given calibration run in one query
        existing_parameters = CalibrationParameter.objects.filter(
            calibration_formulation__calibration_run=run
        ).select_related('calibration_formulation__module')

        # Create a lookup dictionary for existing parameters by module name and parameter name
        parameter_lookup = {
            (param.calibration_formulation.module.name, param.name): param
            for param in existing_parameters
        }

        # Update the parameters based on the input
        for p in parameters:
            calibration_param = parameter_lookup[(p['module'], p['name'])]
            # min, max and initial_value might be null if imported.  Leavve the value from Hydrofabric
            if not no_override:
                calibration_param.minimum = p.get('minimum')
                calibration_param.maximum = p.get('maximum')
                calibration_param.initial_value = p.get('initial_value')
            calibration_param.user_selected_for_tuning = True
            parameters_to_update.append(calibration_param)

        # Use bulk_update to update all parameters at once
        CalibrationParameter.objects.bulk_update(
            parameters_to_update, ['minimum', 'maximum', 'initial_value', 'user_selected_for_tuning']
        )


# Reads a CSV file and gets the date field from the first column. Then computes the min/max to construct a date range
def get_csv_daterange(file: Path) -> DateTimeRange:
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


def get_forcing_date_range(forcing_dir_path: Path) -> DateTimeRange | None:
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


def get_observation_date_range(observational_filepath: Path) -> DateTimeRange:
    return get_csv_daterange(observational_filepath)


def get_date_range_intersection(observational_file_path: Path, forcing_dir_path: Path) -> DateTimeRange | None:
    # The get latest start data and the earlier end date
    obs_range = get_observation_date_range(observational_file_path)
    logger.debug(f'obs_range: {obs_range}')
    forcing_range = get_forcing_date_range(forcing_dir_path)
    logger.debug(f'forcing_range: {forcing_range}')
    return obs_range.intersection(forcing_range) if forcing_range and obs_range else None
