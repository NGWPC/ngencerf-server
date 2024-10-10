import json
import logging
from pathlib import Path
from typing import Optional

from drf_spectacular.utils import OpenApiParameter, extend_schema, OpenApiResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.enums import StatusEnum, PlotDefinitionsEnum
from calibration.models import CalibrationRun
from calibration.util.calibration_validators import CalibrationRunSerializer, GetPLotNamesResponseSerializer, \
    ErrorResponseSerializer, GetPlotRequestSerializer, GetPlotResponseSerializer
from calibration.util.ngen_locations import get_output_calibration_run_dir, get_output_validation_run_dir
from calibration.views.common import get_calibration_run, handle_exceptions, validate_response, validate_request, CerfException, \
    png_str_to_base64_url, ResponseError
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
def get_plot_names(request):
    data = request.data if request.method == 'POST' else request.query_params.dict()

    logger.debug(f'get_plot_names() request from {request.user} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=[StatusEnum.RUNNING, StatusEnum.DONE])
    if error_return:
        return error_return

    filtered_plot_definitions = get_filtered_plot_definitions(run)

    # Create list of plot names with descriptions
    plot_names = [
        {'name': plot['name'], 'description': plot['description']}
        for plot in filtered_plot_definitions
    ]

    response = {'calibration_run_id': calibration_run_id, 'plot_names': plot_names, 'status': run.status.name}

    response_validator, error_response = validate_response(GetPLotNamesResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'get_plot_names() request from {request.user} - {response_validator.data}')

    return Response(response_validator.data)


def png_to_base64_url(png):
    if png:
        png_path = Path(png)
        if png_path.exists():
            with png_path.open("rb") as png_file:
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
def get_plot(request):
    data = request.data if request.method == 'POST' else request.query_params.dict()

    logger.debug(f'get_plot() request from {request.user} - {data}')

    validator, error_return = validate_request(GetPlotRequestSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    plot_name = validator.get('plot_name')

    run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=[StatusEnum.RUNNING, StatusEnum.DONE])
    if error_return:
        return error_return

    gage_id = run.gage.gage_id

    # Get cached plot definitions
    filtered_plot_definitions = get_filtered_plot_definitions(run, plot_name=plot_name)

    if not filtered_plot_definitions:
        return ResponseError(f"Plot '{plot_name}' not found for Calibration Run {run.id}")

    plot_info = filtered_plot_definitions[0]

    match plot_info['location']:
        case 'output_validation':
            location = get_output_validation_run_dir(run)
        case 'output_calibration':
            location = get_output_calibration_run_dir(run)
        case 'plot_iteration':
            location = find_non_empty_plot_iteration(run)
            if location is None:
                return ResponseError(f'Plots could not be found for Calibration Run {run.id}')
        case _:
            # Default case (if no match is found)
            return ResponseError(f"Unknown location {plot_info['location']} in PlotDefinitions")

    plot_file_name = plot_info['filename_mask'].format(gage_id=gage_id)
    plot_file_path = location / plot_file_name
    if not plot_file_path.exists():
        return ResponseError(f"Plot {plot_file_path} not found at expected location")

    plot_url = png_to_base64_url(plot_file_path)

    response = {'calibration_run_id': run.id, 'plot_name': plot_name, 'plot_file_name': plot_file_name, 'plot_url': plot_url}
    response_validator, error_response = validate_response(GetPlotResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user} from get_plot() - {response_validator.data}')

    return Response(response_validator.data)


def find_non_empty_plot_iteration(calibration_run: CalibrationRun) -> Optional[Path]:
    """
    Uses process_worker_dirs to find the 'Plot_Iteration' directory in a worker directory
    that is non-empty.

    :param calibration_run: The run object to process
    :return: The worker directory with a non-empty 'Plot_Iteration' directory, or None if not found
    """
    found_plot_iteration_dir: Optional[Path] = None

    # Custom function to check worker directories
    def check_worker(worker_dir, run: CalibrationRun):
        nonlocal found_plot_iteration_dir
        plot_iteration_dir = worker_dir / 'Plot_Iteration'

        # Check if 'Plot_Iteration' exists and is non-empty
        if plot_iteration_dir.is_dir() and any(plot_iteration_dir.iterdir()):
            found_plot_iteration_dir = plot_iteration_dir

    # Call process_worker_dirs to iterate through the worker directories
    process_worker_dirs(calibration_run, check_worker)

    return found_plot_iteration_dir


def get_filtered_plot_definitions(run, plot_name=None):
    # Load cached plot definitions with specific fields to be included in the returned dictionaries
    cached_plot_definitions = PlotDefinitionsEnum.active_choices_with_fields(
        fields=['name', 'description', 'valid_optimizations', 'validation', 'location', 'filename_mask']
    )

    # Filter the cached plot definitions based on the given criteria
    filtered_plot_definitions = [
        plot for plot in cached_plot_definitions
        # Include only plots that match the given plot name, if provided
        if (plot_name is None or plot['name'] == plot_name)
           # Check if the run's optimization name is in the list of valid optimizations for the plot
           and run.optimization.name in json.loads(plot['valid_optimizations'])
           # If the run does not have automatic validation enabled, include only plots with validation=False
           # Otherwise, include all plots (validation=True or False)
           and (plot['validation'] is False if not run.automatic_validation else True)
    ]

    return filtered_plot_definitions
