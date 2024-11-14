import logging

from drf_spectacular.utils import OpenApiParameter, extend_schema, OpenApiResponse
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from calibration.enums import ForecastCycleEnum
from calibration.util.calibration_validators import ErrorResponseSerializer, EmptySerializer, LoadForecastTabResponseSerializer
from calibration.views.common import handle_exceptions, validate_response, validate_request

logger = logging.getLogger(__name__)


@extend_schema(
    request=EmptySerializer,
    responses={
        200: LoadForecastTabResponseSerializer,
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
def load_forecast_tab(request: Request) -> Response:
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'load_forecast_tab() request from {request.user.email} - {data}')

    validator, error_return = validate_request(EmptySerializer, data)
    if error_return:
        return error_return

    cycle_values = ForecastCycleEnum.active_choices_with_fields(fields=['name', 'description'])

    response = {'forecast_cycle_values': cycle_values}

    response_validator, error_response = validate_response(LoadForecastTabResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'load_forecast_tab() request from {request.user.email} - {response_validator.data}')

    return Response(response_validator.data)
