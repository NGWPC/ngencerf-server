import base64
import logging
import mimetypes
import os
from pathlib import Path

from django.db.models import Value, CharField
from django.db.models.functions import Concat
from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, extend_schema, OpenApiResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.enums import StatusEnum
from calibration.models import PlotDefinitions
from calibration.util.calibration_validators import CalibrationRunSerializer, LoadPlotDefinitionsResponseSerializer, \
    ErrorResponseSerializer, CalibrationPlotNameSerializer, GetPlotRequestSerializer
from calibration.util.ngen_locations import CAL_PLOTS_DIR
from calibration.views.common import get_run, handle_exceptions, validate_response, validate_request, CerfException, png_str_to_base64_url

logger = logging.getLogger(__name__)


@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: LoadPlotDefinitionsResponseSerializer,
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

    gage_id = run.gage.gage_id

    plots = (
        PlotDefinitions.objects.filter(is_active=True)
        .annotate(filename=Concat(Value(gage_id), 'filename_mask', output_field=CharField()))
        .values('name', 'description', 'filename')
    )

    response = {'calibration_run_id': calibration_run_id, 'plot_list': list(plots), 'status': run.status.name}

    response = {key: value for key, value in response.items() if value not in [None, '', [], {}]}

    response_validator, error_response = validate_response(LoadPlotDefinitionsResponseSerializer, response)
    logger.debug(f'get_plot_names() request from {request.user} - {response_validator.data}')

    return Response(response_validator.data)


# def download_plot(filename):
#     # @TODO - once decided, replace settings.CAL_PLOTS_DIR with the final location for the plots
#     file_path = CAL_PLOTS_DIR + '/' + filename
#
#     fileData = open(file_path, "r")
#     file_mimetype = mimetypes.guess_type(file_path)
#     response = HttpResponse(fileData, content_type=file_mimetype)
#     response['X-Sendfile'] = file_path
#     response['Content-Length'] = os.stat(file_path).st_size
#     response['Content-Disposition'] = 'attachment; filename=%s' % str(filename)
#
#     return response


def png_to_base64_url(png):
    if png:
        png_path = Path(png)
        if png.exists():
            with png_path.open("rb") as png_file:
                return png_str_to_base64_url(png_file.read())
        else:
            raise CerfException(f"File {png} does not exist")
    return None




@extend_schema(
    request=CalibrationPlotNameSerializer,
    responses={
        200: CalibrationPlotNameSerializer,
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

    run, error_return = get_run(calibration_run_id, request.user, run_status=[StatusEnum.RUNNING, StatusEnum.DONE])
    if error_return:
        return error_return

    gage_id = run.gage.gage_id




    plot_file_name = validator.get('cal_plot_name')
    # TODO Validate the plot name

    # Figure out the full path
    png_path = None
    url = png_to_base64_url(png_path)




    response = {'calibration_run_id': run.id, 'plot_name': plot_name, 'plot_url': plot_url}
    response_validator, error_response = validate_response(UploadGeopackageResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user} from get_plot() - {response_validator.data}')


    return response
