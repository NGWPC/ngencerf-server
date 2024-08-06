import base64
import json
import logging
import os
from json.decoder import JSONDecodeError

from django.core.files.storage import FileSystemStorage
from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.enums import ObservationalSourceEnum, ForcingSourceEnum
from calibration.models import Gage, ForcingSource, ObservationalSource, Domain
from calibration.util.aws_util import download_s3, download_all_s3
from calibration.util.calibration_validators import SaveGageRequestValidator, GageIdValidator, CalibrationRunValidator, GeopackageValidator, \
    UploadForcingValidator, ObservationalHydrofabricValidator, ForcingHydrofabricValidator, DomainValidator, SaveGageResponseSerializer, \
    LoadGageResponseSerializer, GageValidator, GenericResponseSerializer
from calibration.views import ngen_cal_input
from calibration.views.common import get_run, ResponseError

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
    request=CalibrationRunValidator,
    responses={
        200: LoadGageResponseSerializer
    },
    parameters=[
        OpenApiParameter(name='calibration_run_id', description='ID of the calibration run', required=True, type=int)
    ],
    description="Load gage tab data"
)
@api_view(['GET', 'POST'])
# @login_required
def load_gage_tab(request):
    try:
        print('user', request.user)
        if request.method == 'POST':
            data = json.loads(request.body or '{}')
        else:
            data = request.GET

        logger.debug(f'load_gage_tab() request from {request.user} - {data}')

        validator = CalibrationRunValidator(data=data)
        validator.is_valid(raise_exception=True)

        calibration_run_id = validator.data.get('calibration_run_id')

        run, errorReturn = get_run(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn

        gage = {'gage_id': run.gage.id, 'agency': run.gage.agency, 'station_name': run.gage.station_name, 'latitude': run.gage.latitude,
                'longitude': run.gage.longitude, 'altitude': run.gage.altitude} if run.gage else {}

        forcing_source_values = list(ForcingSource.objects.only('name', 'description', 'is_active').values('name', 'description', 'is_active'))
        observational_source_values = list(
            ObservationalSource.objects.only('name', 'description', 'is_active').values('name', 'description', 'is_active'))
        domain_values = list(Domain.objects.only('name', 'description', 'is_active').values('name', 'description', 'is_active'))

        # Get all the gages so the user can select another
        gages = list(Gage.objects.filter(is_active=True).only('gage_id', 'nws_id').values('gage_id', 'nws_id'))
        gage_dict = {gage['gage_id']: gage['nws_id'] for gage in gages}

        ngen_cal_input.ready_to_run(run)

        response = {'calibration_run_id': run.id, 'status': run.status.name, 'gage': gage,
                    'forcing_source': run.forcing_source, 'forcing_user_dir': run.forcing_user_dir,
                    'observational_source': run.observational_source, 'observational_user_filename': run.observational_user_filename,
                    'domain_values': domain_values,
                    'forcing_source_values': forcing_source_values,
                    'observational_source_values': observational_source_values,
                    'gages': gage_dict}
        serializer = LoadGageResponseSerializer(response)
        logger.debug(f'Returning to {request.user} from load_gage_tab() - {serializer.data}')

        return Response(serializer.data)
    except JSONDecodeError as e:
        logger.exception(e)
        return Response({'validation_error': 'JSON parsing error - ' + str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except serializers.ValidationError as e:
        logger.exception(e)
        return Response({'validation_error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception(e)
        return Response({'exception': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# TODO Not sure we need this endpoint
@api_view(['GET', 'POST'])
def get_gages(request):
    try:
        if request.method == 'POST':
            data = json.loads(request.body or '{}')
        else:
            data = request.GET

        logger.debug(f'get_gages() request from {request.user} - {data}')

        validator = DomainValidator(data=data)
        validator.is_valid(raise_exception=True)

        domain = validator.data.get('domain')

        gages = Gage.objects.filter(domain__name=domain).only('gage_id').values('gage_id').first()

        response = {'domain': domain, 'gages': gages}
        logger.debug(f'Returning to {request.user} from get_gages() - {response}')

        return Response(response)
    except JSONDecodeError as e:
        logger.exception(e)
        return Response({'validation_error': 'JSON parsing error - ' + str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except serializers.ValidationError as e:
        logger.exception(e)
        return Response({'validation_error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception(e)
        return Response({'exception': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    request=GageIdValidator,
    responses={
        200: GageValidator
    },
    parameters=[
        OpenApiParameter(name='calibration_run_id', description='ID of the calibration run', required=True, type=int)
    ],
    description="Get details for a specific gage"
)
@api_view(['GET', 'POST'])
# @login_required()
def get_gage(request):
    try:
        if request.method == 'POST':
            data = json.loads(request.body or '{}')
        else:
            data = request.GET

        logger.debug(f'get_gage() request from {request.user} - {data}')

        validator = GageIdValidator(data=data)
        validator.is_valid(raise_exception=True)

        gage_id = validator.data.get('gage_id')

        gage = Gage.objects.filter(gage_id=gage_id).only('gage_id', 'agency', 'station_name').values(
            'gage_id', 'agency', 'station_name', 'latitude', 'longitude', 'altitude').first()
        if not gage:
            return ResponseError("Gage '{}' does not exist".format(gage_id), status.HTTP_404_NOT_FOUND)
        serializer = GageValidator(gage)
        logger.debug(f'Returning to {request.user} from get_gage() - {serializer.data}')

        return Response(serializer.data)
    except JSONDecodeError as e:
        logger.exception(e)
        return Response({'validation_error': 'JSON parsing error - ' + str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except serializers.ValidationError as e:
        logger.exception(e)
        return Response({'validation_error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception(e)
        return Response({'exception': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def get_geopackage_from_hydrofabric(gage_id):
    # Get this from hydrofabric
    # modules_request = {"gage_id": gage_id
    # response = requests.post(settings.HYDROFABRIC_URL, json=modules_request)
    # module_data = response.json()
    geopackage_data = geopackage_sample_data

    validator = GeopackageValidator(data=geopackage_data)
    if not validator.is_valid():
        logger.debug(validator.errors)
        raise Exception(f'Geopackage data from Hydrofabric is not in the expected format - {validator.errors}')

    uri = geopackage_data['uri']
    save_dir = '/home/peter.a.kronenberg/temp/'
    file_path = download_s3(uri, save_dir)

    return file_path


def get_observational_data_from_hydrofabric(observation_source):
    print('Getting observational data from Hydrofabric')
    # Get this from hydrofabric
    # request = {"source": observational_source
    # response = requests.post(settings.HYDROFABRIC_URL, json=request)
    # response = response.json()
    response = observational_sample_data
    validator = ObservationalHydrofabricValidator(data=response)
    if not validator.is_valid():
        logger.debug(validator.errors)
        raise Exception(f'Observational data from Hydrofabric is not in the expected format - {validator.errors}')

    s3_uri = validator.data.get('uri')

    # This is a path to a single file, which we just need to download
    # bucket, key = parse_s3_uri(s3_uri)
    # filename = key.split('/')[-1]
    save_dir = f'/home/peter.a.kronenberg/temp/'
    download_s3(s3_uri, save_dir)


def get_forcing_data_from_hydrofabric(forcing_source):
    print('Getting forcing data from Hydrofabric')
    # Get this from hydrofabric
    # request = {"source": forcing_source
    # response = requests.post(settings.HYDROFABRIC_URL, json=request)
    # response = response.json()
    response = forcing_sample_data
    validator = ForcingHydrofabricValidator(data=response)
    if not validator.is_valid():
        logger.debug(validator.errors)
        raise Exception(f'Forcing data from Hydrofabric is not in the expected format - {validator.errors}')

    s3_uri = validator.data.get('uri')

    # This is a path to a directory, so we want to download all files
    # bucket, key = parse_s3_uri(s3_uri)
    # subdir = key.split('/')[-1]

    save_dir = f'/home/peter.a.kronenberg/temp/'
    download_all_s3(s3_uri, save_dir)


@extend_schema(
    request=SaveGageRequestValidator,
    responses={
        200: SaveGageResponseSerializer
    },
    description="Save gage tab data"
)
@api_view(['POST'])
# @login_required
def save_gage_tab(request):
    try:
        print('user', request.user)

        body = json.loads(request.body or '{}')
        logger.debug(f'save_gage_tab() request from {request.user} - {body}')
        validator = SaveGageRequestValidator(data=body)
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
            gage = Gage.objects.filter(gage_id=gage_id).first()
            if not gage:
                return ResponseError("Gage '{}' does not exist".format(gage_id), status.HTTP_404_NOT_FOUND)
            else:
                run.gage = gage
                geopackage_path = get_geopackage_from_hydrofabric(gage_id)
                run.hydrofabric_gpkg_path = geopackage_path

                # geopackage_png = convert_to_png(geopackage_path)
                geopackage_png = geopackage_path

                # Convert to base64 so we can return to the front-end
                with open(geopackage_png, 'rb') as geopackage_data:
                    base64_str = base64.b64encode(geopackage_data.read()).decode('utf-8')
                extension = geopackage_path.split('.')[-1]
                geopackage_image_url = f'data:image/{extension};base64,{base64_str}'

                # Assuming we return a ByteIO object
                # base64.b64encode(buffer.get.value()).decode('utf-8')

                # Get observational data
                run.forcing_source = forcing_source
                run.observational_source = observational_source
                if observational_source and observational_source != ObservationalSourceEnum.UPLOAD.value:
                    run.observational_path = get_observational_data_from_hydrofabric(observational_source)

                if forcing_source and forcing_source != ForcingSourceEnum.UPLOAD.value:
                    run.forcing_path = get_forcing_data_from_hydrofabric(forcing_source)

        with transaction.atomic():
            run.save()

        ngen_cal_input.ready_to_run(run)

        # TODO Need to return the actual geopackage file, not just the name
        response = {'message': f'Calibration Run {run.id} updated', 'calibration_run_id': run.id, 'status': run.status.name,
                    'geopackage_image': geopackage_image_url}

        serializer = SaveGageResponseSerializer(response)
        logger.debug(f'Returning to {request.user} from save_gage_tab() - {serializer.data}')
        return Response(serializer.data)
    except JSONDecodeError as e:
        logger.exception(e)
        return Response({'validation_error': 'JSON parsing error - ' + str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except serializers.ValidationError as e:
        logger.exception(e)
        return Response({'validation_error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception(e)
        return Response({'exception': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    request=CalibrationRunValidator,
    responses={
        200: GenericResponseSerializer
    },
    description="Allow user to upload observational data"
)
@api_view(['POST'])
# @login_required
def upload_observational_data(request):
    try:
        print('user', request.user)

        body = request.POST
        logger.debug(f'upload_observational_data() request from {request.user} - {body}')
        validator = CalibrationRunValidator(data=body)
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

        observational_dir = '/home/peter.a.kronenberg/temp/obs'
        fs = FileSystemStorage(location=observational_dir)

        # Make sure file doesn't exist
        files = request.FILES.getlist(key)
        count = len(files)
        if count > 1:
            return ResponseError("Only one observational file should be uploaded")

        observational_file = files[0]
        run.observational_file_path = os.path.join(observational_dir, observational_file.name)
        run.observational_user_filename = observational_file.name
        if fs.exists(observational_file.name):
            return ResponseError(f"File {observational_file.name} already exists")

        fs.save(observational_file.name, observational_file)

        # Invalidate the dates, since we'll have to compute the intersection again
        run.time_range_start = None
        run.time_range_end = None

        with transaction.atomic():
            run.save()

        ngen_cal_input.ready_to_run(run)

        response = {'message': f"Observational file '{observational_file.name}' saved for Calibration Run {run.id}", 'calibration_run_id': run.id,
                    'status': run.status.name}

        serializer = GenericResponseSerializer(response)
        logger.debug(f'Returning to {request.user} from upload_observational_data() - {serializer.data}')
        return Response(serializer.data)
    except JSONDecodeError as e:
        logger.exception(e)
        return Response({'validation_error': 'JSON parsing error - ' + str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except serializers.ValidationError as e:
        logger.exception(e)
        return Response({'validation_error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception(e)
        return Response({'exception': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    request=UploadForcingValidator,
    responses={
        200: GenericResponseSerializer
    },
    description="Allow user to upload observational data"
)
@api_view(['POST'])
# @login_required
def upload_forcing_data(request):
    try:
        print('user', request.user)

        body = request.POST
        logger.debug(f'upload_forcing_data() request from {request.user} - {body}')
        validator = UploadForcingValidator(data=body)
        validator.is_valid(raise_exception=True)

        calibration_run_id = validator.data.get('calibration_run_id')
        forcing_user_dir = validator.data.get('forcing_user_dir')

        run, errorReturn = get_run(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn

        if run.forcing_source != ForcingSourceEnum.UPLOAD.value:
            return ResponseError('Forcing files upload only allowed if ForcingSource is set to UPLOAD')

        # Validate the file keys and how many there are
        count = len(request.FILES)
        if count == 0:
            return ResponseError('Forcing data must be uploaded')

        keys = set(request.FILES.keys())
        key = 'forcing_files'
        if key not in keys:
            return Response({'validation_error': f"Missing expected key '{key}'"}, status=status.HTTP_400_BAD_REQUEST)

        keys.remove(key)
        if len(keys) > 0:
            return Response({'validation_error': f"Unexpected keys {keys}".format(keys=keys)}, status=status.HTTP_400_BAD_REQUEST)

        # TODO Need to generate a subdirectory based on the gage name
        subdir = 'gage_id'
        run.forcing_dir_path = os.path.join('/home/peter.a.kronenberg/temp/forcing', subdir)
        run.forcing_user_dir = forcing_user_dir

        fs = FileSystemStorage(location=run.forcing_dir_path)
        errors = []

        # Make sure they don't exist
        files = request.FILES.getlist(key)
        count = len(files)
        for forcing_file in files:
            print('forcing file', forcing_file)

            if fs.exists(forcing_file.name):
                errors.append(f"File {forcing_file.name} already exists")

        if errors:
            return ResponseError(errors)

        for forcing_file in files:
            fs.save(forcing_file.name, forcing_file)

        # Invalidate the dates, since we'll have to compute the intersection again
        run.time_range_start = None
        run.time_range_end = None

        with transaction.atomic():
            run.save()

        ngen_cal_input.ready_to_run(run)

        file_or_files = 'file' if count == 1 else 'files'
        response = {'message': f'{count} forcing {file_or_files} saved for Calibration Run {run.id}', 'calibration_run_id': run.id,
                    'status': run.status.name}

        serializer = GenericResponseSerializer(response)
        logger.debug(f'Returning to {request.user} from upload_forcing_data() - {serializer.data}')
        return Response(serializer.data)
    except JSONDecodeError as e:
        logger.exception(e)
        return Response({'validation_error': 'JSON parsing error - ' + str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except serializers.ValidationError as e:
        logger.exception(e)
        return Response({'validation_error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception(e)
        return Response({'exception': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
