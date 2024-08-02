import base64
import json
import logging
import os
from json.decoder import JSONDecodeError

from django.core.files.storage import FileSystemStorage
from django.db import transaction
from django.http import JsonResponse
from rest_framework import serializers
from rest_framework import status
from rest_framework.decorators import api_view

from calibration.calibration_validators import SaveGageValidator, GageIdValidator, CalibrationRunValidator, GeopackageValidator, \
    UploadForcingValidator
from calibration.enums import ObservationalSourceEnum, ForcingSourceEnum
from calibration.models import Gage, ForcingSource, ObservationalSource, Domain
from views import ngen_cal_input
from views.aws_util import parse_s3_uri, download_s3
from views.common import get_run, JsonException, JsonError, JsonValidationError

geopackage_sample_data = {
    "uri": "s3://ngwpc-dev/Yuqiong.Liu/data/gauge_01073000.gpkg",
    "creation_date": "2024-07-30T12:33:00.001Z"
}

logger = logging.getLogger(__name__)


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

        validate = CalibrationRunValidator(data=data)
        validate.is_valid(raise_exception=True)

        calibration_run_id = validate.data.get('calibration_run_id')

        run, errorReturn = get_run(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn

        gage = {'gage_id': run.gage.id, 'agency': run.gage.agency, 'station_name': run.gage.station_name, 'latitude': run.gage.latitude,
                'longitude': run.gage.longitude, 'altitude': run.gage.altitude} if run.gage else {}

        forcing_source_values = list(ForcingSource.objects.only('name', 'description', 'is_active').values_list('name', 'description', 'is_active'))
        observational_source_values = list(
            ObservationalSource.objects.only('name', 'description', 'is_active').values_list('name', 'description', 'is_active'))
        domain_values = list(Domain.objects.only('name', 'description', 'is_active').values_list('name', 'description', 'is_active'))

        # Get all the gages so the user can select another
        gages = Gage.objects.filter(is_active=True).values_list('gage_id', flat=True)

        ngen_cal_input.ready_to_run(run)

        response = {'calibration_run_id': run.id, 'status': run.status.name, 'gage': gage,
                    'forcing_source': run.forcing_source, 'forcing_user_dir': run.forcing_user_dir,
                    'observational_source': run.observational_source, 'observational_user_filename': run.observational_user_filename,
                    'domain_values': domain_values, 'forcing_source_values': forcing_source_values,
                    'observational_source_values': observational_source_values,
                    'gages': list(gages)}
        logger.debug(f'Returning to {request.user} from load_gage_tab() - {response}')

        return JsonResponse(response, safe=False)
    except (serializers.ValidationError, JSONDecodeError) as v:
        return JsonValidationError(v)
    except Exception as e:
        return JsonException(e)


@api_view(['GET', 'POST'])
# @login_required()
def get_gage(request):
    try:
        if request.method == 'POST':
            data = json.loads(request.body or '{}')
        else:
            data = request.GET

        logger.debug(f'get_gage() request from {request.user} - {data}')

        validate = GageIdValidator(data=data)
        validate.is_valid(raise_exception=True)

        gage_id = validate.data.get('gage_id')

        gage = Gage.objects.filter(gage_id=gage_id).only('gage_id', 'agency', 'station_name').values(
            'gage_id', 'agency', 'station_name', 'latitude', 'longitude', 'altitude').first()
        if not gage:
            return JsonError("Gage '{}' does not exist".format(gage_id), status.HTTP_404_NOT_FOUND)
        logger.debug(f'Returning to {request.user} from get_gage() - {gage}')

        return JsonResponse(gage, safe=False)
    except (serializers.ValidationError, JSONDecodeError) as v:
        return JsonValidationError(v)
    except Exception as e:
        return JsonException(e)


def get_geopackage_from_hydrofabric(gage_id):
    # Get this from hydrofabric
    # modules_request = {"gage_id": gage_id
    # response = requests.post(settings.HYDROFABRIC_URL, json=modules_request)
    # module_data = response.json()
    geopackage_data = geopackage_sample_data

    validator = GeopackageValidator(data=geopackage_data)
    if not validator.is_valid():
        logger.debug(validator.errors)
        raise Exception('Geopackage data from Hydrofabric is not in the expected format')

    uri = geopackage_data['uri']
    bucket, key = parse_s3_uri(uri)
    save_as = '/home/peter.a.kronenberg/temp/my_gpkg.gpkg'
    download_s3(bucket, key, save_as)


    return save_as


@api_view(['POST'])
# @login_required
def save_gage_tab(request):
    try:
        print('user', request.user)

        body = json.loads(request.body or '{}')
        logger.debug(f'save_gage_tab() request from {request.user} - {body}')
        validate = SaveGageValidator(data=body)
        validate.is_valid(raise_exception=True)

        calibration_run_id = validate.data.get('calibration_run_id')
        gage_id = validate.data.get('gage_id')
        forcing_source = validate.data.get('forcing_source')
        observational_source = validate.data.get('observational_source')

        run, errorReturn = get_run(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn

        if gage_id:
            gage = Gage.objects.filter(gage_id=gage_id).first()
            if not gage:
                return JsonError("Gage '{}' does not exist".format(gage_id), status.HTTP_404_NOT_FOUND)
            else:
                run.gage = gage
                geopackage_path = get_geopackage_from_hydrofabric(gage_id)
                run.hydrofabric_gpkg_path = geopackage_path

                # geopackage_png = convert_to_png(geopackage_path)
                geopackage_png = geopackage_path

                # Convert to base64 so we can return to the front-end
                with open(geopackage_png, 'rb') as geopackage_data:
                    base64_str = base64.b64encode(geopackage_data.read()).decode('utf-8')
                # print('base64:', base64_str)
                extension = geopackage_path.split('.')[-1]
                dataurl = f'data:image/{extension};base64,{base64_str}'
                print('dataurl:', dataurl)

                # Assuming we return a ByteIO object
                # base64.b64encode(buffer.get.value()).decode('utf-8')


        run.forcing_source = forcing_source
        run.observational_source = observational_source

        with transaction.atomic():
            run.save()

        ngen_cal_input.ready_to_run(run)

        # TODO Need to return the actual geopackage file, not just the name
        response = {'message': f'Calibration Run {run.id} updated', 'calibration_run_key': run.id, 'status': run.status.name,
                    'geopackage_image': dataurl}
        logger.debug(f'Returning to {request.user} from save_gage_tab() - {response}')
        return JsonResponse(response)
    except (serializers.ValidationError, JSONDecodeError) as v:
        return JsonValidationError(v)
    except Exception as e:
        return JsonException(e)


@api_view(['POST'])
# @login_required
def upload_observational_data(request):
    try:
        print('user', request.user)

        body = request.POST
        logger.debug(f'upload_observational_data() request from {request.user} - {body}')
        validate = CalibrationRunValidator(data=body)
        validate.is_valid(raise_exception=True)

        calibration_run_id = validate.data.get('calibration_run_id')

        run, errorReturn = get_run(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn

        if run.observational_source != ObservationalSourceEnum.UPLOAD.value:
            return JsonError('Observational file upload only allowed if ObservationalSource is set to UPLOAD')

        if len(request.FILES) == 0:
            return JsonError('Observational data must be uploaded')

        keys = set(request.FILES.keys())
        key = 'observational_file'
        if key not in keys:
            return JsonValidationError(f"Missing expected key '{key}'")

        keys.remove(key)
        if len(keys) > 0:
            return JsonValidationError("unexpected keys - {keys}".format(keys=keys))

        observational_dir = '/home/peter.a.kronenberg/temp/obs'
        fs = FileSystemStorage(location=observational_dir)

        # Make sure file doesn't exist
        files = request.FILES.getlist(key)
        count = len(files)
        if count > 1:
            return JsonError("Only one observational file should be uploaded")

        observational_file = files[0]
        run.observational_file_path = os.path.join(observational_dir, observational_file.name)
        run.observational_user_filename = observational_file.name
        if fs.exists(observational_file.name):
            return JsonError(f"File {observational_file.name} already exists")

        fs.save(observational_file.name, observational_file)

        # Invalidate the dates, since we'll have to compute the intersection again
        run.time_range_start = None
        run.time_range_end = None

        with transaction.atomic():
            run.save()

        ngen_cal_input.ready_to_run(run)

        response = {'message': f"Observational file '{observational_file.name}' saved for Calibration Run {run.id}", 'calibration_run_key': run.id,
                    'status': run.status.name}

        logger.debug(f'Returning to {request.user} from upload_observational_data() - {response}')
        return JsonResponse(response)
    except (serializers.ValidationError, JSONDecodeError) as v:
        return JsonValidationError(v)
    except Exception as e:
        return JsonException(e)


@api_view(['POST'])
# @login_required
def upload_forcing_data(request):
    try:
        print('user', request.user)

        body = request.POST
        logger.debug(f'upload_forcing_data() request from {request.user} - {body}')
        validate = UploadForcingValidator(data=body)
        validate.is_valid(raise_exception=True)

        calibration_run_id = validate.data.get('calibration_run_id')
        forcing_user_dir = validate.data.get('forcing_user_dir')

        run, errorReturn = get_run(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn

        if run.forcing_source != ForcingSourceEnum.UPLOAD.value:
            return JsonError('Forcing files upload only allowed if ForcingSource is set to UPLOAD')

        # Validate the file keys and how many there are
        count = len(request.FILES)
        if count == 0:
            return JsonError('Forcing data must be uploaded')

        keys = set(request.FILES.keys())
        key = 'forcing_files'
        if key not in keys:
            return JsonValidationError(f"Missing expected key '{key}'")

        keys.remove(key)
        if len(keys) > 0:
            return JsonValidationError("unexpected keys - {keys}".format(keys=keys))

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
            return JsonError(errors)

        for forcing_file in files:
            fs.save(forcing_file.name, forcing_file)

        # Invalidate the dates, since we'll have to compute the intersection again
        run.time_range_start = None
        run.time_range_end = None

        with transaction.atomic():
            run.save()

        ngen_cal_input.ready_to_run(run)

        file_or_files = 'file' if count == 1 else 'files'
        response = {'message': f'{count} forcing {file_or_files} saved for Calibration Run {run.id}', 'calibration_run_key': run.id,
                    'status': run.status.name}

        logger.debug(f'Returning to {request.user} from upload_forcing_data() - {response}')
        return JsonResponse(response)
    except (serializers.ValidationError, JSONDecodeError) as v:
        return JsonValidationError(v)
    except Exception as e:
        return JsonException(e)
