import logging
import os
from typing import Any

import pandas as pd
from django.core.cache import cache
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from calibration.enums import StatusEnum, PlotDefinitionsEnum, ValidationType
from calibration.enums_vanilla import JobType
from calibration.models import CalibrationRun, ValidationRun
from calibration.util.caching import get_filtered_plot_definitions
from calibration.util.calibration_validators import GetPLotNamesResponseSerializer, \
    ErrorResponseSerializer, GetPlotRequestSerializer, GetPlotResponseSerializer, CalibrationOrValidationOrForecastRunSerializer
from calibration.util.ngen_locations import get_output_calibration_run_dir, get_output_validation_plot_dir, get_output_iteration_file, \
    get_output_last_iteration_file, get_output_best_iteration_file, get_observational_file_for_job, get_cost_hist_file, \
    get_validation_metrics_valid_best_file, get_validation_metrics_nwm_retrospective_file, get_validation_metrics_valid_control_file, \
    NWM_RETROSPECTIVE_DIR, get_output_valid_control_file, get_output_valid_best_file, get_output_validation_iteration_plot_dir, \
    get_validation_metrics_valid_iteration_file, get_output_valid_iteration_file
from calibration.views.calibration_evaluation_views import get_iterations_for_calibration_job
from calibration.views.common import get_calibration_run, handle_exceptions, validate_response, validate_request, CerfException, \
    png_str_to_base64_url, ResponseError, truncate_large_fields, get_validation_run, get_job_description, \
    get_forecast_run, replace_nan_with_none
from calibration.views.end_of_job_processing import process_worker_dirs

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

    Args:
        request (Request): The request containing either POST data or query parameters.

    Returns:
        Response: A JSON response with the calibration run ID, list of plot names and descriptions, and run status.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'get_plot_names() request from {request.user.email} - {data}')

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

    # Get filtered plot definitions for the calibration run
    filtered_plot_definitions = get_filtered_plot_definitions(run)

    # Create a list of plot names with descriptions
    plot_names = [{'name': plot['name'], 'description': plot['description']} for plot in filtered_plot_definitions]

    response = {
        f"{run_type.lower()}_run_id": run.id,
        'plot_names': plot_names,
        'status': run.status.name}

    response_validator, error_response = validate_response(GetPLotNamesResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'get_plot_names() request from {request.user.email} - {response_validator.data}')

    return Response(response_validator.data)


def png_to_base64_url(png):
    """
    Converts a PNG file to a base64-encoded URL string.

    :param png: Path to the PNG file.
    :return: Base64 URL string if successful, or None if the file does not exist.
    """
    if png and os.path.exists(png):
        try:
            with open(png, "rb") as png_file:
                return png_str_to_base64_url(png_file.read())
        except IOError as e:
            raise CerfException(f"Failed to read PNG file: {e}")
    else:
        raise CerfException(f"Plot '{png}' does not exist")


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

    Args:
        request (Request): The request containing plot name and options.

    Returns:
        Response: A JSON response with plot details, or an error if the plot is not found.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'get_plot() request from {request.user.email} - {data}')

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
            return ResponseError(f"Plot '{plot_name}' not found for {run_type} Job {run.id}")

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
        # Apply replace_nan_with_none to the retrieved data
        if plot_data:
            plot_data = replace_nan_with_none(plot_data)
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
        f'Returning to {request.user.email} from get_plot() - {truncate_large_fields(response_validator.data, fields_to_truncate=["plot_url", "plot_data"], max_length=10)}')

    return Response(response_validator.data)


