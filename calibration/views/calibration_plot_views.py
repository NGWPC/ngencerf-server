import logging
import mimetypes
import os

from django.db.models import Value, CharField
from django.db.models.functions import Concat
from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, extend_schema, PolymorphicProxySerializer
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.enums import StatusEnum
from calibration.models import PlotDefinitions
from calibration.util.calibration_validators import CalibrationRunSerializer, LoadPlotDefinitionsResponseSerializer, ExceptionResponseSerializer, \
    ValidationExceptionSerializer, ErrorResponseSerializer, CalibrationPlotNameSerializer
from calibration.util.ngen_locations import CAL_PLOTS_DIR
from calibration.views.common import get_run, handle_exceptions, validate_request, validate_response

logger = logging.getLogger(__name__)


@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: LoadPlotDefinitionsResponseSerializer,
        400: PolymorphicProxySerializer(
            component_name='MultipleErrorResponse',
            serializers=[
                ValidationExceptionSerializer,
                ErrorResponseSerializer,
            ],
            resource_type_field_name=None
        ),
        500: ExceptionResponseSerializer
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

    calibration_run_id = validator.data.get('calibration_run_id')

    run, errorReturn = get_run(calibration_run_id, request.user, run_status=[StatusEnum.RUNNING, StatusEnum.DONE, StatusEnum.SAVED])
    if errorReturn:
        return errorReturn

    gage_id = run.gage.gage_id

    plots = (
        PlotDefinitions.objects.filter(is_active=True)
        .annotate(filename=Concat(Value(gage_id), 'filename_mask', output_field=CharField()))
        .values('name', 'description', 'filename')
    )

    response = {'calibration_run_id': calibration_run_id, 'plot_list': list(plots)}

    response = {key: value for key, value in response.items() if value not in [None, '', [], {}]}

    response_validator, error_response = validate_response(LoadPlotDefinitionsResponseSerializer, response)
    logger.debug(f'get_plot_names() request from {request.user} - {response_validator.data}')

    return Response(response_validator.data)


def download_plot(filename):
    # @TODO - once decided, replace settings.CAL_PLOTS_DIR with the final location for the plots 
    file_path = CAL_PLOTS_DIR + '/' + filename

    fileData = open(file_path, "r")
    file_mimetype = mimetypes.guess_type(file_path)
    response = HttpResponse(fileData, content_type=file_mimetype)
    response['X-Sendfile'] = file_path
    response['Content-Length'] = os.stat(file_path).st_size
    response['Content-Disposition'] = 'attachment; filename=%s' % str(filename)

    return response


@extend_schema(
    request=CalibrationPlotNameSerializer,
    responses={
        # 200: ,
        400: PolymorphicProxySerializer(
            component_name='MultipleErrorResponse',
            serializers=[
                ValidationExceptionSerializer,
                ErrorResponseSerializer,
            ],
            resource_type_field_name=None
        ),
        500: ExceptionResponseSerializer
    },
    parameters=[
        OpenApiParameter(name='calibration_run_id', description='ID of the calibration run', required=True, type=int)
    ],
    description="Get a list of plot names"
)
@api_view(['GET', 'POST'])
@handle_exceptions
def get_plot(request):
    data = request.data if request.method == 'POST' else request.query_params

    logger.debug(f'get_plot() request from {request.user} - {data}')

    validator, error_return = validate_request(CalibrationPlotNameSerializer, data)
    if error_return:
        return error_return

    plot_file_name = validator.data.get('cal_plot_name')

    response = download_plot(plot_file_name)

    logger.debug(f'Response to get_plot() request from {request.user} : \n {response}')

    return response
