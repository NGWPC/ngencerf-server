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
from calibration.models import Gage, ForcingSource, ObservationalSource, Domain, CalibrationRun
from calibration.util import ngen_locations
from calibration.util.calibration_validators import SaveGageRequestSerializer, GageIdSerializer, CalibrationRunSerializer, UploadForcingSerializer, \
    SaveGageResponseSerializer, \
    LoadGageResponseSerializer, GageSerializer, GenericResponseSerializer, ErrorResponseSerializer, \
    UploadObservationalSerializer, UploadGeopackageSerializer, UploadGeopackageResponseSerializer
from calibration.util.geopkg import gpkg_to_png_selected_layers
from calibration.util.ngen_locations import get_observational_dir_for_job, get_forcing_dir_for_job, get_observational_file_for_job, \
    get_geopackage_dir_for_job
from calibration.views import ngen_cal_input
from calibration.views.common import get_run, ResponseError, handle_exceptions, validate_request, validate_response, CerfException
from calibration.views.hydrofabric import get_forcing_data_from_hydrofabric, get_observational_data_from_hydrofabric, get_geopackage_from_hydrofabric
from cerfServer import settings

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

    run, errorReturn = get_run(calibration_run_id, request.user)
    if errorReturn:
        return errorReturn

    geopackage_image_url = None
    if gage_id:
        gage = save_gage(run, gage_id)
        if not gage:
            return ResponseError("Gage '{}' does not exist".format(gage_id), http_status=status.HTTP_404_NOT_FOUND)

        # We don't even want fake data
        if not settings.HYDROFABRIC:
            try:
                get_geopackage_from_hydrofabric(run)
            except ClientError as e:
                # TODO Check for other errors
                return Response(f'Error downloading geopackage from AWS.  Check your AWS credentials - {e}')

        geopackage_image_url = get_geopackage_image_url(run)

        """
        Some notes about forcing/obs paths (relevant here and in import/export and ngen_cal_input)
        
        run.forcing_hydrofabric_dir_path and observational_hydrofabric_file_path are *only* used when getting the data from hydrofabric.
        These paths are also not really used for anything, except as a reference for the unsubsetted data
        
        The actual paths that are eventually put in the input.config are not stored in the calibration_run object.
        This path is deterministic and can be derived at the time we create input.config.  They are referred to use the job-specific paths.
        It is obtained by ngen_locations.get_forcing_dir() and ngen_locations_get_observational_dir()
        Files that are uploaded by the user are immediately saved in the job-specific path.  If the files are obtained from Hydrofabric,
        the job specific path remains empty, until we build the config, at which point the Hydrofabric data is subsetted by time-range and the 
        resulting files placed in the job-specific paths.
        
        run.geopackage_hydrofabric_path is the path of the geopackage file from Hydrofabric.  
        This field is always used, since the geopackage files can't be uploaded.
        """
        # Get forcing and observational data
        if observational_source_name and observational_source_name != ObservationalSourceEnum.UPLOAD.value:
            # Delete any user-upload, if there
            observational_file = ngen_locations.get_observational_file_for_job(run)
            if os.path.exists(observational_file):
                os.remove(observational_file)
            get_observational_data_from_hydrofabric(run)
        run.observational_source = ObservationalSourceEnum.from_enum(ObservationalSourceEnum(observational_source_name)) if observational_source_name else None

        if forcing_source_name and forcing_source_name != ForcingSourceEnum.UPLOAD.value:
            # Delete any user-upload, if there
            forcing_dir = ngen_locations.get_forcing_dir_for_job(run)
            if os.path.exists(forcing_dir):
                shutil.rmtree(forcing_dir)
            get_forcing_data_from_hydrofabric(run)
        run.forcing_source = ForcingSourceEnum.from_enum(ForcingSourceEnum(forcing_source_name)) if forcing_source_name else None

    with transaction.atomic():
        run.save()

    ngen_cal_input.ready_to_run(run)

    response = {'message': f'Calibration Run {run.id} updated', 'calibration_run_id': run.id, 'status': run.status.name,
                'geopackage_image_url': geopackage_image_url}

    response_validator, error_response = validate_response(SaveGageResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user} from save_gage_tab() - {response_validator.data}')
    return Response(response_validator.data)