def determine_plot_location(run: CalibrationRun | ValidationRun, plot_definition: dict[str, Any]) -> str:
    """
    Determines the file location of the plot based on the plot definition's attributes.

    :param run: The run object, which could be either a calibration or validation run.
    :param plot_definition: Dictionary containing the plot's attributes, such as its location type.
    :return: The file path where the plot is expected to be located.
    :raises CerfException: If the plot's location type is unknown or the required directory cannot be found.
    """
    calibration_run = run if isinstance(run, CalibrationRun) else run.calibration_run
    match plot_definition['location']:
        case 'plot_valid':
            if isinstance(run, CalibrationRun) or run.validation_type != ValidationType.VALID_ITERATION.value:
                return get_output_validation_plot_dir(calibration_run)
            return get_output_validation_iteration_plot_dir(
                run.calibration_run, run.iteration_num, run.worker_name
            )

        case 'output_calibration':
            return get_output_calibration_run_dir(calibration_run)

        case 'plot_iteration':
            worker_dir = find_worker_with_non_empty_plot_iteration(calibration_run)
            if worker_dir is None:
                raise CerfException(f'Plots could not be found for {get_job_description(run)}')
            return os.path.join(worker_dir, 'Plot_Iteration')

        case 'forecast_output':
            # TODO Need to figure out the name of the forecast directory
            return 'dummy_dir'

        case _:
            raise CerfException(f"Unknown location '{plot_definition['location']}' in PlotDefinitions")


