import json
import logging
import os
import re
from collections import defaultdict
from functools import lru_cache
from typing import Any

import pandas as pd
from django.core.cache import cache
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from calibration.enums import StatusEnum, PlotDefinitionsEnum, ValidationType, ValidationMetricPeriod
from calibration.enums_vanilla import JobType
from calibration.models import CalibrationRun, ValidationRun, ForecastRun, ValidationMetrics, NWMRetrospectiveMetrics
from calibration.util.caching import get_filtered_plot_definitions
from calibration.util.calibration_validators import GetPLotNamesResponseSerializer, \
    ErrorResponseSerializer, GetPlotRequestSerializer, GetPlotResponseSerializer, CalibrationOrValidationOrForecastRunSerializer
from calibration.util.ngen_locations import get_output_calibration_run_dir, get_output_validation_plot_dir, get_output_iteration_file, \
    get_output_last_iteration_file, get_output_best_iteration_file, get_observational_file_for_job, get_cost_hist_file, \
    NWM_RETROSPECTIVE_DIR, get_output_valid_control_file, get_output_valid_best_file, get_output_validation_iteration_plot_dir, \
    get_output_valid_iteration_file, get_forecast_output_dir, get_forecast_output_file
from calibration.views.calibration_evaluation_views import get_iterations_for_calibration_job
from calibration.views.called_from import get_caller_name
from calibration.views.common import get_calibration_run, handle_exceptions, validate_response, validate_request, CerfException, \
    ResponseError, truncate_large_fields, get_validation_run, get_job_description, \
    get_forecast_run, replace_nan_and_inf_with_none, png_to_base64_url, process_worker_dirs, get_user_email

logger = logging.getLogger(__name__)


