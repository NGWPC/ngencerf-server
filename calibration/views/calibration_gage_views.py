import base64
import logging
import os
import shutil

from botocore.exceptions import ClientError
from django.core.files.storage import FileSystemStorage
from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.enums import ObservationalSourceEnum, ForcingSourceEnum
from calibration.models import Gage, ForcingSource, ObservationalSource, Domain
from calibration.util.calibration_validators import SaveGageRequestSerializer, GageIdSerializer, CalibrationRunSerializer, UploadForcingSerializer, \
    SaveGageResponseSerializer, \
    LoadGageResponseSerializer, GageSerializer, GenericResponseSerializer, ErrorResponseSerializer, \
    UploadObservationalSerializer
from calibration.util.geopkg import gpkg_to_png_selected_layers
from calibration.util.ngen_locations import get_observation_dir, get_forcing_dir, get_observation_file, get_geopackage_file
from calibration.views import ngen_cal_input
from calibration.views.common import get_run, ResponseError, handle_exceptions, validate_request, validate_response
from calibration.views.hydrofabric import get_forcing_data_from_hydrofabric, get_observational_data_from_hydrofabric, get_geopackage_from_hydrofabric

logger = logging.getLogger(__name__)


@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: LoadGageResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        404: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Gage not found"
        ),
        500: ErrorResponseSerializer
    },
    parameters=[
        OpenApiParameter(name='calibration_run_id', description='ID of the calibration run', required=True, type=int)
    ],
    description="Load gage tab data"
)
@api_view(['GET', 'POST'])
# @permission_classes([AllowAny])
@handle_exceptions
def load_gage_tab(request):
    data = request.data if request.method == 'POST' else request.query_params

    logger.debug(f'load_gage_tab() request from {request.user} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.data.get('calibration_run_id')

    run, errorReturn = get_run(calibration_run_id, request.user)
    if errorReturn:
        return errorReturn

    forcing_source_values = list(ForcingSource.objects.values('name', 'description', 'is_active'))
    observational_source_values = list(ObservationalSource.objects
                                       .values('name', 'description', 'is_active'))
    domain_values = list(Domain.objects
                         .values('name', 'description', 'is_active'))

    gages = list(Gage.objects.filter(is_active=True)
                 .values('gage_id', 'nws_id', 'nwm_v3_calibrated', 'domain__name'))
    [gage.update({'domain': gage.pop('domain__name')}) for gage in gages]

    ngen_cal_input.ready_to_run(run)

    response = {'calibration_run_id': run.id, 'status': run.status.name,
                'domain_values': domain_values,
                'forcing_source_values': forcing_source_values,
                'observational_source_values': observational_source_values,
                'gages': gages}
    response = {key: value for key, value in response.items() if value not in [None, '', [], {}]}

    serializer, error_response = validate_response(LoadGageResponseSerializer, response)
    if error_response:
        return error_response

    logger.debug(f'Returning to {request.user} from load_gage_tab() - {serializer.data}')

    return Response(serializer.data)


@extend_schema(
    request=GageIdSerializer,
    responses={
        200: GageSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: ErrorResponseSerializer
    },
    parameters=[
        OpenApiParameter(name='calibration_run_id', description='ID of the calibration run', required=True, type=int)
    ],
    description="Get details for a specific gage"
)
@api_view(['GET', 'POST'])
# @permission_classes([AllowAny])
@handle_exceptions
def get_gage(request):
    data = request.data if request.method == 'POST' else request.query_params

    logger.debug(f'get_gage() request from {request.user} - {data}')

    validator, error_return = validate_request(GageIdSerializer, data)
    if error_return:
        return error_return

    gage_id = validator.data.get('gage_id')

    gage = Gage.objects.filter(gage_id=gage_id).values('gage_id', 'agency', 'station_name', 'latitude', 'longitude', 'altitude').first()
    if not gage:
        return ResponseError("Gage '{}' does not exist".format(gage_id), http_status=status.HTTP_404_NOT_FOUND)

    response_validator, error_response = validate_response(GageSerializer, gage)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user} from get_gage() - {response_validator.data}')
    return Response(response_validator.data)


