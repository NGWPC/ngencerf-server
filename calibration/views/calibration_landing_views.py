import json
import logging
from json.decoder import JSONDecodeError

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from drf_spectacular.utils import extend_schema, PolymorphicProxySerializer
from rest_framework import serializers
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from calibration.enums import StatusEnum
from calibration.models import CalibrationRun
from calibration.models.status import Status
from calibration.util.calibration_validators import GenericMessageResponseSerializer, GetJobsResponseSerializer, FooterResponseSerializer, \
    ErrorResponseSerializer, ExceptionResponseSerializer, ValidationErrorSerializer, ValidationExceptionSerializer, CreateCalibrationRunSerializer, \
    GageIdOptionalSerializer
from calibration.views.common import ResponseError

logger = logging.getLogger(__name__)


@extend_schema(
    request=None,
    responses={
        201: GenericMessageResponseSerializer,
        400: PolymorphicProxySerializer(
            component_name='MultipleErrorResponse',
            serializers=[
                ValidationExceptionSerializer,
                ValidationErrorSerializer,
                ErrorResponseSerializer,
            ],
            resource_type_field_name=None
        ),
    },
    description="Create a new calibration"
)
@api_view(['POST'])
# @permission_classes([AllowAny])
def create_calibration_run(request):
    try:
        print('user', request.user)
        logger.debug(f'create_calibration_run() request from {request.user}')

        with transaction.atomic():
            run = CalibrationRun.objects.create(is_active=True, owner=request.user, status=Status.objects.get(name=StatusEnum.SAVED.value))

            response = {'message': f'Calibration Run {run.id} created', 'calibration_run_id': run.id}
            serializer = CreateCalibrationRunSerializer(data=response)
            if not serializer.is_valid():
                return ResponseError(f'Data format error returning from create_calibration_run() - {serializer.errors}',
                                     httpStatus=status.HTTP_500_INTERNAL_SERVER_ERROR)
            logger.debug(f'Returning to {request.user} from create_calibration_run() - {serializer.data}')
            return Response(serializer.data, status=status.HTTP_201_CREATED)
    except JSONDecodeError as e:
        logger.exception(e)
        return Response({'validation_error': 'JSON parsing error - ' + str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except serializers.ValidationError as e:
        logger.exception(e)
        return Response({'validation_error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        response = {'exception': str(e)}
        serializer = ExceptionResponseSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    request=GageIdOptionalSerializer,
    responses={
        200: GetJobsResponseSerializer,
        400: PolymorphicProxySerializer(
            component_name='MultipleErrorResponse',
            serializers=[
                ValidationExceptionSerializer,
                ValidationErrorSerializer,
                ErrorResponseSerializer,
            ],
            resource_type_field_name=None
        ),
        500: ExceptionResponseSerializer
    },

    description="Get all jobs"
)
@api_view(['POST', 'GET'])
# @permission_classes([AllowAny])
def get_jobs(request):
    try:

        if request.method == 'POST':
            data = json.loads(request.body or '{}')
        else:
            data = request.GET

        logger.debug(f'get_jobs() request from {request.user}')

        validator = GageIdOptionalSerializer(data=data)
        validator.is_valid(raise_exception=True)

        gage_id = validator.data.get('gage_id')

        jobs = CalibrationRun.objects.filter(
            Q(owner=request.user) &
            Q(gage__gage_id=gage_id) if gage_id else Q()
        )

        # Get all jobs for this user
        runs = list(jobs
                    .values('id', 'gage__gage_id', 'run_date', 'calibration_start_period', 'calibration_end_period',
                            'status__name',  'owner__username', formulation_name=F('user_formulation_name')))
        for r in runs:
            r['calibration_run_id'] = r.pop('id')
            r['gage_id'] = r.pop('gage__gage_id')
            r['status'] = r.pop('status__name')
            r['owner'] = r.pop('owner__username')

        response = {'jobs': runs}
        print('response', response)

        serializer = GetJobsResponseSerializer(data=response)
        if not serializer.is_valid():
            return ResponseError(f'Data format error returning from get_jobs() - {serializer.errors}',
                                 httpStatus=status.HTTP_500_INTERNAL_SERVER_ERROR)

        logger.debug(f'Returning to {request.user} from get_jobs() - {serializer.data}')
        return Response(serializer.data)
    except JSONDecodeError as e:
        response = {'validation_error': 'JSON parsing error - ' + str(e)}
        serializer = ValidationErrorSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)
    except ValidationError as e:
        response = {'validation_error': str(e)}
        serializer = ValidationExceptionSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        response = {'exception': str(e)}
        serializer = ExceptionResponseSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    request=None,
    responses={
        200: FooterResponseSerializer,
        500: ExceptionResponseSerializer
    },
    description="Load gage tab data"
)
@api_view(['POST', 'GET'])
def get_footer(request):
    try:
        response = {"version": settings.VERSION, "contact_email": settings.CONTACT_EMAIL}
        serializer = FooterResponseSerializer(data=response)
        if not serializer.is_valid():
            return ResponseError(f'Data format error returning from get_footer() - {serializer.errors}',
                                 httpStatus=status.HTTP_500_INTERNAL_SERVER_ERROR)
        logger.debug(f'Returning to {request.user} from get_footer() - {serializer.data}')
        return Response(serializer.data)
    except Exception as e:
        response = {'exception': str(e)}
        serializer = ExceptionResponseSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
