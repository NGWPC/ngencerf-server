import logging
import os
from typing import Optional, Dict, Any

from drf_spectacular.utils import OpenApiParameter, extend_schema, OpenApiResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.enums import StatusEnum, PlotDefinitionsEnum
from calibration.models import CalibrationRun, PlotDefinition
from calibration.util.caching import get_filtered_plot_definitions
from calibration.util.calibration_validators import CalibrationRunSerializer, GetPLotNamesResponseSerializer, \
    ErrorResponseSerializer, GetPlotRequestSerializer, GetPlotResponseSerializer
from calibration.util.ngen_locations import get_output_calibration_run_dir, get_output_validation_plot_dir
from calibration.views.calibration_evaluation_views import get_iterations_for_calibration_job
from calibration.views.common import get_calibration_run, handle_exceptions, validate_response, validate_request, CerfException, \
    png_str_to_base64_url, ResponseError, truncate_large_fields
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
    parameters=[
        OpenApiParameter(name='calibration_run_id', description='ID of the calibration run', required=True, type=int)
    ],
    description="Get a list of plot names"
)
@api_view(['GET', 'POST'])
@handle_exceptions
def get_plot_names(request) -> Response:
    """
    Retrieves the list of plot names and descriptions for a calibration run, filtered by applicable optimizations.

    Args:
        request (HttpRequest): The request containing either POST data or query parameters.

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
    if png:
        if os.path.exists(png):
            with open(png, "rb") as png_file:
                return png_str_to_base64_url(png_file.read())
        else:
            raise CerfException(f"Plot '{png}' does not exist")
    return None


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
    parameters=[
        OpenApiParameter(name='calibration_run_id', description='ID of the calibration run', required=True, type=int)
    ],
    description="Return a base64 url for a plot image"
)
@api_view(['GET', 'POST'])
@handle_exceptions
def get_plot(request) -> Response:
    """
    Retrieves a specific plot for a calibration run, returning the plot file location and optional data.

    Args:
        request (HttpRequest): The request containing plot name and options.

    Returns:
        Response: A JSON response with plot details, or an error if the plot is not found.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'get_plot() request from {request.user.email} - {data}')

    validator, error_return = validate_request(GetPlotRequestSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    plot_name = validator.get('plot_name')
    include_data = validator.get('include_data')

    run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=[StatusEnum.RUNNING, StatusEnum.DONE])
    if error_return:
        return error_return

    gage_id = run.gage.gage_id

    # Get a single plot definition
    plot_definition = get_filtered_plot_definitions(run, plot_name=plot_name, first_match=True)

    if not plot_definition:
        return ResponseError(f"Plot '{plot_name}' not found for Calibration Run {run.id}")


    match plot_definition['location']:
        case 'plot_valid':
            location = get_output_validation_plot_dir(run)
        case 'output_calibration':
            location = get_output_calibration_run_dir(run)
        case 'plot_iteration':
            location = find_non_empty_plot_iteration(run)
            if location is None:
                return ResponseError(f'Plots could not be found for Calibration Run {run.id}')
        case _:
            # Default case (if no match is found)
            return ResponseError(f"Unknown location '{plot_definition['location']}' in PlotDefinitions")

    plot_file_name = plot_definition['filename_mask'].format(gage_id=gage_id)
    plot_file_path = os.path.join(location, plot_file_name)

    if not os.path.exists(plot_file_path):
        return ResponseError(f"Plot {plot_file_path} not found at expected location")

    plot_url = png_to_base64_url(plot_file_path)

    logger.info(f'Retrieving plot {plot_file_name} from {plot_file_path}')

    plot_data = get_plot_data(run, plot_definition) if include_data else None

    response = {
        'calibration_run_id': run.id,
        'plot_name': plot_definition['name'],
        'plot_file_name': plot_file_name,
        'plot_url': plot_url
    }
    if include_data:
        if not plot_data:
            logger.warning(f"Data not available for {plot_definition['name']}")

        response['plot_data'] = plot_data

    response_validator, error_response = validate_response(GetPlotResponseSerializer, response, fields_to_truncate=['plot_url'])
    if error_response:
        return error_response
    logger.debug(
        f'Returning to {request.user.email} from get_plot() - {truncate_large_fields(response_validator.data, fields_to_truncate=["plot_url"])}')

    return Response(response_validator.data)


def get_plot_data(run: CalibrationRun, plot_definition: Dict[str, Any]):
    # Convert plot_definition.name to an enum member
    plot_enum = PlotDefinitionsEnum(plot_definition['name'])

    plot_data = []
    match plot_enum:
        case PlotDefinitionsEnum.OBJECTIVE_FUNCTION_EVOLUTION:
            iterations = get_iterations_for_calibration_job(run)
            for iteration in iterations:
                objective_function_element = {'iteration': iteration.iteration_num, 'objective_function_value': iteration.objective_function_value}
                plot_data.append(objective_function_element)

        case PlotDefinitionsEnum.HYDROGRAPH_EVOLUTION:
            pass
        case PlotDefinitionsEnum.METRIC_EVOLUTION:
            pass
        case PlotDefinitionsEnum.PARAMETER_EVOLUTION:
            pass
        case PlotDefinitionsEnum.SCATTERPLOT_STREAMFLOW:
            pass
        case PlotDefinitionsEnum.METRICS_VS_OBJECTIVE_FUNCTION:
            pass
        case PlotDefinitionsEnum.STREAM_FLOW_PRECIPITATION:
            pass
        case PlotDefinitionsEnum.FLOW_DURATION_CURVES:
            pass
        case PlotDefinitionsEnum.COST_HISTORY:
            pass
        case PlotDefinitionsEnum.BAR_CHART_METRICS:
            pass
        case PlotDefinitionsEnum.FLOW_DURATION_CURVES_VALIDATION:
            pass
        case PlotDefinitionsEnum.HYDROGRAPH_VALIDATION:
            pass
        case PlotDefinitionsEnum.STREAMFLOW_VALIDATION_PRECIPITATION:
            pass

    return plot_data

def find_non_empty_plot_iteration(calibration_run: CalibrationRun) -> Optional[str]:
    """
    Uses process_worker_dirs to find the 'Plot_Iteration' directory in a worker directory
    that is non-empty.

    :param calibration_run: The run object to process
    :return: The worker directory with a non-empty 'Plot_Iteration' directory, or None if not found
    """
    found_plot_iteration_dir: Optional[str] = None

    # Custom function to check worker directories
    def check_worker(worker_dir, run: CalibrationRun):
        nonlocal found_plot_iteration_dir
        plot_iteration_dir = os.path.join(worker_dir, 'Plot_Iteration')

        # Check if 'Plot_Iteration' exists and is non-empty
        if os.path.isdir(plot_iteration_dir) and any(os.scandir(plot_iteration_dir)):
            found_plot_iteration_dir = plot_iteration_dir

    # Call process_worker_dirs to iterate through the worker directories
    process_worker_dirs(calibration_run, check_worker)

    return found_plot_iteration_dir