def get_geopackage_image_url(run: CalibrationRun):
    if run.geopackage_hydrofabric_path:
        if os.path.exists(run.geopackage_hydrofabric_path):
            geopackage_png = gpkg_to_png_selected_layers(run.geopackage_hydrofabric_path)

            # Convert ByteIO image to base64
            base64_str = base64.b64encode(geopackage_png.getvalue()).decode('utf-8')
            return f'data:image/png;base64,{base64_str}'
        else:
            raise CerfException(f'Cannot find geopackage file at {run.geopackage_hydrofabric_path}')
    else:
        return None


def save_gage(run, gage_id):
    gage = Gage.objects.only('gage_id').filter(gage_id=gage_id).first()
    if gage:
        if run.gage != gage:

            if run.gage:
                # Delete any user uploaded files
                uploaded_forcing_dir = get_forcing_dir_for_job(run)
                if os.path.exists(uploaded_forcing_dir):
                    shutil.rmtree(uploaded_forcing_dir)

                uploaded_observational_file = get_observational_file_for_job(run)
                if os.path.exists(uploaded_observational_file):
                    os.remove(uploaded_observational_file)

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

    run, errorReturn = get_run(calibration_run_id, request.user)
    if errorReturn:
        return errorReturn

    run.observational_source = ObservationalSourceEnum.from_enum(ObservationalSourceEnum.UPLOAD)

    # Save to the run-specific observational directory
    fs = FileSystemStorage(location=get_observational_dir_for_job(run))

    files = request.FILES.getlist('observational_file')

    observational_file = files[0]
    run.observational_hydrofabric_file_path = None

    if fs.exists(observational_file.name):
        os.remove(os.path.join(fs.location, observational_file.name))
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

    run, errorReturn = get_run(calibration_run_id, request.user)
    if errorReturn:
        return errorReturn

    run.forcing_source = ForcingSourceEnum.from_enum(ForcingSourceEnum.UPLOAD)

    # Validate the file keys and how many there are
    key = 'forcing_files'
    files = request.FILES.getlist(key)

    run.forcing_hydrofabric_dir_path = None

    # Save to the run-specific forcing directory
    fs = FileSystemStorage(location=get_forcing_dir_for_job(run))

    for forcing_file in files:
        if fs.exists(forcing_file.name):
            os.remove(os.path.join(fs.location, forcing_file.name))
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


@extend_schema(
    request=UploadGeopackageSerializer,
    responses={
        200: GenericResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: ErrorResponseSerializer
    },
    description="Allow user to upload geopackage data"
)
@api_view(['POST'])
# @permission_classes([AllowAny])
@handle_exceptions
def upload_geopackage_data(request):
    data = request.data
    logger.debug(f'upload_geopackage_data() request from {request.user} - {data}')

    validator, error_return = validate_request(UploadGeopackageSerializer, data, context={'request': request})
    if error_return:
        return error_return

    calibration_run_id = validator.data.get('calibration_run_id')

    run, errorReturn = get_run(calibration_run_id, request.user)
    if errorReturn:
        return errorReturn

    # Save to the run-specific geopackage directory
    fs = FileSystemStorage(location=get_geopackage_dir_for_job(run))

    files = request.FILES.getlist('geopackage_file')

    geopackage_file = files[0]
    run.geopackage_hydrofabric_path = None

    geopackage_hydrofabric_path = os.path.join(fs.location, geopackage_file.name)
    if fs.exists(geopackage_file.name):
        os.remove(geopackage_hydrofabric_path)
    fs.save(geopackage_file.name, geopackage_file)

    run.geopackage_hydrofabric_path = geopackage_hydrofabric_path

    geopackage_image_url = get_geopackage_image_url(run)

    with transaction.atomic():
        run.save()

    ngen_cal_input.ready_to_run(run)

    # TODO Need to return geopackage_png
    response = {'message': f"Geopackage file '{geopackage_file.name}' saved for Calibration Run {run.id}", 'calibration_run_id': run.id,
                'status': run.status.name, 'geopackage_image_url': geopackage_image_url}

    response_validator, error_response = validate_response(UploadGeopackageResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user} from upload_geopackage_data() - {response_validator.data}')
    return Response(response_validator.data)
