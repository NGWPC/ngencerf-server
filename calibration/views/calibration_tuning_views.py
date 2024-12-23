import io
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import MAXYEAR, MINYEAR, datetime, timezone
from typing import Tuple

import pandas as pd
from datetimerange import DateTimeRange
from django.db import transaction
from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiParameter, extend_schema, OpenApiResponse
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from calibration.enums import ObservationalSourceEnum, ForcingSourceEnum, StatusEnum, JobType
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
def load_tuning_tab(request: Request) -> Response:
    """
    Loads tuning tab data for a calibration run, including time ranges, modules, and formulations.
    Handles both GET and POST requests.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'load_tuning_tab() request from {request.user.email} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=list(StatusEnum))
    if error_return:
        return error_return

    # Retrieve the time range and modules for the run
    time_range = get_time_range(run)
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
    """
    Checks if any calibration parameters were selected by the user for tuning across all modules that are part of the job
    """
    return modules.filter(calibrationparameter__user_selected_for_tuning=True).exists()


def get_parameters_and_output_variables(modules: QuerySet[CalibrationFormulation]) -> list[dict[str, str | list[dict[str, str | float | int]]]]:
    """
    Retrieves the parameters and output variables for each module in the specified calibration formulation.
    """
    module_list = []

    for formulation in modules.prefetch_related('calibrationparameter_set', 'output_variables'):
        module = get_cached_module_by_name(formulation.module.name)

        if module:
            # Gather calibration parameters and output variables for each module
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


def get_parameters_for_export(modules: QuerySet[CalibrationFormulation]) -> list[dict[str, str | float]]:
    """
    Prepares calibration parameters for export by gathering only user-selected parameters.
    """
    parameter_list = []
    for m in modules:
        calibration_parameters = list(CalibrationParameter.objects
                                      .filter(calibration_formulation=m, user_selected_for_tuning=True)
                                      .values('name', 'minimum', 'maximum', 'initial_value'))

        for p in calibration_parameters:
            p['module'] = m.module.name
            parameter_list.append(p)

    return parameter_list


def get_time_range(run: CalibrationRun) -> dict[str, datetime | None]:
    """
    Determines the date range intersection between observational and forcing data, updating the run if changed.
    """
    observation_path = get_valid_path(run.observational_source, run.observational_eds_file_path,
                                      ObservationalSourceEnum.UPLOAD,
                                      lambda: get_observational_file_for_job(run))

    forcing_path = get_valid_path(run.forcing_source, run.forcing_eds_dir_path,
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


def get_times(run: CalibrationRun) -> Tuple[dict[str, datetime], dict[str, datetime]]:
    """
    Retrieves calibration and validation times if available, otherwise returns empty dictionaries.
    """
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
@handle_exceptions
def save_tuning_tab(request: Request) -> Response:
    """
    Saves tuning settings for a calibration run, including parameters, output variables, and time periods.
    """
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

    response = {'message': f'Calibration Job {run.id} updated', 'calibration_run_id': run.id, 'status': run.status.name}

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
def upload_user_parameters(request: Request) -> Response:
    """
    Allows the user to upload a parameter file for tuning, validating its structure
    and content, and then attaching it to the specified calibration run.
    """
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

    # Process the first file in the list
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
        'message': f"Parameter file '{parameter_file.name}' saved for Calibration Job {run.id}",
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
        job_type: JobType
) -> str | None:
    """
    Validates that the specified simulation period is within the provided data range.

    Parameters:
        data_start (datetime): The start date of the data range.
        data_end (datetime): The end date of the data range.
        simulation_start (datetime): The start date of the simulation period.
        simulation_end (datetime): The end date of the simulation period.
        job_type (enum): A label indicating whether it's for calibration or validation, used in the error message.

    Returns:
        str | None: An error message if the simulation period is out of range; otherwise, None.
    """
    if simulation_start < data_start or simulation_end > data_end:
        return (
            f"{job_type.value.capitalize()} simulation times must be within the intersection of forcing data and "
            f"observational data - {format_datetime(data_start)} to {format_datetime(data_end)}"
        )
    return None


def validate_time_range_against_data(
        run: CalibrationRun,
        calibration_times: dict[str, datetime] | None = None,
        validation_times: dict[str, datetime] | None = None
) -> str | None:
    """
    Ensures that calibration and validation times fall within the observational and forcing data range of the run.

    Parameters:
        run (CalibrationRun): The calibration run being validated.
        calibration_times (dict[str, datetime] | None): Dictionary with calibration start and end times.
        validation_times (dict[str, datetime] | None): Dictionary with validation start and end times.

    Returns:
        str | None: An error message if any time range is out of bounds; otherwise, None.
    """
    if not (run.time_range_start and run.time_range_end):
        return None

    data_start, data_end = run.time_range_start, run.time_range_end

    # Retrieve calibration period from either provided dictionary or `run`
    calibration_start = calibration_times.get('simulation_start_time') if calibration_times else run.calibration_start_period
    calibration_end = calibration_times.get('simulation_end_time') if calibration_times else run.calibration_end_period

    if calibration_start and calibration_end:
        error_message = validate_simulation_within_range(data_start, data_end, calibration_start, calibration_end, JobType.CALIBRATION)
        if error_message:
            return error_message

    # Retrieve validation period from either provided dictionary or `run`
    validation_start = validation_times.get('simulation_start_time') if validation_times else run.validation_start_period
    validation_end = validation_times.get('simulation_end_time') if validation_times else run.validation_end_period

    if run.automatic_validation and validation_start and validation_end:
        return validate_simulation_within_range(data_start, data_end, validation_start, validation_end, JobType.VALIDATION)

    return None


def validate_and_save_times(run: CalibrationRun, calibration_times: dict[str, datetime], validation_times: dict[str, datetime]) -> list[str]:
    """
    Validates that time ranges fall within allowable ranges and saves times if valid.

    Parameters:
        run (CalibrationRun): The calibration run object.
        calibration_times (dict[str, datetime]): Dictionary of calibration time periods.
        validation_times (dict[str, datetime]): Dictionary of validation time periods.

    Returns:
        list[str] | None: A list of error messages if any validation checks fail; otherwise, None.
    """
    messages = []

    # Validation against forcing and observational data intersection
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

    # Define full evaluation range from minimum and maximum evaluation start/end times
    full_evaluation_start_date: datetime | None = None
    full_evaluation_end_date: datetime | None = None

    # Define the expanded evaluation range from the minimum and maximum evaluation start/end times
    if validation_evaluation_range and calibration_evaluation_range:
        full_evaluation_start_date, full_evaluation_end_date = get_full_evaluation_date_range_from_ranges(calibration_evaluation_range,
                                                                                                          validation_evaluation_range)

    # Ensure calibration simulation range contains the calibration evaluation range
    if calibration_evaluation_range and calibration_simulation_range:
        start_outside_range = calibration_evaluation_range[0] < calibration_simulation_range[0]
        end_outside_range = calibration_evaluation_range[1] > calibration_simulation_range[1]

        if start_outside_range or end_outside_range:
            messages.append(
                f'Calibration simulation range from {format_datetime(calibration_simulation_range[0])} to '
                f'{format_datetime(calibration_simulation_range[1])} must contain the calibration evaluation range from '
                f'{format_datetime(calibration_evaluation_range[0])} to {format_datetime(calibration_evaluation_range[1])}.'
            )

    # Ensure validation simulation range contains both the calibration and validation evaluation ranges
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

    # Save times if no errors found
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
    """
    Determines the full evaluation date range by finding the minimum start time and maximum end time
    across both calibration and validation evaluation ranges.

    Parameters:
        calibration_evaluation_range (Tuple[datetime, datetime]): Calibration evaluation start and end times.
        validation_evaluation_range (Tuple[datetime, datetime]): Validation evaluation start and end times.

    Returns:
        Tuple[datetime, datetime]: Start and end times for the full evaluation range.
    """
    start_date = min(calibration_evaluation_range[0], validation_evaluation_range[0])
    end_date = max(calibration_evaluation_range[1], validation_evaluation_range[1])
    return start_date, end_date


def get_full_evaluation_date_range(
        calibration_evaluation_start_time: datetime,
        calibration_evaluation_end_time: datetime,
        validation_evaluation_start_time: datetime,
        validation_evaluation_end_time: datetime
) -> Tuple[datetime, datetime]:
    """
    Calculates the full evaluation date range by taking the minimum start time and maximum end time
    from both calibration and validation periods.

    Parameters:
        calibration_evaluation_start_time (datetime): Start time of the calibration evaluation period.
        calibration_evaluation_end_time (datetime): End time of the calibration evaluation period.
        validation_evaluation_start_time (datetime): Start time of the validation evaluation period.
        validation_evaluation_end_time (datetime): End time of the validation evaluation period.

    Returns:
        Tuple[datetime, datetime]: Combined start and end times for the entire evaluation range.
    """
    start_date = min(calibration_evaluation_start_time, validation_evaluation_start_time)
    end_date = max(calibration_evaluation_end_time, validation_evaluation_end_time)

    return start_date, end_date


# TODO Do woe need allow_empty?
def validate_time_range(
        start_time: datetime | None,
        end_time: datetime | None,
        field_name: str
) -> tuple[str | None, tuple[datetime | None, datetime | None] | None]:
    """
    Validates a given time range, requiring both start and end times to be provided.
    """
    if start_time is None or end_time is None:
        return f'{field_name.capitalize()} requires both start and end times', None

    # Check if start time is earlier than or equal to end time
    if start_time > end_time:
        return (f'{field_name.capitalize()} must have a start time earlier than or equal to the end time - '
                f'{format_datetime(start_time)} > {format_datetime(end_time)}'), None

    # If all validations pass, return the valid range
    return None, (start_time, end_time)


def validate_parameters(run: CalibrationRun, parameters: list[dict[str, str | float]]) -> str | None:
    """
    Validates each provided parameter against existing calibration parameters for a specific calibration run.
    """
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


def save_output_variable(run: CalibrationRun, output_variable_to_calibrate: dict[str, str]) -> str | None:
    """
    Saves the output variable to calibrate for the calibration run if it is valid.
    """
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


def save_parameters(run: CalibrationRun, parameters: list[dict[str, str | float]], allow_nulls: bool = False) -> None:
    """
    Saves or updates calibration parameters for a run.

    This function takes user-specified parameters and overrides the default values from Data Services.
    - If `allow_nulls` is False (the default), user-provided values will always override the Data Services defaults,
      regardless of whether any values are missing in the user input.
    - If `allow_nulls` is True, user-provided values will override the Data Services defaults only if they are not None.
      In this case, any missing values will retain their defaults from Data Services.
    """

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

            # Override Data Services values conditionally based on `allow_nulls`
            # If `allow_nulls` is True, update only if user input is not None
            if allow_nulls:
                if p.get('minimum') is not None:
                    calibration_param.minimum = p.get('minimum')
                if p.get('maximum') is not None:
                    calibration_param.maximum = p.get('maximum')
                if p.get('initial_value') is not None:
                    calibration_param.initial_value = p.get('initial_value')
            else:
                # Always override with user input if `allow_nulls` is False
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
def get_csv_daterange(file: str) -> DateTimeRange:
    """
    Reads a CSV file, assumes the first column contains date information, and calculates
    the minimum and maximum dates to construct a date range.

    Args:
        file (str): The file path to the CSV file.

    Returns:
        DateTimeRange: The calculated date range based on the first column's min and max dates.

    Raises:
        CerfException: If the file does not exist or there is an error in reading the file.
    """
    try:
        if not os.path.exists(file):
            raise CerfException(f"File {file} does not exist")

        # Read the CSV file, assuming the first column contains date information
        df = pd.read_csv(file, delimiter=',', parse_dates=[0])

        # Ensure the first column contains valid datetime values
        df.iloc[:, 0] = pd.to_datetime(df.iloc[:, 0], errors='coerce')  # Handle invalid dates gracefully

        # Compute the min and max dates and convert them to UTC
        min_time = df.iloc[:, 0].min().replace(tzinfo=timezone.utc)
        max_time = df.iloc[:, 0].max().replace(tzinfo=timezone.utc)

        return DateTimeRange(min_time, max_time)
    except Exception as e:
        # Just in case a file is totally unreadable
        raise CerfException(f'Error reading file {file}: {e}')


def get_forcing_date_range(forcing_dir_path: str) -> DateTimeRange | None:
    """
    Computes the encompassing date range for all valid CSV files in a given directory.

    Args:
        forcing_dir_path (str): The directory path containing forcing data files.

    Returns:
        DateTimeRange | None: The combined date range from all files in the directory, or None if no files are found.
    """
    # Use pathlib only for globbing
    from pathlib import Path

    csv_files = [file for file in Path(forcing_dir_path).glob("*.csv") if file.is_file()]
    if not csv_files:
        return None

    # Define a function to process individual files and calculate their date range
    def process_file(file: str) -> DateTimeRange:
        return get_csv_daterange(str(file))  # Convert Path to string

    # Use ThreadPoolExecutor for parallel processing
    with ThreadPoolExecutor() as executor:
        ranges = list(executor.map(process_file, csv_files))

    # Combine all individual ranges into a single encompassing range
    timerange = None
    for new_range in ranges:
        if timerange:
            timerange = timerange.encompass(new_range)
        else:
            timerange = new_range
    return timerange


def get_observation_date_range(observational_filepath: str) -> DateTimeRange:
    """
    Calculates the date range for a single observational data file.

    Args:
        observational_filepath (str): The file path to the observational data file.

    Returns:
        DateTimeRange: The calculated date range based on the observational data file.
    """
    return get_csv_daterange(observational_filepath)


def get_date_range_intersection(observational_file_path: str, forcing_dir_path: str) -> DateTimeRange | None:
    """
    Calculates the intersection of date ranges between observational and forcing data.

    Args:
        observational_file_path (str): Path to the observational data file.
        forcing_dir_path (str): Directory path containing forcing data files.

    Returns:
        DateTimeRange | None: The intersection of date ranges if both ranges exist, or None if there is no overlap.
    """
    # Calculate the date range for the observational data
    obs_range = get_observation_date_range(observational_file_path)
    logger.debug(f'obs_range: {obs_range}')

    # Calculate the date range for the forcing data
    forcing_range = get_forcing_date_range(forcing_dir_path)
    logger.debug(f'forcing_range: {forcing_range}')

    # Compute the intersection of the two ranges
    if obs_range and forcing_range:
        start_time = max(obs_range.start_datetime, forcing_range.start_datetime)
        end_time = min(obs_range.end_datetime, forcing_range.end_datetime)
        if start_time <= end_time:
            return DateTimeRange(start_time, end_time)
    return None
