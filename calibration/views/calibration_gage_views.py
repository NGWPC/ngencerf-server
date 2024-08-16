import base64
import logging
import os

from botocore.exceptions import ClientError
from django.core.files.storage import FileSystemStorage
from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema, PolymorphicProxySerializer
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.enums import ObservationalSourceEnum, ForcingSourceEnum
from calibration.models import Gage, ForcingSource, ObservationalSource, Domain
from calibration.util.aws_util import download_s3, download_all_s3
from calibration.util.calibration_validators import SaveGageRequestSerializer, GageIdSerializer, CalibrationRunSerializer, GeopackageSerializer, \
    UploadForcingSerializer, ObservationalHydrofabricSerializer, ForcingHydrofabricSerializer, SaveGageResponseSerializer, \
    LoadGageResponseSerializer, GageSerializer, GenericResponseSerializer, ErrorResponseSerializer, ExceptionResponseSerializer, \
    ValidationExceptionSerializer
from calibration.util.geopkg import gpkg_to_png_selected_layers
from calibration.util.ngen_locations import geopackage_dir, observation_dir, forcing_dir
from calibration.views import ngen_cal_input
from calibration.views.common import get_run, ResponseError, handle_exceptions
from calibration.views.ngen_cal_input import get_main_dir

geopackage_sample_data = {
    "uri": "s3://ngwpc-dev/Yuqiong.Liu/data/gauge_01073000.gpkg",
    "creation_date": "2024-07-30T12:33:00.001Z"
}

forcing_sample_data = {
    "uri": "s3://ngwpc-dev/Yuqiong.Liu/data/aorc_nwm/csv_basin_group1/Gage_01123000/"
}

observational_sample_data = {
    "uri": "s3://ngwpc-dev/Yuqiong.Liu/data/streamflow_obs/01123000_hourly_discharge.csv"
}

logger = logging.getLogger(__name__)


@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: LoadGageResponseSerializer,
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
    description="Load gage tab data"
)
@api_view(['GET', 'POST'])
# @permission_classes([AllowAny])
@handle_exceptions
def load_gage_tab(request):
    print('user', request.user)
    data = request.data if request.method == 'POST' else request.query_params

    logger.debug(f'load_gage_tab() request from {request.user} - {data}')

    validator = CalibrationRunSerializer(data=data)
    validator.is_valid(raise_exception=True)

    calibration_run_id = validator.data.get('calibration_run_id')

    run, errorReturn = get_run(calibration_run_id, request.user)
    if errorReturn:
        return errorReturn

    gage = {'gage_id': run.gage.id, 'agency': run.gage.agency, 'station_name': run.gage.station_name, 'latitude': run.gage.latitude,
            'longitude': run.gage.longitude, 'altitude': run.gage.altitude} if run.gage else {}

    forcing_source_values = list(ForcingSource.objects.values('name', 'description', 'is_active'))
    observational_source_values = list(ObservationalSource.objects
                                       .values('name', 'description', 'is_active'))
    domain_values = list(Domain.objects
                         .values('name', 'description', 'is_active'))

    gages = list(Gage.objects.filter(is_active=True)
                 .values('gage_id', 'nws_id', 'nwm_v3_calibrated', 'domain__name'))
    [gage.update({'domain': gage.pop('domain__name')}) for gage in gages]

    ngen_cal_input.ready_to_run(run)

    response = {'calibration_run_id': run.id, 'status': run.status.name, 'gage': gage,
                'forcing_source': run.forcing_source, 'forcing_user_dir': run.forcing_user_dir,
                'observational_source': run.observational_source, 'observational_user_filename': run.observational_user_filename,
                'domain_values': domain_values,
                'forcing_source_values': forcing_source_values,
                'observational_source_values': observational_source_values,
                'gages': gages}
    response = {key: value for key, value in response.items() if value not in [None, '', [], {}]}

    serializer = LoadGageResponseSerializer(data=response)
    if not serializer.is_valid():
        return ResponseError(f'Data format error returning from load_gage_tab() - {serializer.errors}',
                             httpStatus=status.HTTP_500_INTERNAL_SERVER_ERROR)
    logger.debug(f'Returning to {request.user} from load_gage_tab() - {serializer.data}')

    return Response(serializer.data)




