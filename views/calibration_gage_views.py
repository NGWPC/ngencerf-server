import json
import logging
import os
from json.decoder import JSONDecodeError

from django.core.files.storage import FileSystemStorage
from django.db import transaction
from django.http import JsonResponse
from django.middleware.csrf import get_token
from rest_framework import serializers
from rest_framework import status
from rest_framework.decorators import api_view

from calibration.calibration_validators import SaveGageValidator, GageIdValidator, CalibrationRunValidator, GeopackageValidator
from calibration.enums import ObservationalSourceEnum, ForcingSourceEnum
from calibration.models import Gage, ForcingSource, ObservationalSource, Domain
from views import ngen_cal_input
from views.common import get_run, JsonException, JsonError, JsonValidationError

geopackage_sample_data = {
    "uri": "file://example.com/foo",
    "creation_date": "2024-07-30T12:33:00.001Z"
}

logger = logging.getLogger(__name__)


# Probably don't need this
@api_view(['GET'])
def csrf(request):
    return JsonResponse({'csrf': get_token(request)})


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
                    'forcing_source': run.forcing_source, 'forcing_user_filename': run.forcing_user_dir,
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

    # TODO Need to move this file to the local file system first
    return geopackage_data['uri']


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
        forcing_user_filename = validate.data.get('forcing_user_filename')
        observational_source = validate.data.get('observational_source')
        observational_user_filename = validate.data.get('observational_user_filename')

        run, errorReturn = get_run(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn

        if gage_id:
            gage = Gage.objects.filter(gage_id=gage_id).first()
            if not gage:
                return JsonError("Gage '{}' does not exist".format(gage_id), status.HTTP_404_NOT_FOUND)
            else:
                run.gage = gage
                geopackage = get_geopackage_from_hydrofabric(gage_id)
                run.hydrofabric_gpkg_path = geopackage

        run.forcing_source = forcing_source
        run.forcing_user_dir = forcing_user_filename
        run.observational_source = observational_source
        run.observational_user_filename = observational_user_filename
        # TODO Need to fill in forcing_path and observational_path with our location

        with transaction.atomic():
            run.save()

        ngen_cal_input.ready_to_run(run)

        # TODO Need to return the actual geopackage file, not just the name
        response = {'message': f'Calibration Run {run.id} updated', 'calibration_run_key': run.id, 'status': run.status.name,
                    'geopackage': geopackage}
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
        # validate = SaveGageValidator(data=body)
        # validate.is_valid(raise_exception=True)

        calibration_run_id = body['calibration_run_id']
        # calibration_run_id = validate.data.get('calibration_run_id')

        run, errorReturn = get_run(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn

        if run.observational_source != ObservationalSourceEnum.UPLOAD.value:
            return JsonError('Observational file upload only allowed if ObservationalSource is set to UPLOAD')

        if request.FILES.keys == 0:
            return JsonError('Observational data must be uploaded')

        if request.FILES.keys > 1:
            return JsonError("Only one observational observational_file should be uploaded")

        observational_dir = '/home/peter.a.kronenberg/temp/obs'
        fs = FileSystemStorage(location=run.observational_dir)

        observational_file = request.FILES[request.POST.keys()[0]]
        run.observational_file_path = os.path.join(observational_dir, observational_file)
        run.observational_user_filename = observational_file.name
        if fs.exists(observational_file.name):
            return JsonError(f"File {observational_file.name} already exists")

        fs.save(observational_file.name, observational_file)

        with transaction.atomic():
            run.save()

        ngen_cal_input.ready_to_run(run)

        response = {'message': f'Observational file {observational_file.name} saved for Calibration Run {run.id}', 'calibration_run_key': run.id,
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
        # validate = SaveGageValidator(data=body)
        # validate.is_valid(raise_exception=True)

        calibration_run_id = body['calibration_run_id']
        forcing_user_dir = body['forcing_user_dir']
        # calibration_run_id = validate.data.get('calibration_run_id')

        run, errorReturn = get_run(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn

        if run.forcing_source != ForcingSourceEnum.UPLOAD.value:
            return JsonError('Forcing files uploads only allowed if ForcingSource is set to UPLOAD')

        if request.FILES.keys == 0:
            return JsonError('Forcing data must be uploaded')

        run.forcing_dir_path = '/home/peter.a.kronenberg/temp/forcing'
        run.forcing_user_dir = forcing_user_dir
        fs = FileSystemStorage(location=run.forcing_dir_path)
        errors = []
        for file in request.FILES.keys():
            # Check if any of them exist
            forcing_file = request.FILES[request.POST.keys()[file]]

            if fs.exists(forcing_file.name):
                errors.append(f"File {forcing_file.name} already exists")
        if errors:
            return JsonError(errors)

        for file in request.FILES.keys():
            fs.save(file.name, file)

        with transaction.atomic():
            run.save()

        ngen_cal_input.ready_to_run(run)

        response = {'message': f'Forcing files saved for Calibration Run {run.id}', 'calibration_run_key': run.id,
                    'status': run.status.name}

        logger.debug(f'Returning to {request.user} from upload_forcing_data() - {response}')
        return JsonResponse(response)
    except (serializers.ValidationError, JSONDecodeError) as v:
        return JsonValidationError(v)
    except Exception as e:
        return JsonException(e)