@extend_schema(
    request=CalibrationOrValidationOrForecastRunSerializer,
    responses={
        200: GetPLotNamesResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Get a list of plot names"
)
@api_view(['GET', 'POST'])
@handle_exceptions
def get_plot_names(request: Request) -> Response:
    """
    Retrieves the list of plot names and descriptions for a calibration run, filtered by applicable optimizations.

    :param request: The request containing either POST data or query parameters.
    :return: A JSON response with the calibration run ID, list of plot names and descriptions, and run status.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {data}')

    validator, error_return = validate_request(CalibrationOrValidationOrForecastRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    validation_run_id = validator.get('validation_run_id')
    forecast_run_id = validator.get('forecast_run_id')

    # Determine job type and retrieve the appropriate run instance
    if calibration_run_id:
        run_func = get_calibration_run
        run_id = calibration_run_id
        run_type = JobType.CALIBRATION.value.capitalize()
    elif validation_run_id:
        run_func = get_validation_run
        run_id = validation_run_id
        run_type = JobType.VALIDATION.value.capitalize()
    else:
        run_func = get_forecast_run
        run_id = forecast_run_id
        run_type = JobType.FORECAST.value.capitalize()
    run, error_return = run_func(run_id, request.user, run_status=[StatusEnum.RUNNING, StatusEnum.DONE])
    if error_return:
        return error_return

    # Get filtered plot definitions for the run
    filtered_plot_definitions = get_filtered_plot_definitions(run)

    # Create a list of plot names with descriptions
    plot_names = [{'name': plot['name'], 'description': plot['description'], 'timeseries_available': plot['timeseries_available']}
                  for plot in filtered_plot_definitions]

    response = {
        f"{run_type.lower()}_run_id": run.id,
        'plot_names': plot_names,
        'status': run.status.name
    }

    response_validator, error_response = validate_response(GetPLotNamesResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {json.dumps(response_validator.data)}')
    logger.debug(
        f'Returning to {get_user_email(request)} from {get_caller_name()}() - '
        f'{json.dumps(response_validator.data)}'
    )

    return Response(response_validator.data)


@extend_schema(
    request=GetPlotRequestSerializer,
    responses={
        200: GetPlotResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Return a base64 URL for a plot image and the associated data"
)
@api_view(['GET', 'POST'])
@handle_exceptions
def get_plot(request: Request) -> Response:
    """
    Retrieves a specific plot for a calibration run, validation run, or forecast run, returning the plot file location and optional data with pagination support.

    If a calibration_run_id is given, then we can retrieve plots for the calibration run or the validation best run.
    If a validation_run_id is given, then we can retrieve plots for that specific validation run as well as the calibration run.
    If a forecast_run_id is given, then we can retrieve plots for that specific forecast run as well as the calibration run.

    :param request: The request containing plot name and options.
    :return: A JSON response with plot details, or an error if the plot is not found.
    :raises ResponseError: If the plot cannot be found or an error occurs.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {data}')

    validator, error_return = validate_request(GetPlotRequestSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    validation_run_id = validator.get('validation_run_id')
    forecast_run_id = validator.get('forecast_run_id')

    plot_name = validator.get('plot_name')
    include_data = validator.get('include_data')
    force_include_plot = validator.get('force_include_plot')
    start = validator.get('start')
    limit = validator.get('limit')

    # Replace spaces with underscores in plot_name to avoid CacheKeyWarning
    sanitized_plot_name = plot_name.replace(" ", "_")
    # Base cache key common part
    cache_key_base = f"{sanitized_plot_name}_{calibration_run_id or validation_run_id}"
    cache_key_plot_url = f"plot_url_{cache_key_base}"

    plot_url = cache.get(cache_key_plot_url)
    plot_file_path = None
    plot_url_calculated = False  # Tracks if plot_url was calculated in this request

    # Determine job type and retrieve the appropriate run instance
    if calibration_run_id:
        run_func = get_calibration_run
        run_id = calibration_run_id
        run_type = JobType.CALIBRATION.value.capitalize()
    elif validation_run_id:
        run_func = get_validation_run
        run_id = validation_run_id
        run_type = JobType.VALIDATION.value.capitalize()
    else:
        run_func = get_forecast_run
        run_id = forecast_run_id
        run_type = JobType.FORECAST.value.capitalize()

    run, error_return = run_func(run_id, request.user, run_status=[StatusEnum.RUNNING, StatusEnum.DONE])
    if error_return:
        return error_return

    # Identify the associated calibration run, handling calibration, validation, and forecast cases
    calibration_run = run if calibration_run_id else run.calibration_run

    # Fetch plot definition if needed for force_include_plot, include_data, or when plot_url is missing
    plot_definition = None
    if force_include_plot or not plot_url or include_data:
        plot_definition = get_filtered_plot_definitions(run, plot_name=plot_name, first_match=True)
        if not plot_definition:
            return ResponseError(f"Invalid plot type '{plot_name}' requested for {run_type} {run.id}.")

    # Process plot_url if it doesn't exist in the cache or if force_include_plot is True
    if force_include_plot or not plot_url:
        gage_id = calibration_run.gage.gage_id

        # Determine plot location based on plot definition
        location = determine_plot_location(run, plot_definition)
        plot_file_name = plot_definition['filename_mask'].format(gage_id=gage_id)
        plot_file_path = os.path.join(location, plot_file_name)

        if not os.path.exists(plot_file_path):
            return ResponseError(f"Plot {plot_file_path} not found at expected location")

        plot_url = png_to_base64_url(plot_file_path)
        logger.info(f'Retrieving plot {plot_file_name} from {plot_file_path}')
        plot_url_calculated = True

        # Cache the plot_url
        cache.set(cache_key_plot_url, plot_url, timeout=3600)

    # Handle data if include_data is True
    plot_data = None
    pagination_metadata = None
    if include_data:
        # Retrieve data and total_count from get_plot_data
        plot_result = get_plot_data(run, plot_definition, start, limit)
        plot_data = plot_result.get('data', [])
        total_count = plot_result['total_count']
        # Replace NaN values with None for JSON compatibility
        if plot_data:
            plot_data = replace_nan_and_inf_with_none(plot_data)
        else:
            logger.warning(f"Data not available for {plot_name}")

        pagination_metadata = {
            'start': start,
            'limit': limit,
            'count': total_count
        }

    response = {
        'calibration_run_id': calibration_run.id,
        'plot_name': plot_name,
    }

    # Include plot_url based on force_include_plot or whether it was just calculated
    if force_include_plot or plot_url_calculated:
        response['plot_url'] = plot_url

    # Include plot_file_name if available
    if plot_file_path:
        response['plot_file_path'] = plot_file_path

    if validation_run_id:
        response['validation_run_id'] = validation_run_id
    if forecast_run_id:
        response['forecast_run_id'] = forecast_run_id
    if include_data:
        response['plot_data'] = plot_data
        if pagination_metadata:
            response['pagination_metadata'] = pagination_metadata  # Add pagination metadata if available

    # Validate and return response
    response_validator, error_response = validate_response(
        GetPlotResponseSerializer, response,
        fields_to_truncate=['plot_url', 'plot_data'], max_length=10
    )
    if error_response:
        return error_response
    logger.debug(
        f'Returning to {get_user_email(request)} from {get_caller_name()}() - '
        f'{json.dumps(truncate_large_fields(response_validator.data, fields_to_truncate=["plot_url", "plot_data"], max_length=10))}'
    )

    return Response(response_validator.data)


def determine_plot_location(run: CalibrationRun | ValidationRun | ForecastRun, plot_definition: dict[str, Any]) -> str:
    """
    Determines the file location of the plot based on the plot definition's attributes.

    :param run: The run object, which could be either a calibration, validation, or forecast run.
    :param plot_definition: Dictionary containing the plot's attributes, such as its location type.
    :return: The file path where the plot is expected to be located.
    :raises CerfException: If the plot's location type is unknown, the required directory cannot be found,
                           or an invalid run type is provided for a specific plot type.
    """
    calibration_run = run if isinstance(run, CalibrationRun) else run.calibration_run
    match plot_definition['location']:
        case 'plot_valid':
            # Ensure that 'plot_valid' is not used for a ForecastRun
            if isinstance(run, ForecastRun):
                raise CerfException("Plot type is not valid for ForecastRun.")

            # Validation plots can be retrieved with either a CalibrationRun or a non-VALID_ITERATION ValidationRun
            if isinstance(run, CalibrationRun) or run.validation_type != ValidationType.VALID_ITERATION.value:
                return get_output_validation_plot_dir(calibration_run)
            return get_output_validation_iteration_plot_dir(
                run.calibration_run, run.iteration_num, run.worker_name
            )

        case 'output_calibration':
            return get_output_calibration_run_dir(calibration_run)

        case 'plot_iteration':
            # TODO Need to return the worker name
            worker_dir = find_worker_with_non_empty_plot_iteration(calibration_run)
            if worker_dir is None:
                raise CerfException(f'Plots could not be found for {get_job_description(run)}')
            return os.path.join(worker_dir, 'Plot_Iteration')

        case 'forecast_output':
            if not isinstance(run, ForecastRun):
                raise CerfException('A ForecastRun id is required for forecast plots')
            return get_forecast_output_dir(run)

        case _:
            raise CerfException(f"Unknown location '{plot_definition['location']}' in PlotDefinitions")


def get_plot_data(run: CalibrationRun | ValidationRun | ForecastRun, plot_definition: dict[str, Any], start: int, limit: int) -> dict[str, Any]:
    """
    Retrieves data for a specific plot based on its definition and includes the total count of rows.

    :param run: The run object, either a calibration, validation, or forecast run
    :param plot_definition: Dictionary containing plot specifications.
    :param start: The starting index for pagination.
    :param limit: The maximum number of items to retrieve.
    :return: A dictionary containing 'data' and 'total_count'.
    :raises CerfException: If an invalid plot type is requested for the given run.
    """
    plot_enum = PlotDefinitionsEnum(plot_definition['name'])

    # Initialize calibration_run to None
    calibration_run = None

    # Ensure ForecastRun only processes FORECAST_HYDROGRAPH
    if isinstance(run, ForecastRun):
        if plot_enum != PlotDefinitionsEnum.FORECAST_HYDROGRAPH:
            raise CerfException(f"Invalid plot type '{plot_enum}' requested for ForecastRun {run.id}.")
    else:
        if not isinstance(run, (CalibrationRun, ValidationRun)):
            raise CerfException(f"Invalid plot type '{plot_enum}' requested for {type(run).__name__} {run.id}.")
        calibration_run = run.calibration_run if isinstance(run, ValidationRun) else run

    worker_dir = None  # Cache worker directory to avoid multiple lookups

    match plot_enum:
        case PlotDefinitionsEnum.FORECAST_HYDROGRAPH:
            # Ensure only ForecastRun can access this plot type
            if not isinstance(run, ForecastRun):
                raise CerfException(f"'{plot_enum}' is only valid for ForecastRun.")

            # Read the forecast output data from a file and paginate the result
            forecast_output = get_forecast_output_file(run)
            if not os.path.exists(forecast_output):
                raise FileNotFoundError(f"File not found: {forecast_output}")
            data, total_count = count_and_read_file_in_chunks(forecast_output, start, limit)
            return {'data': data, 'total_count': total_count}

        case PlotDefinitionsEnum.OBJECTIVE_FUNCTION_EVOLUTION:
            # Only get iterations for a specific worker
            worker_dir = find_worker_with_non_empty_plot_iteration(calibration_run)
            worker_name = get_worker_name_from_directory(worker_dir)
            iterations = get_iterations_for_calibration_job(calibration_run, worker_name=worker_name)
            total_count = len(iterations)

            data = [{'iteration': iteration.iteration_num, 'objective_function_value': iteration.objective_function_value}
                    for iteration in iterations[start:start + limit]]
            return {'data': data, 'total_count': total_count}

        case PlotDefinitionsEnum.HYDROGRAPH_EVOLUTION | PlotDefinitionsEnum.SCATTERPLOT_STREAMFLOW:
            # Merge multiple hydrograph-related files and paginate the result
            worker_dir = worker_dir or find_worker_with_non_empty_plot_iteration(calibration_run)
            file_paths = [
                get_observational_file_for_job(calibration_run),  # Observation
                get_output_iteration_file(calibration_run, 0, worker_dir),  # Iteration
                get_output_last_iteration_file(calibration_run, worker_dir),  # Last Iteration
                get_output_best_iteration_file(calibration_run, worker_dir)  # Best Iteration
            ]
            column_names = ["Observation", "Control Run", "Last Run", "Best Run"]
            # Get paginated data and total count
            data, total_count = load_and_merge_hydrograph_files_with_pagination_and_count(file_paths, column_names, start, limit)
            return {'data': data, 'total_count': total_count}

        case PlotDefinitionsEnum.METRIC_EVOLUTION:
            # Only get iterations for a specific worker
            worker_dir = find_worker_with_non_empty_plot_iteration(calibration_run)
            worker_name = get_worker_name_from_directory(worker_dir)
            iterations = get_iterations_for_calibration_job(calibration_run, worker_name=worker_name)
            total_count = len(iterations)

            data = [{'iteration': iteration.iteration_num,
                     'metrics': [{'name': metric.metric.name, 'value': metric.metric_value} for metric in iteration.iterationmetric_set.all()]}
                    for iteration in iterations[start:start + limit]]
            return {'data': data, 'total_count': total_count}

        case PlotDefinitionsEnum.PARAMETER_EVOLUTION:
            # Only get iterations for a specific worker
            worker_dir = find_worker_with_non_empty_plot_iteration(calibration_run)
            worker_name = get_worker_name_from_directory(worker_dir)
            iterations = get_iterations_for_calibration_job(calibration_run, worker_name=worker_name)
            total_count = len(iterations)

            data = [{'iteration': iteration.iteration_num,
                     'parameters': [{'name': parameter.calibration_parameter.name, 'value': parameter.tuned_value} for parameter in
                                    iteration.iterationparameter_set.all()]}
                    for iteration in iterations[start:start + limit]]
            return {'data': data, 'total_count': total_count}

        case PlotDefinitionsEnum.METRICS_VS_OBJECTIVE_FUNCTION:
            # Only get iterations for a specific worker
            worker_dir = find_worker_with_non_empty_plot_iteration(calibration_run)
            worker_name = get_worker_name_from_directory(worker_dir)
            iterations = get_iterations_for_calibration_job(calibration_run, worker_name=worker_name)
            total_count = len(iterations)

            data = [{'iteration': iteration.iteration_num,
                     'objective_function_value': iteration.objective_function_value,
                     'metrics': [{'name': metric.metric.name, 'value': metric.metric_value} for metric in iteration.iterationmetric_set.all()]}
                    for iteration in iterations[start:start + limit]]
            return {'data': data, 'total_count': total_count}

        case PlotDefinitionsEnum.STREAM_FLOW_PRECIPITATION:
            # Requires calculation, so we won't return data
            return {'data': [], 'total_count': 0}

        case PlotDefinitionsEnum.FLOW_DURATION_CURVES:
            # Requires calculation, so we won't return data
            return {'data': [], 'total_count': 0}

        case PlotDefinitionsEnum.COST_HISTORY:
            # Read cost history data from a file and paginate the result
            forecast_output = get_cost_hist_file(calibration_run)
            if not os.path.exists(forecast_output):
                logger.error(f"File not found: {forecast_output}")
                raise FileNotFoundError(f"File not found: {forecast_output}")
            data, total_count = count_and_read_file_in_chunks(forecast_output, start, limit)

            return {'data': data, 'total_count': total_count}

        case PlotDefinitionsEnum.BAR_CHART_METRICS:
            combined_data_by_run = get_bar_chart_metrics([calibration_run.id])
            combined_data = combined_data_by_run.get(calibration_run.id, [])

            total_count = len(combined_data)
            paginated_data = combined_data[start:start + limit]

            return {'data': paginated_data, 'total_count': total_count}

        case PlotDefinitionsEnum.HYDROGRAPH_VALIDATION:
            # Files being read:
            # 1. Observational data file
            # 2. NWM retrospective data file
            # 3. Valid Control hydrograph data file
            # 4. Valid Best hydrograph data file
            # 5. (Optional) Hydrograph data file for a specific iteration if this is a ValidationRun of type "VALID_ITERATION"

            file_paths = [
                get_observational_file_for_job(calibration_run),  # Observation
                os.path.join(NWM_RETROSPECTIVE_DIR, f'{calibration_run.gage.gage_id}.csv'),  # NWM Retro
                get_output_valid_control_file(calibration_run),  # Valid Control
                get_output_valid_best_file(calibration_run)  # Valid Best
            ]
            column_names = ["Observation", "NWM Retro", "Valid Control", "Valid Best"]

            if isinstance(run, ValidationRun) and run.validation_type == ValidationType.VALID_ITERATION.value:
                # Add hydrograph data for the specific iteration
                file_paths.append(get_output_valid_iteration_file(calibration_run, run.worker_name, run.iteration_num))
                column_names.append(run.worker_name)  # Append corresponding column name

            # Combine and paginate data from the hydrograph files
            data, total_count = load_and_merge_hydrograph_files_with_pagination_and_count(file_paths, column_names, start, limit)
            return {'data': data, 'total_count': total_count}

        case PlotDefinitionsEnum.STREAMFLOW_VALIDATION_PRECIPITATION:
            # Requires calculation, so we won't return data
            return {'data': [], 'total_count': 0}

        case _:
            logger.error(f"Data handler not found for '{plot_enum}'")
            return {'data': [], 'total_count': 0}


def load_and_merge_hydrograph_files_with_pagination_and_count(
        file_paths: list[str], column_names: list[str], start: int, limit: int, key_col: str = "time"
) -> tuple[list[dict[str, Any]], int]:
    """
    Loads multiple hydrograph-related CSV files, merges them, and returns paginated results.

    :param file_paths: List of file paths to the hydrograph-related data files.
    :param column_names: Column names to rename the value columns for clarity.
    :param start: Starting index for pagination (0-based).
    :param limit: Maximum number of rows to return.
    :param key_col: The key column to merge on (default: "time").
    :return: A tuple containing paginated data and the total row count.
    """
    logger.info(f'Merging files: {file_paths}')
    try:
        # Step 1: Merge all the provided files into a single DataFrame
        merged_df = load_files_and_merge(file_paths, column_names, key_col=key_col)

        # Step 2: Calculate the total number of rows in the merged DataFrame
        total_count = len(merged_df)

        # Step 3: Extract a paginated subset of the merged DataFrame
        paginated_data = merged_df.iloc[start:start + limit].to_dict(orient="records")

        # Step 4: Convert all Timestamp objects in the key column to ISO 8601 strings
        for row in paginated_data:
            if key_col in row and isinstance(row[key_col], pd.Timestamp):
                row[key_col] = row[key_col].isoformat()

        # Return the paginated data and total row count
        return paginated_data, total_count
    except Exception as e:
        # Log the error and raise a custom exception if any issues occur during processing
        logger.error(f"Error processing hydrograph files: {e}")
        raise CerfException(f"Failed to process hydrograph files: {e}")


def load_files_and_merge(file_paths: list[str], column_names: list[str], key_col: str = "time") -> pd.DataFrame:
    """
    Reads and merges multiple files into a single DataFrame using a common key column.

    :param file_paths: List of file paths to load.
    :param column_names: List of names for value columns in the merged DataFrame.
    :param key_col: The key column to merge on (default: "time").
    :return: Merged DataFrame containing data from all files.
    :raises CerfException: If no valid files are found or if merging fails.
    """
    dataframes = []  # List to store individual DataFrames from each file

    # Step 1: Read and prepare each file, dynamically detecting column names
    for file_path, col_name in zip(file_paths, column_names):
        try:
            if os.path.exists(file_path):
                logger.info(f"Reading file: {file_path}")
                # Read file and automatically detect value column
                df = pd.read_csv(file_path, nrows=1)  # Read only the header to determine column names
                value_col = next((col for col in df.columns if col.lower() not in ["time", "datetime", "date", "timestamp", "value_date"]), None)

                if not value_col:
                    raise ValueError(f"No valid data column found in file {file_path}")

                df = read_and_prepare_hydrograph_files(file_path, column_mapping={value_col: col_name})
                dataframes.append(df)
            else:
                # Log a warning for missing files
                logger.warning(f"File not found: {file_path}")
        except ValueError as ve:
            # Handle files with missing key columns
            logger.error(f"Skipping file {file_path} due to error: {ve}")

    # Step 2: Handle the case where no valid files were processed
    if not dataframes:
        logger.error("No valid files found to merge.")
        raise CerfException("No valid files found to merge.")

    # Step 3: Merge all DataFrames on the key column
    merged_df = dataframes[0]  # Start with the first DataFrame
    for df in dataframes[1:]:
        try:
            # Perform an inner merge to include only rows with matching key column values
            merged_df = merged_df.merge(df, on=key_col, how="inner")
        except Exception as e:
            # Log and raise an error if merging fails
            logger.error(f"Error merging DataFrames: {e}")
            raise CerfException(f"Error merging DataFrames: {e}")

    # Step 4: Check for empty merged DataFrame
    if merged_df.empty:
        logger.warning("Merged DataFrame is empty after merging. Check key column values.")

    # Step 5: Log the final structure of the merged DataFrame for debugging
    logger.debug(f"Merged DataFrame columns: {merged_df.columns.tolist()}, shape: {merged_df.shape}")

    return merged_df


def read_and_prepare_hydrograph_files(file_path: str, column_mapping: dict[str, str]) -> pd.DataFrame:
    """
    Reads a hydrograph-related CSV file, dynamically identifies columns for time and values,
    formats data, and filters out invalid rows.

    :param file_path: Path to the CSV file.
    :param column_mapping: A dictionary mapping detected column names to standardized column names.
                           If None is given as the key, it means the column should be detected dynamically.
    :return: A DataFrame containing valid data, formatted for merging.
    :raises ValueError: If no timestamp or value column is found in the file.
    """
    # Step 1: Read CSV and infer types
    df = pd.read_csv(file_path, dtype=None)
    logger.debug(f"Loaded file: {file_path}, Columns: {df.columns.tolist()}, Shape: {df.shape}")

    # Step 2: Detect the timestamp column dynamically
    timestamp_col = next(
        (col for col in df.columns if col.lower() in ["datetime", "time", "date", "timestamp", "value_date"]),
        None
    )
    if not timestamp_col:
        # This is not an error, unless the file is expected to have timestamp information and does not
        logger.info(f"No timestamp column found in file {file_path}. Columns: {df.columns.tolist()}")
        raise ValueError(f"No timestamp column found in file {file_path}. Columns: {df.columns.tolist()}")

    # Step 3: Rename the detected timestamp column to a standard name
    df = df.rename(columns={timestamp_col: "time"})

    # Step 4: Convert the "time" column to datetime format and drop invalid rows
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    invalid_rows = df[df["time"].isna()]
    if not invalid_rows.empty:
        logger.warning(f"Invalid timestamps found in file {file_path}:\n{invalid_rows}")

    # Drop rows with invalid timestamps
    df = df.dropna(subset=["time"])  # Drop rows with invalid timestamps

    # Step 5: Rename value columns based on the provided mapping
    df = df.rename(columns=column_mapping)

    # Step 6: Log the final DataFrame structure
    logger.debug(f"Processed file: {file_path}, Final Columns: {df.columns.tolist()}, Final Shape: {df.shape}")

    return df


def count_and_read_file_in_chunks(file_path: str, start: int, limit: int) -> tuple[list[dict[str, Any]], int]:
    """
    Counts the total number of rows (excluding the header) in a file and retrieves a specific slice of rows efficiently.

    :param file_path: Path to the CSV file to be read.
    :param start: Starting index for pagination (0-based, excluding the header).
    :param limit: Maximum number of rows to retrieve.
    :return: A tuple containing the paginated rows and total row count (excluding the header).
    :raises CerfException: If the file cannot be read due to an error.
    """
    try:
        # Read only the header to get column names
        with open(file_path, 'r') as file:
            header = next(file).strip().split(",")

        # Count total rows efficiently (excluding header)
        with open(file_path, 'r') as file:
            total_count = sum(1 for _ in file) - 1  # Subtract 1 for the header row

        # Ensure start is within valid range
        if start >= total_count:
            return [], total_count  # No data to return

        # Read only the required rows using pandas
        df = pd.read_csv(file_path, skiprows=list(range(1, start + 1)), nrows=limit, names=header, header=0)

        # Convert the "time" column to datetime format, handling errors
        if "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"], errors="coerce")
            df = df.dropna(subset=["time"])  # Drop rows with invalid timestamps

        # Convert DataFrame to a list of dictionaries
        data = df.to_dict(orient="records")

        return data, total_count

    except Exception as e:
        logger.error(f"Error reading file: {e}")
        raise CerfException(f"Failed to read file: {file_path}")


