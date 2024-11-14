import logging
import os
from typing import Any

import pandas as pd
from django.core.cache import cache
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework.decorators import api_view
from rest_framework.pagination import PageNumberPagination
from rest_framework.request import Request
from rest_framework.response import Response

from calibration.enums import StatusEnum, PlotDefinitionsEnum, ValidationType
from calibration.models import CalibrationRun, ValidationRun
from calibration.util.caching import get_filtered_plot_definitions
from calibration.util.calibration_validators import CalibrationRunSerializer, GetPLotNamesResponseSerializer, \
    ErrorResponseSerializer, GetPlotRequestSerializer, GetPlotResponseSerializer
from calibration.util.ngen_locations import get_output_calibration_run_dir, get_output_validation_plot_dir, get_output_iteration_file, \
    get_output_last_iteration_file, get_output_best_iteration_file, get_observational_file_for_job, get_cost_hist_file, \
    get_validation_metrics_valid_best_file, get_validation_metrics_nwm_retrospective_file, get_validation_metrics_valid_control_file, \
    NWM_RETROSPECTIVE_DIR, get_output_valid_control_file, get_output_valid_best_file, get_output_validation_iteration_plot_dir
from calibration.views.calibration_evaluation_views import get_iterations_for_calibration_job
from calibration.views.common import get_calibration_run, handle_exceptions, validate_response, validate_request, CerfException, \
    png_str_to_base64_url, ResponseError, truncate_large_fields, format_datetime, replace_nan_with_none, get_validation_run, get_job_description
from calibration.views.read_output import process_worker_dirs

logger = logging.getLogger(__name__)