def get_plot_data(run: CalibrationRun | ValidationRun, plot_definition: dict[str, Any], start: int, limit: int) -> dict[str, Any]:
    """
    Retrieves data for a specific plot based on its definition and includes the total count of rows.

    :param run: The run object, either a calibration or validation run.
    :param plot_definition: Dictionary containing plot specifications.
    :param start: The starting index for pagination.
    :param limit: The maximum number of items to retrieve.
    :return: A dictionary containing 'data' and 'total_count'.
    """
    calibration_run = run if isinstance(run, CalibrationRun) else run.calibration_run
    plot_enum = PlotDefinitionsEnum(plot_definition['name'])
    worker_dir = None  # Cache worker directory to avoid multiple lookups

    match plot_enum:
        case PlotDefinitionsEnum.OBJECTIVE_FUNCTION_EVOLUTION:
            iterations = get_iterations_for_calibration_job(calibration_run)
            total_count = len(iterations)
            data = [
                {
                    'iteration': iteration.iteration_num,
                    'objective_function_value': iteration.objective_function_value
                }
                for iteration in iterations[start:start + limit]
            ]
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
            iterations = get_iterations_for_calibration_job(calibration_run)
            total_count = len(iterations)
            data = [
                {
                    'iteration': iteration.iteration_num,
                    'metrics': [{'name': metric.metric.name, 'value': metric.metric_value} for metric in iteration.iterationmetric_set.all()]
                }
                for iteration in iterations[start:start + limit]
            ]
            return {'data': data, 'total_count': total_count}

        case PlotDefinitionsEnum.PARAMETER_EVOLUTION:
            iterations = get_iterations_for_calibration_job(calibration_run)
            total_count = len(iterations)
            data = [
                {
                    'iteration': iteration.iteration_num,
                    'parameters': [{'name': parameter.calibration_parameter.name, 'value': parameter.tuned_value} for parameter in
                                   iteration.iterationparameter_set.all()]
                }
                for iteration in iterations[start:start + limit]
            ]
            return {'data': data, 'total_count': total_count}

        case PlotDefinitionsEnum.METRICS_VS_OBJECTIVE_FUNCTION:
            iterations = get_iterations_for_calibration_job(calibration_run)
            total_count = len(iterations)
            data = [
                {
                    'iteration': iteration.iteration_num,
                    'objective_function_value': iteration.objective_function_value,
                    'metrics': [{'name': metric.metric.name, 'value': metric.metric_value} for metric in iteration.iterationmetric_set.all()]
                }
                for iteration in iterations[start:start + limit]
            ]
            return {'data': data, 'total_count': total_count}

        case PlotDefinitionsEnum.STREAM_FLOW_PRECIPITATION:
            # Requires calculation, so we won't return data
            return {'data': [], 'total_count': 0}

        case PlotDefinitionsEnum.FLOW_DURATION_CURVES:
            # Requires calculation, so we won't return data
            return {'data': [], 'total_count': 0}

        case PlotDefinitionsEnum.COST_HISTORY:
            # Read cost history data from a file and paginate the result
            cost_history_file = get_cost_hist_file(calibration_run)
            if not os.path.exists(cost_history_file):
                logger.error(f"File not found: {cost_history_file}")
                raise FileNotFoundError(f"File not found: {cost_history_file}")
            data, total_count = count_and_read_file_in_chunks(cost_history_file, start, limit)

            return {'data': data, 'total_count': total_count}

        case PlotDefinitionsEnum.BAR_CHART_METRICS:
            # Files being read:
            # 1. Validation metrics for the "Valid Control" run
            # 2. Validation metrics for the "Valid Best" run
            # 3. NWM retrospective validation metrics
            # 4. (Optional) Validation metrics for a specific iteration if this is a ValidationRun of type "VALID_ITERATION"

            file_paths = [
                get_validation_metrics_valid_control_file(calibration_run),
                get_validation_metrics_valid_best_file(calibration_run),
                get_validation_metrics_nwm_retrospective_file(calibration_run)
            ]
            if isinstance(run, ValidationRun) and run.validation_type == ValidationType.VALID_ITERATION.value:
                # Add metrics file for the specific iteration
                file_paths.append(get_validation_metrics_valid_iteration_file(calibration_run, run.worker_name, run.iteration_num))

            # Column names to use for the respective files
            column_names = ["Valid Control", "Valid Best", "NWM Retrospective"]
            if isinstance(run, ValidationRun) and run.validation_type == ValidationType.VALID_ITERATION.value:
                column_names.append("Valid Iteration")

            # Combine and paginate data from the metrics files
            data, total_count = load_and_merge_hydrograph_files_with_pagination_and_count(file_paths, column_names, start, limit)
            return {'data': data, 'total_count': total_count}

        case PlotDefinitionsEnum.FLOW_DURATION_CURVES_VALIDATION:
            # Requires calculation, so we won't return data
            return {'data': [], 'total_count': 0}

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
            if isinstance(run, ValidationRun) and run.validation_type == ValidationType.VALID_ITERATION.value:
                # Add hydrograph data for the specific iteration
                file_paths.append(get_output_valid_iteration_file(calibration_run, run.worker_name, run.iteration_num))

            # Column names for clarity in the merged data
            column_names = ["Observation", "NWM Retro", "Valid Control", "Valid Best"]
            if isinstance(run, ValidationRun) and run.validation_type == ValidationType.VALID_ITERATION.value:
                column_names.append(run.worker_name)

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
        merged_df = load_files_and_merge(file_paths, column_names, key_col=key_col)
        total_count = len(merged_df)

        # Paginate results
        paginated_data = merged_df.iloc[start:start + limit].to_dict(orient="records")

        # Convert Timestamp objects to strings
        for row in paginated_data:
            if key_col in row and isinstance(row[key_col], pd.Timestamp):
                row[key_col] = row[key_col].isoformat()

        return paginated_data, total_count
    except Exception as e:
        logger.error(f"Error processing hydrograph files: {e}")
        raise CerfException(f"Failed to process hydrograph files: {e}")


def load_files_and_merge(file_paths: list[str], column_names: list[str], key_col: str = "time") -> pd.DataFrame:
    """
    Reads and merges multiple files into a single DataFrame using a common key column.

    :param file_paths: List of file paths to load.
    :param column_names: List of names for value columns in the merged DataFrame.
    :param key_col: The key column to merge on (default: "time").
    :return: Merged DataFrame containing data from all input files.
    :raises ValueError: If no valid files are found or no common key column exists for merging.
    """
    dataframes = []
    for file_path, col_name in zip(file_paths, column_names):
        if os.path.exists(file_path):
            try:
                # Map columns to standardized names for value
                column_mapping = {"q_cms": col_name, "sim_flow": col_name}
                df = read_and_prepare_hydrograph_files(file_path, column_mapping)
                dataframes.append(df)
            except Exception as e:
                logger.error(f"Error processing file {file_path}: {e}")

    if not dataframes:
        logger.error("No valid files found to merge.")
        return pd.DataFrame(columns=[key_col] + column_names)

    merged_df = dataframes[0]
    for df in dataframes[1:]:
        merged_df = merged_df.merge(df, on=key_col, how="inner")

    logger.debug(f"Merged DataFrame columns: {merged_df.columns.tolist()}, Shape: {merged_df.shape}")
    return merged_df


