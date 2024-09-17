import json
import logging
from pathlib import Path

from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema, OpenApiResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.enums import StatusEnum
from calibration.models import PlotDefinitions
from calibration.util.calibration_validators import CalibrationRunSerializer, GetPLotNamesResponseSerializer, \
    ErrorResponseSerializer, CalibrationPlotNameSerializer, GetPlotRequestSerializer, GetPlotResponseSerializer
from calibration.views.common import get_run, handle_exceptions, validate_response, validate_request, CerfException, png_str_to_base64_url

logger = logging.getLogger(__name__)


@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: GetPLotNamesResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: ErrorResponseSerializer
    },
    parameters=[
        OpenApiParameter(name='calibration_run_id', description='ID of the calibration run', required=True, type=int)
    ],
    description="Get a list of plot names"
)
@api_view(['GET', 'POST'])
@handle_exceptions
def get_plot_names(request):
    # TODO need to clean this up with final directory names, etc
    data = request.data if request.method == 'POST' else request.query_params

    logger.debug(f'get_plot_names() request from {request.user} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_run(calibration_run_id, request.user, run_status=[StatusEnum.RUNNING, StatusEnum.DONE])
    if error_return:
        return error_return

    # If automatic_validation is True, retrieve all records
    # Otherwise, filter where 'validation' is False
    plot_names = list(PlotDefinitions.objects
                      .filter(Q(valid_optimizations__contains=json.dumps(run.optimization.name)) &
                              (Q(validation=False) if not run.automatic_validation else Q()))
                      .values('name', 'description'))

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
            raise CerfException(f"Plot {png} does not exist")
    return None


@extend_schema(
    request=GetPlotRequestSerializer,
    responses={
        200: GetPlotResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: ErrorResponseSerializer
    },
    parameters=[
        OpenApiParameter(name='calibration_run_id', description='ID of the calibration run', required=True, type=int)
    ],
    description="Return a base64 url for a plot image"
)
@api_view(['GET', 'POST'])
@handle_exceptions
def get_plot(request):
    data = request.data if request.method == 'POST' else request.query_params

    logger.debug(f'get_plot() request from {request.user} - {data}')

    validator, error_return = validate_request(GetPlotRequestSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    plot_name = validator.get('plot_name')

    run, error_return = get_run(calibration_run_id, request.user, run_status=[StatusEnum.RUNNING, StatusEnum.DONE])
    if error_return:
        return error_return

    gage_id = run.gage.gage_id

    plot_file_name = validator.get('cal_plot_name')
    # TODO Validate the plot name

    # Figure out the full path
    png_path = "foo"
    plot_url = png_to_base64_url(png_path) or "bar"

    response = {'calibration_run_id': run.id, 'plot_name': plot_file_name, 'plot_url': plot_url}
    response_validator, error_response = validate_response(GetPlotResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user} from get_plot() - {response_validator.data}')

    return response