@extend_schema(
    request=CalibrationRunSerializer,
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

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=[StatusEnum.RUNNING, StatusEnum.DONE])
    if error_return:
        return error_return

    # Get filtered plot definitions for the calibration run
    filtered_plot_definitions = get_filtered_plot_definitions(run)

    # Create a list of plot names with descriptions
    plot_names = [{'name': plot['name'], 'description': plot['description']} for plot in filtered_plot_definitions]

    response = {'calibration_run_id': calibration_run_id, 'plot_names': plot_names, 'status': run.status.name}

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
@api_view(['GET'])
@handle_exceptions
def get_plot(request: Request) -> Response:
    """
    Retrieves a specific plot for a calibration run or validation run, returning the plot file location and optional data with pagination support.
    If a calibration_run_id is given, then we can retrieve plots for the calibration run or the validation best run.
    If a validation_run_id is given, then we can retrieve plots for that specific validation run as well as the calibration run.

    Args:
        request (Request): The request containing plot name and options.

    Returns:
        Response: A JSON response with plot details, or an error if the plot is not found.
    """
    data = request.query_params
    logger.debug(f'get_plot() request from {request.user.email} - {data}')

    validator, error_return = validate_request(GetPlotRequestSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    validation_run_id = validator.get('validation_run_id')
    plot_name = validator.get('plot_name')
    include_data = validator.get('include_data')
    force_include_plot = validator.get('force_include_plot')
    page = validator.get('page')
    page_size = validator.get('page_size')

    # Replace spaces with underscores in plot_name to avoid CacheKeyWarning
    sanitized_plot_name = plot_name.replace(" ", "_")
    # Base cache key common part
    cache_key_base = f"{sanitized_plot_name}_{calibration_run_id or validation_run_id}"
    cache_key_plot_data = f"plot_data_{cache_key_base}"
    cache_key_plot_url = f"plot_url_{cache_key_base}"

    # Try to retrieve cached data
    cached_plot_data = cache.get(cache_key_plot_data)
    plot_url = cache.get(cache_key_plot_url)
    plot_file_name = None
    plot_url_calculated = False  # Tracks if plot_url was calculated in this request

    # Select the correct function and retrieve the run object
    run_func = get_calibration_run if calibration_run_id else get_validation_run
    run_id = calibration_run_id or validation_run_id

    run, error_return = run_func(run_id, request.user, run_status=[StatusEnum.RUNNING, StatusEnum.DONE])
    if error_return:
        return error_return

    # Identify the associated calibration run, handling both calibration and validation cases
    calibration_run = run if calibration_run_id else run.calibration_run

    # Fetch plot definition if needed for force_include_plot, include_data, or when plot_url is missing
    plot_definition = None
    if force_include_plot or not plot_url or include_data:
        plot_definition = get_filtered_plot_definitions(calibration_run, plot_name=plot_name, first_match=True)
        if not plot_definition:
            return ResponseError(f"Plot '{plot_name}' not found for Calibration Run {run.id}")

    # Process plot_url if it doesn't exist in the cache or if force_include_plot is True
    if force_include_plot or not plot_url:
        gage_id = calibration_run.gage.gage_id

        # Determine plot location based on plot definition
        location = determine_plot_location(calibration_run, run, plot_definition)
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
    paginated_data = None
    pagination_metadata = None
    if include_data:
        plot_data = cached_plot_data if cached_plot_data is not None else get_plot_data(calibration_run, plot_definition)
        if not plot_data:
            logger.warning(f"Data not available for {plot_name}")
        else:
            paginator = PlotDataPagination(page=page, page_size=page_size)
            paginated_data = paginator.paginate_queryset(plot_data, request)
            paginated_data = replace_nan_with_none(paginated_data) if paginated_data else []

            # Extract pagination metadata if paginated_data is not empty
            if paginated_data:
                pagination_metadata = {
                    'count': paginator.page.paginator.count,
                    'total_pages': paginator.page.paginator.num_pages,
                    'current_page': paginator.page.number,
                    'next': paginator.get_next_link(),
                    'previous': paginator.get_previous_link()
                }

    response = {
        'calibration_run_id': calibration_run.id,
        'plot_name': plot_name,
    }

    # Include plot_url based on force_include_plot or whether it was just calculated
    if force_include_plot or plot_url_calculated:
        response['plot_url'] = plot_url

    # Include plot_file_name if available
    if plot_file_name:
        response['plot_file_name'] = plot_file_name

    if validation_run_id:
        response['validation_run_id'] = validation_run_id
    if include_data:
        response['plot_data'] = paginated_data or plot_data
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


def determine_plot_location(calibration_run: CalibrationRun, run: CalibrationRun | ValidationRun, plot_definition: dict[str, Any]) -> str:
    """
    Determines the location of the plot based on the plot definition's location attribute.

    :param calibration_run: The calibration run object.
    :param run: The run object, either a calibration or validation run.
    :param plot_definition: The plot definition dictionary containing location details.
    :return: The determined plot location as a string path.
    """
    match plot_definition['location']:
        case 'plot_valid':
            if calibration_run.id or run.validation_type != ValidationType.VALID_ITERATION.value:
                return get_output_validation_plot_dir(calibration_run)
            return get_output_validation_iteration_plot_dir(
                calibration_run, run.iteration.iteration_num, run.iteration.worker_name
            )

        case 'output_calibration':
            return get_output_calibration_run_dir(calibration_run)

        case 'plot_iteration':
            worker_dir = find_worker_with_non_empty_plot_iteration(calibration_run)
            if worker_dir is None:
                raise ResponseError(f'Plots could not be found for {get_job_description(run)}')
            return os.path.join(worker_dir, 'Plot_Iteration')

        case _:
            raise ResponseError(f"Unknown location '{plot_definition['location']}' in PlotDefinitions")


class PlotDataPagination(PageNumberPagination):
    def __init__(self, page: int = 1, page_size: int = 100):
        super().__init__()
        self.page_number = page
        self.page_size = page_size


def get_plot_data(run: CalibrationRun, plot_definition: dict[str, Any]) -> list[Any]:
    """
    Retrieves data for a specific plot based on its definition.

    :param run: The calibration run object.
    :param plot_definition: Dictionary containing plot specifications.
    :return: List of data entries or empty list if no data is available.
    """
    plot_enum = PlotDefinitionsEnum(plot_definition['name'])
    worker_dir = None  # Cache worker directory to avoid multiple lookups

    match plot_enum:
        case PlotDefinitionsEnum.OBJECTIVE_FUNCTION_EVOLUTION:
            return [
                {'iteration': iteration.iteration_num,
                 'objective_function_value': iteration.objective_function_value}
                for iteration in get_iterations_for_calibration_job(run)
            ]

        case PlotDefinitionsEnum.HYDROGRAPH_EVOLUTION | PlotDefinitionsEnum.SCATTERPLOT_STREAMFLOW:
            worker_dir = worker_dir or find_worker_with_non_empty_plot_iteration(run)
            file_paths = [
                get_observational_file_for_job(run),  # Observation
                get_output_iteration_file(run, 0, worker_dir),  # Iteration
                get_output_last_iteration_file(run, worker_dir),  # Last Iteration
                get_output_best_iteration_file(run, worker_dir)  # Best Iteration
            ]
            column_names = ["Observation", "Control Run", "Last Run", "Best Run"]
            return load_and_merge_hydrograph_files(file_paths, column_names)

        case PlotDefinitionsEnum.METRIC_EVOLUTION:
            return [
                {
                    'iteration': iteration.iteration_num,
                    'metrics': [{'name': metric.metric.name, 'value': metric.metric_value} for metric in iteration.iterationmetric_set.all()]
                }
                for iteration in get_iterations_for_calibration_job(run)
            ]

        case PlotDefinitionsEnum.PARAMETER_EVOLUTION:
            return [
                {
                    'iteration': iteration.iteration_num,
                    'parameters': [{'name': parameter.calibration_parameter.name, 'value': parameter.tuned_value} for parameter in
                                   iteration.iterationparameter_set.all()]
                }
                for iteration in get_iterations_for_calibration_job(run)
            ]

        case PlotDefinitionsEnum.METRICS_VS_OBJECTIVE_FUNCTION:
            return [
                {
                    'iteration': iteration.iteration_num,
                    'objective_function_value': iteration.objective_function_value,
                    'metrics': [{'name': metric.metric.name, 'value': metric.metric_value} for metric in iteration.iterationmetric_set.all()]
                }
                for iteration in get_iterations_for_calibration_job(run)
            ]

        case PlotDefinitionsEnum.STREAM_FLOW_PRECIPITATION:
            # Requires calculation, so we won't return data
            return []

        case PlotDefinitionsEnum.FLOW_DURATION_CURVES:
            # Requires calculation, so we won't return data
            return []

        case PlotDefinitionsEnum.COST_HISTORY:
            cost_history = get_cost_hist_file(run)
            if not os.path.exists(cost_history):
                logger.error(f"File not found: {cost_history}")
                raise FileNotFoundError(f"File not found: {cost_history}")
            try:
                df = pd.read_csv(cost_history, dtype=None)  # Automatic type inference
                return df.to_dict(orient="records")  # Convert to list of dicts
            except Exception as e:
                logger.error(f"Error reading cost history file: {e}")
                return []

        case PlotDefinitionsEnum.BAR_CHART_METRICS:
            files = [
                get_validation_metrics_valid_control_file(run),
                get_validation_metrics_valid_best_file(run),
                get_validation_metrics_nwm_retrospective_file(run)
            ]
            plot_data = []

            # Read each file as a DataFrame, apply type inference, and convert to dict
            for file_path in files:
                df = pd.read_csv(file_path, dtype=None)  # Allow pandas to infer types
                plot_data.append(df.to_dict(orient="records"))

            return plot_data

        case PlotDefinitionsEnum.FLOW_DURATION_CURVES_VALIDATION:
            # Requires calculation, so we won't return data
            return []

        case PlotDefinitionsEnum.HYDROGRAPH_VALIDATION:
            # Define files and column names for HYDROGRAPH_VALIDATION
            file_paths = [
                get_observational_file_for_job(run),  # Observation
                os.path.join(NWM_RETROSPECTIVE_DIR, f'{run.gage.gage_id}.csv'),  # NWM Retro
                get_output_valid_control_file(run),  # Valid Control
                get_output_valid_best_file(run)  # Valid Best
                # get_output_validation_iteration_file(run)
            ]
            column_names = ["Observation", "NWM Retro", "Valid Control", "Valid Best"]
            return load_and_merge_hydrograph_files(file_paths, column_names)

        case PlotDefinitionsEnum.STREAMFLOW_VALIDATION_PRECIPITATION:
            # Requires calculation, so we won't return data
            return []

    logger.error(f"Data handler not found for '{plot_enum}'")
    return []  # Return an empty list or raise an exception if no match is found


def find_worker_with_non_empty_plot_iteration(calibration_run: CalibrationRun) -> str | None:
    """
    Uses process_worker_dirs to find the worker directory that has a non-empty 'Plot_Iteration' subdirectory.

    :param calibration_run: The run object to process
    :return: The path of the worker directory with a non-empty 'Plot_Iteration' directory, or None if not found
    """
    found_worker_dir = None

    # Custom function to check worker directories
    def check_worker(worker_dir, run: CalibrationRun):
        nonlocal found_worker_dir
        plot_iteration_dir = os.path.join(worker_dir, 'Plot_Iteration')

        # Check if 'Plot_Iteration' exists and is non-empty
        if os.path.isdir(plot_iteration_dir) and any(os.scandir(plot_iteration_dir)):
            found_worker_dir = worker_dir

    # Call process_worker_dirs to iterate through the worker directories
    process_worker_dirs(calibration_run, check_worker)

    return found_worker_dir


# Helper function to read and prepare each CSV file
def read_and_prepare_hydrograph_files(file_path: str, time_col: str = 'time', value_col: str = 'value') -> pd.DataFrame:
    """
    Reads a CSV file, renames columns to 'time' and 'value', converts 'time' to datetime, and removes rows with invalid 'time'.

    :param file_path: Path to the CSV file
    :param time_col: Column name for time (default is 'time')
    :param value_col: Column name for values (default is 'value')
    :return: DataFrame with 'time' and renamed 'value' column
    """
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        raise FileNotFoundError(f"File not found: {file_path}")

    df = pd.read_csv(file_path)
    datetime_column, value_column = df.columns[:2]
    df = df.rename(columns={datetime_column: time_col, value_column: value_col})
    df[time_col] = pd.to_datetime(df[time_col], errors='coerce')
    return df.dropna(subset=[time_col])


# Helper function to load and merge hydrograph files with dynamic column names
def load_and_merge_hydrograph_files(file_paths: list[str], column_names: list[str]) -> list[dict[str, Any]]:
    """
    Loads CSV files, renames columns based on provided names, merges on 'time', and returns data as a list of dicts.

    :param file_paths: List of file paths to load
    :param column_names: List of new column names for each file's value column
    :return: Merged data as a list of dictionaries with formatted 'time' values
    """
    dataframes = []
    for file_path, col_name in zip(file_paths, column_names):
        df = read_and_prepare_hydrograph_files(file_path)
        dataframes.append(df.rename(columns={"value": col_name}))

    if not dataframes:
        logger.error("No data to merge; all files were missing or empty.")
        return []

    # Merge DataFrames on 'time' column, applying inner join to retain only matching rows across all files
    merged_df = dataframes[0]
    for df in dataframes[1:]:
        merged_df = merged_df.merge(df, on="time", how="inner")

    # Format 'time' column
    merged_df['time'] = merged_df['time'].apply(format_datetime)
    return merged_df.to_dict(orient="records")
