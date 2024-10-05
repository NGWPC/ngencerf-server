import logging

from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.enums import StatusEnum
from calibration.util.calibration_validators import GenericMessageResponseSerializer, ErrorResponseSerializer, \
    CalibrationRunSerializer
from calibration.views.common import handle_exceptions, validate_response, get_calibration_run, validate_request

logger = logging.getLogger(__name__)


@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: GenericMessageResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },

    description="Get all jobs"
)
@api_view(['POST', 'GET'])
# @permission_classes([AllowAny])
@handle_exceptions
def get_job_results(request):
    data = request.data if request.method == 'POST' else request.query_params.dict()

    logger.debug(f'get_job() request from {request.user} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    # Only Done or Failed
    run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=[StatusEnum.DONE, StatusEnum.FAILED])
    if error_return:
        return error_return

    # Return metrics and parameters from results

    response = {'message': "Not implemented yet", 'calibration_run_id': calibration_run_id, 'status': run.status.name}
    print('response', response)

    response_validator, error_response = validate_response(GenericMessageResponseSerializer, response)
    if error_response:
        return error_response

    logger.debug(f'Returning to {request.user} from get_jobs() - {response_validator.data}')
    return Response(response_validator.data)