@lru_cache()
def find_worker_with_non_empty_plot_iteration(calibration_run: CalibrationRun) -> str | None:
    """
    Uses process_worker_dirs to find the worker directory that has a non-empty 'Plot_Iteration' subdirectory.

    :param calibration_run: The calibration run object.
    :return: The path of the worker directory with a non-empty 'Plot_Iteration' directory, or None if not found
    """
    found_worker_dir = None

    # Custom function to check worker directories
    def check_worker(worker_dir: str, _run: CalibrationRun):
        nonlocal found_worker_dir
        plot_iteration_dir = os.path.join(worker_dir, 'Plot_Iteration')

        # Check if 'Plot_Iteration' exists and is non-empty
        if os.path.isdir(plot_iteration_dir) and any(os.scandir(plot_iteration_dir)):
            found_worker_dir = worker_dir

    # Call process_worker_dirs to iterate through the worker directories
    process_worker_dirs(calibration_run, check_worker)

    return found_worker_dir


def get_bar_chart_metrics(calibration_run_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    """
    Retrieves ValidationMetrics and NWMRetrospectiveMetrics for a list of calibration_run_ids
    and organizes the results by calibration_run_id.

    Each calibration_run_id key will map to a list of dictionaries structured like:
        {
            "run": run_type,   # Example: 'valid_best', 'valid_control', or 'nwm_retro'
            "period": period,  # Example: 'full', 'calib', 'valid'
            "Corr": value,
            "MAE": value,
            ...
        }

    Field names (e.g., "Corr", "NSELog") match exactly what is stored in the database,
    including casing.

    :param calibration_run_ids: List of CalibrationRun IDs to query.
    :return: A dictionary where each key is a calibration_run_id and the value is a list of result dictionaries.
    """
    valid_periods = ValidationMetricPeriod.get_names()
    valid_run_types = ValidationType.get_names()

    # Query ValidationMetrics (for valid_best and valid_control runs)
    validation_metrics_qs = ValidationMetrics.objects.select_related('metric', 'validation_run').filter(
        validation_run__calibration_run_id__in=calibration_run_ids,
        run_type__in=valid_run_types,
        period__in=valid_periods
    )

    # Query NWMRetrospectiveMetrics (for nwm_retro runs)
    nwm_metrics_qs = NWMRetrospectiveMetrics.objects.select_related('metric').filter(
        calibration_run_id__in=calibration_run_ids,
        period__in=valid_periods
    )

    combined_data_by_run = defaultdict(lambda: defaultdict(dict))
    all_metric_names = set()

    # Process ValidationMetrics (valid_best and valid_control)
    for metric in validation_metrics_qs:
        calibration_run_id = metric.validation_run.calibration_run_id
        run = metric.run_type  # 'valid_best' or 'valid_control'
        period = metric.period
        metric_name = metric.metric.name  # e.g., 'Corr', 'MAE', etc.

        combined_data_by_run[calibration_run_id][(run, period)][metric_name] = metric.metric_value
        all_metric_names.add(metric_name)

    # Process NWMRetrospectiveMetrics (nwm_retro)
    for metric in nwm_metrics_qs:
        calibration_run_id = metric.calibration_run_id
        run = 'nwm_retro'
        period = metric.period
        metric_name = metric.metric.name  # e.g., 'Corr', 'MAE', etc.

        combined_data_by_run[calibration_run_id][(run, period)][metric_name] = metric.metric_value
        all_metric_names.add(metric_name)

    # Flatten into final output format
    final_output = {}

    for calibration_run_id, metrics_by_run_period in combined_data_by_run.items():
        rows = []
        for (run, period), metrics in metrics_by_run_period.items():
            row = {
                'run': run,
                'period': period,
            }
            # Fill all known metric fields, even if missing (set to None)
            for field in sorted(all_metric_names):
                row[field] = metrics.get(field, None)
            rows.append(row)
        final_output[calibration_run_id] = rows

    return final_output


@lru_cache()
def get_worker_name_from_directory(worker_dir: str) -> str:
    """
    Extracts the worker name from a given worker directory string.

    This function assumes that the worker directory string contains a pattern of the form
    'ngen_<worker_name>_worker'. It does not check for a missing match; if the pattern
    is not found, an AttributeError will be raised.

    :param worker_dir: The full path of the worker directory.
    :return: The extracted worker name.
    """
    pattern = r'ngen_([^_]+)_worker'
    dir_name = os.path.basename(worker_dir)
    match = re.search(pattern, dir_name)
    # This will raise an AttributeError if the pattern is not found.
    return match.group(1)