@extend_schema(
    request=SaveGageRequestSerializer,
    responses={
        200: SaveGageResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: ErrorResponseSerializer
    },
    description="Save gage tab data"
)
@api_view(['POST'])
@handle_exceptions
def save_gage_tab(request):
    data = request.data
    logger.debug(f'save_gage_tab() request from {request.user} - {data}')

    validator, error_return = validate_request(SaveGageRequestSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.data.get('calibration_run_id')
    gage_id = validator.data.get('gage_id')
    forcing_source_name = validator.data.get('forcing_source')
    observational_source_name = validator.data.get('observational_source')
    # TODO Sources should be foreign keys

    run, errorReturn = get_run(calibration_run_id, request.user)
    if errorReturn:
        return errorReturn

    geopackage_image_url = None
    if gage_id:
        gage = save_gage(run, gage_id)
        if not gage:
            return ResponseError("Gage '{}' does not exist".format(gage_id), http_status=status.HTTP_404_NOT_FOUND)

        try:
            get_geopackage_from_hydrofabric(gage_id)
        except ClientError as e:
            # TODO Check for other errors
            return Response(f'Error downloading geopackage from AWS.  Check your AWS credentials - {e}')

        geopackage_png = gpkg_to_png_selected_layers(get_geopackage_file(run))

        # Convert ByteIO image to base64
        base64_str = base64.b64encode(geopackage_png.getvalue()).decode('utf-8')
        geopackage_image_url = f'data:image/png;base64,{base64_str}'

        # Get forcing and observational data
        run.forcing_source = ForcingSource.objects.get(name=forcing_source_name) if forcing_source_name else None
        run.observational_source = ObservationalSource.objects.get(name=observational_source_name) if observational_source_name else None
        try:
            if observational_source_name and observational_source_name != ObservationalSourceEnum.UPLOAD.value:
                get_observational_data_from_hydrofabric(run)
        except ClientError as e:
            return Response(f'Error downloading observational data from AWS.  Check your AWS credentials - {e}')

        try:
            if forcing_source_name and forcing_source_name != ForcingSourceEnum.UPLOAD.value:
                get_forcing_data_from_hydrofabric(run)
        except ClientError as e:
            return Response(f'Error downloading forcing data from AWS.  Check your AWS credentials - {e}')

    with transaction.atomic():
        run.save()

    ngen_cal_input.ready_to_run(run)

    response = {'message': f'Calibration Run {run.id} updated', 'calibration_run_id': run.id, 'status': run.status.name,
                'geopackage_image': geopackage_image_url}

    response_validator, error_response = validate_response(SaveGageResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user} from save_gage_tab() - {response_validator.data}')
    return Response(response_validator.data)


def save_gage(run, gage_id):
    gage = Gage.objects.only('gage_id').filter(gage_id=gage_id).first()
    if gage:
        if run.gage != gage:

            if run.gage:
                # Delete any user uploaded files
                if run.forcing_user_dir:
                    shutil.rmtree(get_forcing_dir(run))
                run.forcing_user_dir = None

                if run.observational_file_path:
                    os.remove(get_observation_file(run))
                run.observational_user_filename = None

            run.gage = gage
    return gage


@extend_schema(
    request=UploadObservationalSerializer,
    responses={
        200: GenericResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: ErrorResponseSerializer
    },
    description="Allow user to upload observational data"
)
@api_view(['POST'])
# @permission_classes([AllowAny])
@handle_exceptions
def upload_observational_data(request):
    data = request.data
    logger.debug(f'upload_observational_data() request from {request.user} - {data}')

    validator, error_return = validate_request(UploadObservationalSerializer, data, context={'request': request})
    if error_return:
        return error_return

    calibration_run_id = validator.data.get('calibration_run_id')
    observational_user_filename = validator.data.get('observational_user_filename')

    run, errorReturn = get_run(calibration_run_id, request.user)
    if errorReturn:
        return errorReturn

    run.observational_source = ObservationalSource.objects.get(name=ObservationalSourceEnum.UPLOAD.value)

    # Need to upload to the run-specific observational directory, as opposed to the global directory
    observational_dir = get_observation_dir(run)
    fs = FileSystemStorage(location=observational_dir)

    # Make sure file doesn't exist
    files = request.FILES.getlist('observational_file')

    observational_file = files[0]
    run.observational_user_filename = observational_user_filename

    fs.save(observational_file.name, observational_file)

    # Invalidate the dates, since we'll have to compute the intersection again
    run.time_range_start = None
    run.time_range_end = None

    with transaction.atomic():
        run.save()

    ngen_cal_input.ready_to_run(run)

    response = {'message': f"Observational file '{observational_file.name}' saved for Calibration Run {run.id}", 'calibration_run_id': run.id,
                'status': run.status.name}

    response_validator, error_response = validate_response(GenericResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user} from upload_observational_data() - {response_validator.data}')
    return Response(response_validator.data)


@extend_schema(
    request=UploadForcingSerializer,
    responses={
        200: GenericResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: ErrorResponseSerializer
    },
    description="Allow user to upload observational data"
)
@api_view(['POST'])
@handle_exceptions
# @permission_classes([AllowAny])
def upload_forcing_data(request):
    data = request.data
    logger.debug(f'upload_forcing_data() request from {request.user} - {data}')

    validator, error_return = validate_request(UploadForcingSerializer, data, context={'request': request})
    if error_return:
        return error_return

    calibration_run_id = validator.data.get('calibration_run_id')
    forcing_user_dir = validator.data.get('forcing_user_dir')

    run, errorReturn = get_run(calibration_run_id, request.user)
    if errorReturn:
        return errorReturn

    run.forcing_source = ForcingSource.objects.get(name=ForcingSourceEnum.UPLOAD.value)

    # Validate the file keys and how many there are
    key = 'forcing_files'
    files = request.FILES.getlist(key)

    # Upload to the run-specific forcing directory
    run.forcing_user_dir = forcing_user_dir

    fs = FileSystemStorage(location=get_forcing_dir(run))

    # Note that this will replace files that already exist
    for forcing_file in files:
        fs.save(forcing_file.name, forcing_file)

    # Invalidate the dates, since we'll have to compute the intersection again
    run.time_range_start = None
    run.time_range_end = None

    with transaction.atomic():
        run.save()

    ngen_cal_input.ready_to_run(run)

    response_message = f"{len(files)} forcing file{'s' if len(files) > 1 else ''} saved for Calibration Run {run.id}"
    response = {'message': response_message, 'calibration_run_id': run.id, 'status': run.status.name}

    response_validator, error_response = validate_response(GenericResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user} from upload_forcing_data() - {response_validator.data}')
    return Response(response_validator.data)
