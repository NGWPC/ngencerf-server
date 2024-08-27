import logging

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.enums import StatusEnum
from calibration.models import CalibrationRun
from calibration.models.status import Status
from calibration.util.calibration_validators import GetJobsResponseSerializer, FooterResponseSerializer, \
    ErrorResponseSerializer, CreateCalibrationRunSerializer, \
    GageIdOptionalSerializer, CalibrationRunSerializer, LoadCalibrationRunResponseSerializer
from calibration.views.calibration_import_export_views import load_calibration_run_data
from calibration.views.common import handle_exceptions, validate_request, validate_response, get_run

logger = logging.getLogger(__name__)


@extend_schema(
    request=None,
    responses={
        201: CreateCalibrationRunSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: ErrorResponseSerializer
    },
    description="Create a new calibration"
)
@api_view(['POST'])
@handle_exceptions
# @permission_classes([AllowAny])
def create_calibration_run(request):
    logger.debug(f'create_calibration_run() request from {request.user}')

    with transaction.atomic():
        run = CalibrationRun.objects.create(is_active=True, owner=request.user, status=Status.objects.get(name=StatusEnum.SAVED.value))

        response = {'message': f'Calibration Run {run.id} created', 'calibration_run_id': run.id}

        response_validator, error_response = validate_response(CreateCalibrationRunSerializer, response)
        if error_response:
            return error_response

        logger.debug(f'Returning to {request.user} from create_calibration_run() - {response_validator.data}')
        return Response(response_validator.data, status=status.HTTP_201_CREATED)


@extend_schema(
    request=GageIdOptionalSerializer,
    responses={
        200: GetJobsResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: ErrorResponseSerializer
    },

    description="Get all jobs"
)
@api_view(['POST', 'GET'])
# @permission_classes([AllowAny])
@handle_exceptions
def get_jobs(request):
    data = request.data if request.method == 'POST' else request.query_params

    logger.debug(f'get_jobs() request from {request.user} - {data}')

    validator, error_return = validate_request(GageIdOptionalSerializer, data)
    if error_return:
        return error_return

    gage_id = validator.data.get('gage_id')

    query = Q(owner=request.user)
    if gage_id:
        query &= Q(gage__gage_id=gage_id) & Q(status__name__in=[StatusEnum.DONE, StatusEnum.FAILED])

    jobs = CalibrationRun.objects.filter(query)

    # Get all jobs for this user
    runs = list(jobs
                .values('id', 'gage__gage_id', 'run_date', 'calibration_start_period', 'calibration_end_period',
                        'status__name', 'owner__username', formulation_name=F('user_formulation_name')))
    for r in runs:
        r['calibration_run_id'] = r.pop('id')
        r['gage_id'] = r.pop('gage__gage_id')
        r['status'] = r.pop('status__name')
        r['owner'] = r.pop('owner__username')

    response = {'jobs': runs}
    print('response', response)

    response_validator, error_response = validate_response(GetJobsResponseSerializer, response)
    if error_response:
        return error_response

    logger.debug(f'Returning to {request.user} from get_jobs() - {response_validator.data}')
    return Response(response_validator.data)


@extend_schema(
    request=None,
    responses={
        200: FooterResponseSerializer,
        500: ErrorResponseSerializer
    },
    description="Load gage tab data"
)
@api_view(['POST', 'GET'])
@handle_exceptions
def get_footer(request):
    response = {"version": settings.VERSION, "contact_email": settings.CONTACT_EMAIL}

    response_validator, error_response = validate_response(FooterResponseSerializer, response)
    if error_response:
        return error_response

    logger.debug(f'Returning to {request.user} from get_footer() - {response_validator.data}')
    return Response(response_validator.data)


@extend_schema(
    request=None,
    responses={
        200: LoadCalibrationRunResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: ErrorResponseSerializer
    },
    description="Load all data for a previously saved calibration"
)
@api_view(['POST', 'GET'])
@handle_exceptions
def load_calibration_run(request):
    data = request.data if request.method == 'POST' else request.query_params

    logger.debug(f'load_formulation_tab() request from {request.user} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.data.get('calibration_run_id')

    run, errorReturn = get_run(calibration_run_id, request.user)
    if errorReturn:
        return errorReturn

    calibration_run_data = load_calibration_run_data(run, export=False)

    response_validator, error_response = validate_response(LoadCalibrationRunResponseSerializer, calibration_run_data)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user} from load_formulation_tab() - {response_validator.data}')

    return Response(response_validator.data)