@extend_schema(
    request=GageIdSerializer,
    responses={
        200: GageSerializer,
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
    description="Get details for a specific gage"
)
@api_view(['GET', 'POST'])
# @permission_classes([AllowAny])
@handle_exceptions
def get_gage(request):
    data = request.data if request.method == 'POST' else request.query_params

    logger.debug(f'get_gage() request from {request.user} - {data}')

    validator = GageIdSerializer(data=data)
    validator.is_valid(raise_exception=True)

    gage_id = validator.data.get('gage_id')

    gage = Gage.objects.filter(gage_id=gage_id).values('gage_id', 'agency', 'station_name', 'latitude', 'longitude', 'altitude').first()
    if not gage:
        return ResponseError("Gage '{}' does not exist".format(gage_id), status.HTTP_404_NOT_FOUND)
    serializer = GageSerializer(data=gage)
    if not serializer.is_valid():
        return ResponseError(f'Data format error returning from get_gage() - {serializer.errors}',
                             httpStatus=status.HTTP_500_INTERNAL_SERVER_ERROR)
    logger.debug(f'Returning to {request.user} from get_gage() - {serializer.data}')

    return Response(serializer.data)




def get_geopackage_from_hydrofabric(gage_id):
    # Get this from hydrofabric
    # modules_request = {"gage_id": gage_id
    # response = requests.post(settings.HYDROFABRIC_URL, json=modules_request)
    # module_data = response.json()
    geopackage_data = geopackage_sample_data

    validator = GeopackageSerializer(data=geopackage_data)
    if not validator.is_valid():
        logger.debug(validator.errors)
        raise Exception(f'Geopackage data from Hydrofabric is not in the expected format - {validator.errors}')

    uri = geopackage_data['uri']
    file_path = download_s3(uri, geopackage_dir)

    return file_path


def get_observational_data_from_hydrofabric(observation_source):
    print('Getting observational data from Hydrofabric')
    # Get this from hydrofabric
    # request = {"source": observational_source
    # response = requests.post(settings.HYDROFABRIC_URL, json=request)
    # response = response.json()
    response = observational_sample_data
    validator = ObservationalHydrofabricSerializer(data=response)
    if not validator.is_valid():
        logger.debug(validator.errors)
        raise Exception(f'Observational data from Hydrofabric is not in the expected format - {validator.errors}')

    s3_uri = validator.data.get('uri')

    # This is a path to a single file, which we just need to download
    # bucket, key = parse_s3_uri(s3_uri)
    # filename = key.split('/')[-1]
    download_s3(s3_uri, observation_dir)


def get_forcing_data_from_hydrofabric(forcing_source):
    print('Getting forcing data from Hydrofabric')
    # Get this from hydrofabric
    # request = {"source": forcing_source
    # response = requests.post(settings.HYDROFABRIC_URL, json=request)
    # response = response.json()
    response = forcing_sample_data
    validator = ForcingHydrofabricSerializer(data=response)
    if not validator.is_valid():
        logger.debug(validator.errors)
        raise Exception(f'Forcing data from Hydrofabric is not in the expected format - {validator.errors}')

    s3_uri = validator.data.get('uri')

    # This is a path to a directory, so we want to download all files
    # bucket, key = parse_s3_uri(s3_uri)
    # subdir = key.split('/')[-1]

    download_all_s3(s3_uri, forcing_dir)


@extend_schema(
    request=SaveGageRequestSerializer,
    responses={
        200: SaveGageResponseSerializer,
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
    description="Save gage tab data"
)
@api_view(['POST'])
# @permission_classes([AllowAny])
@handle_exceptions
def save_gage_tab(request):
    print('user', request.user)

    data = request.data
    logger.debug(f'save_gage_tab() request from {request.user} - {data}')
    validator = SaveGageRequestSerializer(data=data)
    validator.is_valid(raise_exception=True)

    calibration_run_id = validator.data.get('calibration_run_id')
    gage_id = validator.data.get('gage_id')
    forcing_source = validator.data.get('forcing_source')
    observational_source = validator.data.get('observational_source')

    run, errorReturn = get_run(calibration_run_id, request.user)
    if errorReturn:
        return errorReturn

    geopackage_image_url = None
    if gage_id:
        gage = save_gage(run, gage_id)
        if not gage:
            return ResponseError("Gage '{}' does not exist".format(gage_id), status.HTTP_404_NOT_FOUND)

        print('gage_id', gage_id)
        try:
            geopackage_path = save_geopackage_path(run, gage_id)
        except ClientError as e:
            # TODO Check for other errors
            return Response(f'Error downloading geopackage from AWS.  Check your credentials - {e}')

        geopackage_png = gpkg_to_png_selected_layers(geopackage_path)

        # Convert to base64 so we can return to the front-end
        # with open(geopackage_png, 'rb') as geopackage_data:
        #     base64_str = base64.b64encode(geopackage_data.read()).decode('utf-8')
        # extension = geopackage_path.split('.')[-1]
        # geopackage_image_url = f'data:image/{extension};base64,{base64_str}'

        # Convert ByteIO image to base64
        base64_str = base64.b64encode(geopackage_png.getvalue()).decode('utf-8')
        geopackage_image_url = f'data:image/png;base64,{base64_str}'

        # Get observational data
        run.forcing_source = forcing_source
        run.observational_source = observational_source
        try:
            if observational_source and observational_source != ObservationalSourceEnum.UPLOAD.value:
                run.observational_path = get_observational_data_from_hydrofabric(observational_source)

            if forcing_source and forcing_source != ForcingSourceEnum.UPLOAD.value:
                run.forcing_path = get_forcing_data_from_hydrofabric(forcing_source)
        except ClientError as e:
            return Response(f'Error downloading forcing or observational data from AWS.  Check your credentials - {e}')

    with transaction.atomic():
        run.save()

    ngen_cal_input.ready_to_run(run)

    response = {'message': f'Calibration Run {run.id} updated', 'calibration_run_id': run.id, 'status': run.status.name,
                'geopackage_image': geopackage_image_url}

    serializer = SaveGageResponseSerializer(data=response)
    if not serializer.is_valid():
        return ResponseError(f'Data format error returning from save_gage_tab() - {serializer.errors}',
                             httpStatus=status.HTTP_500_INTERNAL_SERVER_ERROR)
    logger.debug(f'Returning to {request.user} from save_gage_tab() - {serializer.data}')
    return Response(serializer.data)



# Function to be used for saving a config file to allow CLI
def save_gage(run, gage_id):
    gage = Gage.objects.filter(gage_id=gage_id).first()
    if gage:
        run.gage = gage
    return gage


def save_geopackage_path(run, gage_id):
    geopackage_path = get_geopackage_from_hydrofabric(gage_id)
    run.hydrofabric_gpkg_path = geopackage_path
    return geopackage_path


@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: GenericResponseSerializer,
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
    description="Allow user to upload observational data"
)
@api_view(['POST'])
# @permission_classes([AllowAny])
@handle_exceptions
def upload_observational_data(request):
    print('user', request.user)

    data = request.data
    logger.debug(f'upload_observational_data() request from {request.user} - {data}')
    validator = CalibrationRunSerializer(data=data)
    validator.is_valid(raise_exception=True)

    calibration_run_id = validator.data.get('calibration_run_id')

    run, errorReturn = get_run(calibration_run_id, request.user)
    if errorReturn:
        return errorReturn

    if run.observational_source != ObservationalSourceEnum.UPLOAD.value:
        return ResponseError('Observational file upload only allowed if ObservationalSource is set to UPLOAD')

    if len(request.FILES) == 0:
        return ResponseError('Observational data must be uploaded')

    keys = set(request.FILES.keys())
    key = 'observational_file'
    if key not in keys:
        return Response({'validation_error': f"Missing expected key '{key}'"}, status=status.HTTP_400_BAD_REQUEST)

    keys.remove(key)
    if len(keys) > 0:
        return Response({'validation_error': f"Unexpected keys {keys}".format(keys=keys)}, status=status.HTTP_400_BAD_REQUEST)

    # Need to upload to the run-specific observational directory, as opposed to the global directory
    main_dir = get_main_dir(run)
    observational_dir = os.path.join(main_dir, 'observation')
    fs = FileSystemStorage(location=observational_dir)

    # Make sure file doesn't exist
    files = request.FILES.getlist(key)
    count = len(files)
    if count > 1:
        return ResponseError("Only one observational file should be uploaded")

    observational_file = files[0]
    run.observational_file_path = os.path.join(observational_dir, observational_file.name)
    run.observational_user_filename = observational_file.name

    fs.save(observational_file.name, observational_file)

    # Invalidate the dates, since we'll have to compute the intersection again
    run.time_range_start = None
    run.time_range_end = None

    with transaction.atomic():
        run.save()

    ngen_cal_input.ready_to_run(run)

    response = {'message': f"Observational file '{observational_file.name}' saved for Calibration Run {run.id}", 'calibration_run_id': run.id,
                'status': run.status.name}

    serializer = GenericResponseSerializer(data=response)
    if not serializer.is_valid():
        return ResponseError(f'Data format error returning from upload_observational_data() - {serializer.errors}',
                             httpStatus=status.HTTP_500_INTERNAL_SERVER_ERROR)
    logger.debug(f'Returning to {request.user} from upload_observational_data() - {serializer.data}')
    return Response(serializer.data)




@extend_schema(
    request=UploadForcingSerializer,
    responses={
        200: GenericResponseSerializer,
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
    description="Allow user to upload observational data"
)
@api_view(['POST'])
@handle_exceptions
# @permission_classes([AllowAny])
def upload_forcing_data(request):
    print('user', request.user)

    data = request.data
    logger.debug(f'upload_forcing_data() request from {request.user} - {data}')
    validator = UploadForcingSerializer(data=data)
    validator.is_valid(raise_exception=True)

    calibration_run_id = validator.data.get('calibration_run_id')
    forcing_user_dir = validator.data.get('forcing_user_dir')

    run, errorReturn = get_run(calibration_run_id, request.user)
    if errorReturn:
        return errorReturn

    if run.forcing_source != ForcingSourceEnum.UPLOAD.value:
        return ResponseError('Forcing files upload only allowed if ForcingSource is set to UPLOAD')

    # Validate the file keys and how many there are
    if len(request.FILES) == 0:
        return ResponseError('Forcing data must be uploaded')

    keys = set(request.FILES.keys())
    key = 'forcing_files'
    if key not in keys:
        return Response({'validation_error': f"Missing expected key '{key}'"}, status=status.HTTP_400_BAD_REQUEST)

    keys.remove(key)
    if len(keys) > 0:
        return Response({'validation_error': f"Unexpected keys {keys}"}, status=status.HTTP_400_BAD_REQUEST)

    # Need to upload to the run-specific observational directory, as opposed to the global directory
    main_dir = get_main_dir(run)
    subdir = run.gage.gage_id
    run.forcing_dir_path = os.path.join(main_dir, 'forcing', subdir)
    run.forcing_user_dir = forcing_user_dir

    fs = FileSystemStorage(location=run.forcing_dir_path)

    # Note that this will replace files that already exist
    files = request.FILES.getlist(key)
    for forcing_file in files:
        fs.save(forcing_file.name, forcing_file)

    # Invalidate the dates, since we'll have to compute the intersection again
    run.time_range_start = None
    run.time_range_end = None

    with transaction.atomic():
        run.save()

    ngen_cal_input.ready_to_run(run)

    file_or_files = 'file' if len(files) == 1 else 'files'
    response = {'message': f'{len(files)} forcing {file_or_files} saved for Calibration Run {run.id}', 'calibration_run_id': run.id,
                'status': run.status.name}

    serializer = GenericResponseSerializer(data=response)
    if not serializer.is_valid():
        return ResponseError(f'Data format error returning from upload_forcing_data() - {serializer.errors}',
                             httpStatus=status.HTTP_500_INTERNAL_SERVER_ERROR)
    logger.debug(f'Returning to {request.user} from upload_forcing_data() - {serializer.data}')
    return Response(serializer.data)


