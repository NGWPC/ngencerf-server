import logging
import os
import re
import shutil
import traceback
from pathlib import Path

import requests.exceptions
from django.core.cache import cache
from django.core.files.storage import FileSystemStorage
from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.enums import ObservationalSourceEnum, ForcingSourceEnum, DomainEnum, GeopackageSourceEnum
from calibration.models import Gage, CalibrationRun
from calibration.util.calibration_validators import SaveGageRequestSerializer, GageIdSerializer, CalibrationRunSerializer, UploadForcingSerializer, \
    SaveGageResponseSerializer, \
    LoadGageResponseSerializer, GageSerializer, GenericResponseSerializer, ErrorResponseSerializer, \
    UploadObservationalSerializer, UploadGeopackageSerializer, UploadGeopackageResponseSerializer
from calibration.util.file_util import delete_all_files_in_directory
from calibration.util.geopkg import gpkg_to_png_selected_layers
from calibration.util.ngen_locations import get_forcing_dir_for_job, get_observational_file_for_job, \
    get_geopackage_file_for_job, get_forcing_filename_pattern, get_observational_dir_for_job, get_geopackage_dir_for_job
from calibration.views import ngen_cal_input
from calibration.views.common import get_run, ResponseError, handle_exceptions, validate_response, validate_request, png_str_to_base64_url, \
    truncate_large_fields, get_valid_path
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
    data = request.data if request.method == 'POST' else request.query_params.dict()

    logger.debug(f'load_gage_tab() request from {request.user} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_run(calibration_run_id, request.user)
    if error_return:
        return error_return

    # Use cached enum values for forcing and observational source
    forcing_source_values = ForcingSourceEnum.active_choices_with_fields(fields=['name', 'description'])
    observational_source_values = ObservationalSourceEnum.active_choices_with_fields(fields=['name', 'description'])
    geopackage_source_values = GeopackageSourceEnum.active_choices_with_fields(fields=['name', 'description'])

    domain_values = DomainEnum.active_choices_with_fields(fields=['name', 'description'])

    # Check if gages data is cached
    gages = cache.get('cached_gages')
    if gages is None:
        # If not cached, query the database and cache the result
        gages = list(Gage.objects.filter(is_active=True)
                     .values('gage_id', 'nws_id', 'nwm_v3_calibrated', 'domain__name'))
        [gage.update({'domain': gage.pop('domain__name')}) for gage in gages]

        # Cache the gages data indefinitely (timeout=None)
        cache.set('cached_gages', gages, timeout=None)

    ngen_cal_input.ready_to_run(run)

    response = {'calibration_run_id': run.id, 'status': run.status.name,
                'domain_values': domain_values,
                'forcing_source_values': forcing_source_values,
                'observational_source_values': observational_source_values,
                'geopackage_source_values': geopackage_source_values,
                'gages': gages}
    response = {key: value for key, value in response.items() if value not in [None, '', [], {}]}

    response_validator, error_response = validate_response(LoadGageResponseSerializer, response, fields_to_truncate=["gages"])
    if error_response:
        return error_response

    logger.debug(f'Returning to {request.user} from load_gage_tab() - {truncate_large_fields(response_validator.data, fields_to_truncate=["gages"])}')

    return Response(response_validator.data)


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
    data = request.data if request.method == 'POST' else request.query_params.dict()

    logger.debug(f'get_gage() request from {request.user} - {data}')

    validator, error_return = validate_request(GageIdSerializer, data)
    if error_return:
        return error_return

    gage_id = validator.get('gage_id')

    # Try to get the gage from the cache
    gage = cache.get(f'cached_gage_{gage_id}')
    if gage is None:
        try:
            # If not cached, query the database and cache the result
            gage = Gage.objects.values('gage_id', 'agency', 'station_name', 'latitude', 'longitude', 'altitude').get(gage_id=gage_id)

            cache.set(f'cached_gage_{gage_id}', gage, timeout=None)
        except Gage.DoesNotExist:
            return ResponseError(f"Gage '{gage_id}' does not exist", http_status=status.HTTP_404_NOT_FOUND)

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
    """
     Some notes about forcing/obs paths (relevant here and in import/export and ngen_cal_input)

     run.forcing_hydrofabric_dir_path, observational_hydrofabric_file_path and run.geopackage_hydrofabric_file_path are *only* used when getting the data from hydrofabric.

     User-uploaded files are stored in the job-specific paths and for both observational and forcing data, these are the paths that are always passed to ngen-cal.
     For geopackage file, if the data is from Hydrofabric, we pass the Hydrofabric path.  If the user uplaods a file, then we use the job-specific path.

     The job-specific path is deterministic and can be derived at the time we create input.config.  Therefore, they are not stored in the run object.
     They can be obtained by get_forcing_dir_for_job(), get_observational_dir_for_job() or get_geopackage_dir_for_job().

     For Forcing and Observational data, if the files are obtained from Hydrofabric, the job specific path remains empty,
     until we build the config, at which point the Hydrofabric data is subsetted by time-range and the resulting files placed in the job-specific paths.

     Summary: For Forcing and Observational data, the job-specific paths are always the paths that are passed to ngen-cal.
     They can contain either the unchanged user-uploaded data or subsetted Hyrofabric data.
     For Geopackage, we pass either the Hydrofabric path or the user-uploaded path.
    """
    data = request.data
    logger.debug(f'save_gage_tab() request from {request.user} - {data}')

    validator, error_return = validate_request(SaveGageRequestSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    gage_id = validator.get('gage_id')
    forcing_source_name = validator.get('forcing_source')
    observational_source_name = validator.get('observational_source')
    geopackage_source_name = validator.get('geopackage_source')

    run, error_return = get_run(calibration_run_id, request.user)
    if error_return:
        return error_return

    hydrofabric_errors = []

    geopackage_image_url = None
    if gage_id:
        try:
            save_gage(run, gage_id)
        except Gage.DoesNotExist:
            return ResponseError(f"Gage '{gage_id}' does not exist", http_status=status.HTTP_404_NOT_FOUND)

        if geopackage_source_name and geopackage_source_name != GeopackageSourceEnum.UPLOAD.value:
            # Delete any user-upload, if there
            geopackage_file = get_geopackage_file_for_job(run)
            # Delete if it's already there
            if Path(geopackage_file).exists():
                Path(geopackage_file).unlink()
            try:
                get_geopackage_from_hydrofabric(run)
            except requests.exceptions.HTTPError:
                traceback.print_exc()
                hydrofabric_errors.append('geopackage')
        else:
            run.geopackage_hydrofabric_file_path = None

        run.geopackage_source = GeopackageSourceEnum.get_instance(geopackage_source_name) if geopackage_source_name else None

        geopackage_image_url = get_geopackage_image_url(run)

        # Get forcing and observational data
        if observational_source_name and observational_source_name != ObservationalSourceEnum.UPLOAD.value:
            # Delete any user-upload, if there
            observational_file = get_observational_file_for_job(run)
            if Path(observational_file).exists():
                Path(observational_file).unlink()
            try:
                get_observational_data_from_hydrofabric(run)
            except requests.exceptions.HTTPError:
                traceback.print_exc()
                hydrofabric_errors.append('observational')
        else:
            run.observational_hydrofabric_file_path = None

        run.observational_source = ObservationalSourceEnum.get_instance(observational_source_name) if observational_source_name else None

        if forcing_source_name and forcing_source_name != ForcingSourceEnum.UPLOAD.value:
            # Delete any user-upload, if there
            forcing_dir = get_forcing_dir_for_job(run)
            if Path(forcing_dir).exists():
                shutil.rmtree(forcing_dir)
            try:
                get_forcing_data_from_hydrofabric(run)
            except requests.exceptions.HTTPError:
                traceback.print_exc()
                hydrofabric_errors.append('forcing')
        else:
            run.forcing_hydrofabric_dir_path = None

        run.forcing_source = ForcingSourceEnum.get_instance(forcing_source_name) if forcing_source_name else None

    with transaction.atomic():
        run.save()

    ngen_cal_input.ready_to_run(run)

    response = {'message': f'Calibration Run {run.id} updated', 'calibration_run_id': run.id, 'status': run.status.name,
                'geopackage_image_url': geopackage_image_url}

    response_validator, error_response = validate_response(SaveGageResponseSerializer, response, fields_to_truncate=['geopackage_image_url'])
    if error_response:
        return error_response
    logger.debug(
        f'Returning to {request.user} from load_gage_tab() - {truncate_large_fields(response_validator.data, fields_to_truncate=["geopackage_image_url"])}')

    return Response(response_validator.data)


def get_geopackage_image_url(run: CalibrationRun):
    geopackage_path = get_valid_path(run.geopackage_source, run.geopackage_hydrofabric_file_path,
                                     GeopackageSourceEnum.UPLOAD,
                                     lambda: get_geopackage_file_for_job(run))

    if geopackage_path and Path(geopackage_path).exists():
        geopackage_png = gpkg_to_png_selected_layers(geopackage_path)

        return png_str_to_base64_url(geopackage_png.getvalue())
    else:
        return None


def save_gage(run, gage_id):
    gage = Gage.objects.only('gage_id').get(gage_id=gage_id)

    if run.gage != gage:
        if run.gage:
            # Delete any user uploaded files

            uploaded_geopackage_file = get_geopackage_file_for_job(run)
            if Path(uploaded_geopackage_file).exists():
                Path(uploaded_geopackage_file).unlink()

            uploaded_forcing_dir = get_forcing_dir_for_job(run)
            if Path(uploaded_forcing_dir).exists():
                shutil.rmtree(uploaded_forcing_dir)

            uploaded_observational_file = get_observational_file_for_job(run)
            if Path(uploaded_observational_file).exists():
                Path(uploaded_observational_file).unlink()

        # Update the run.gage field
        run.gage = gage


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

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_run(calibration_run_id, request.user)
    if error_return:
        return error_return

    # if not run.gage:
    #     return ResponseError(f'Calibration Run {run.id} does not yet have a gage specified')

    run.observational_source = ObservationalSourceEnum.from_enum(ObservationalSourceEnum.UPLOAD)

    # Save to the run-specific observational directory
    fs = FileSystemStorage(location=get_observational_dir_for_job(run))

    files = request.FILES.getlist('observational_file')

    user_observational_file = files[0]

    run.observational_hydrofabric_file_path = None

    # Delete the file if it's already there
    delete_all_files_in_directory(fs.location)
    logger.info(f"Saving user-uploaded observational file to {os.path.join(fs.location, user_observational_file.name)}")
    # TODO Need to rename it later
    fs.save(user_observational_file.name, user_observational_file)

    # Invalidate the dates, since we'll have to compute the intersection again
    run.time_range_start = None
    run.time_range_end = None

    with transaction.atomic():
        run.save()

    ngen_cal_input.ready_to_run(run)

    response = {'message': f"Observational file '{user_observational_file.name}' saved for Calibration Run {run.id}", 'calibration_run_id': run.id,
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

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_run(calibration_run_id, request.user)
    if error_return:
        return error_return

    # if not run.gage:
    #     return ResponseError(f'Calibration Run {run.id} does not yet have a gage specified')

    run.forcing_source = ForcingSourceEnum.from_enum(ForcingSourceEnum.UPLOAD)

    # Validate the file keys and how many there are
    key = 'forcing_files'
    files = request.FILES.getlist(key)

    run.forcing_hydrofabric_dir_path = None

    # Save to the run-specific forcing directory
    fs = FileSystemStorage(location=get_forcing_dir_for_job(run))

    number_of_files = len(files)

    delete_all_files_in_directory(fs.location)

    for forcing_file in files:
        if not re.match(get_forcing_filename_pattern(), forcing_file.name):
            logger.warning(f'Skipping forcing file {forcing_file.name} - does not match naming convention')
            number_of_files -= 1

        logger.info(f"Saving user-uploaded forcing file to {os.path.join(fs.location, forcing_file.name)}")
        fs.save(forcing_file.name, forcing_file)

    # Invalidate the dates, since we'll have to compute the intersection again
    run.time_range_start = None
    run.time_range_end = None

    if number_of_files == 0:
        return ResponseError(f'No valid forcing files found')

    with transaction.atomic():
        run.save()

    ngen_cal_input.ready_to_run(run)

    response_message = f"{number_of_files} forcing file{'s' if len(files) > 1 else ''} saved for Calibration Run {run.id}"
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

    calibration_run_id = validator.get('calibration_run_id')
    return_geopackage_url = validator.get('return_geopackage_url')  # default=True

    run, error_return = get_run(calibration_run_id, request.user)
    if error_return:
        return error_return

    run.geopackage_source = GeopackageSourceEnum.from_enum(GeopackageSourceEnum.UPLOAD)

    # Save to the run-specific geopackage directory
    fs = FileSystemStorage(location=get_geopackage_dir_for_job(run))

    files = request.FILES.getlist('geopackage_file')

    user_geopackage_file = files[0]

    run.geopackage_hydrofabric_file_path = None

    # Delete the file if it's already there
    delete_all_files_in_directory(fs.location)
    logger.info(f"Saving user-uploaded geopackage file to {os.path.join(fs.location, user_geopackage_file.name)}")
    fs.save(user_geopackage_file.name, user_geopackage_file)

    geopackage_image_url = get_geopackage_image_url(run) if return_geopackage_url else None

    with transaction.atomic():
        run.save()

    ngen_cal_input.ready_to_run(run)

    response = {'message': f"Geopackage file '{user_geopackage_file.name}' saved for Calibration Run {run.id}", 'calibration_run_id': run.id,
                'status': run.status.name}
    if geopackage_image_url:
        response['geopackage_image_url'] = geopackage_image_url
    print("response", response)

    response_validator, error_response = validate_response(UploadGeopackageResponseSerializer, response, fields_to_truncate=['geopackage_image_url'])
    if error_response:
        return error_response
    logger.debug(
        f'Returning to {request.user} from upload_geopackage_data() - {truncate_large_fields(response_validator.data, fields_to_truncate=["geopackage_image_url"])}')
    return Response(response_validator.data)