def read_and_prepare_hydrograph_files(file_path: str, column_mapping: dict[str, str]) -> pd.DataFrame:
    """
    Reads a hydrograph-related CSV file, dynamically identifies columns for time and values,
    formats data, and filters out invalid rows.

    :param file_path: Path to the CSV file.
    :param column_mapping: A dictionary mapping existing column names to standardized column names.
    :return: A DataFrame containing valid data, formatted for merging.
    :raises ValueError: If no timestamp column is found in the file.
    :raises FileNotFoundError: If the file does not exist.
    """
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        raise FileNotFoundError(f"File not found: {file_path}")

    # Read the CSV file into a DataFrame
    df = pd.read_csv(file_path)

    # Dynamically detect timestamp column
    timestamp_col = next(
        (col for col in df.columns if col.lower() in ["datetime", "time", "date", "timestamp"]),
        None
    )
    if not timestamp_col:
        raise ValueError(f"No timestamp column found in file {file_path}. Columns: {df.columns.tolist()}")

    # Rename detected timestamp column to a standard name
    df = df.rename(columns={timestamp_col: "time"})

    # Ensure the time column exists and is in datetime format
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df = df.dropna(subset=["time"])  # Drop rows with invalid timestamps

    # Rename value columns based on the provided mapping
    df = df.rename(columns=column_mapping)

    # Log the processed DataFrame
    logger.debug(f"Processed file: {file_path}, Columns: {df.columns.tolist()}, Shape: {df.shape}")
    return df


def count_and_read_file_in_chunks(
        file_path: str, start: int, limit: int
) -> tuple[list[dict[str, Any]], int]:
    """
    Counts the total number of rows (excluding the header) in a file and retrieves a specific slice of rows in a single pass.

    :param file_path: Path to the file to be read.
    :param start: Starting index for pagination (0-based, excluding the header).
    :param limit: Maximum number of rows to retrieve.
    :return: A tuple containing the paginated rows and total row count (excluding the header).
    :raises CerfException: If the file cannot be read due to an error.
    """
    total_count = 0
    paginated_lines = []

    try:
        with open(file_path, 'r') as file:
            # Read the header row
            header = next(file, None)
            if header is None:
                raise CerfException(f"File is empty or missing header: {file_path}")

            for current_line_number, line in enumerate(file):
                total_count += 1
                # Adjust the line numbers to exclude the header
                if start <= current_line_number < start + limit:
                    paginated_lines.append({'line_number': current_line_number + 1, 'content': line})
    except Exception as e:
        # Log and raise an exception if reading fails
        logger.error(f"Error reading file: {e}")
        raise CerfException(f"Failed to read file: {file_path}")

    return paginated_lines, total_count


def find_worker_with_non_empty_plot_iteration(calibration_run: CalibrationRun) -> str | None:
    """
    Uses process_worker_dirs to find the worker directory that has a non-empty 'Plot_Iteration' subdirectory.

    :param calibration_run: The run object to process
    :return: The path of the worker directory with a non-empty 'Plot_Iteration' directory, or None if not found
    """
    found_worker_dir = None

    # Custom function to check worker directories
    def check_worker(worker_dir: str, run: CalibrationRun):
        nonlocal found_worker_dir
        plot_iteration_dir = os.path.join(worker_dir, 'Plot_Iteration')

        # Check if 'Plot_Iteration' exists and is non-empty
        if os.path.isdir(plot_iteration_dir) and any(os.scandir(plot_iteration_dir)):
            found_worker_dir = worker_dir

    # Call process_worker_dirs to iterate through the worker directories
    process_worker_dirs(calibration_run, check_worker)

    return found_worker_dir
