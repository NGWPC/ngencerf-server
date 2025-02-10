import json
import logging
import os
import re
import shutil

from django.core.files.storage import FileSystemStorage
from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema, OpenApiResponse
from pyogrio.errors import DataLayerError
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from calibration.enums import ObservationalSourceEnum, ForcingSourceEnum, DomainEnum, GeopackageSourceEnum, StatusEnum
from calibration.models import Gage, CalibrationRun, CalibrationFormulation
from calibration.util.caching import get_cached_gages, get_gage_by_id
from calibration.util.calibration_validators import SaveGageRequestSerializer, GageIdSerializer, CalibrationRunSerializer, UploadForcingSerializer, \
    SaveGageResponseSerializer, LoadGageResponseSerializer, GageSerializer, GenericResponseSerializer, ErrorResponseSerializer, \
    UploadObservationalSerializer, UploadGeopackageSerializer, UploadGeopackageResponseSerializer
from calibration.util.file_util import delete_all_files_in_directory, get_single_file
from calibration.util.geopkg import gpkg_to_png_selected_layers
from calibration.util.ngen_locations import get_forcing_dir_for_job, get_observational_file_for_job, \
    get_forcing_filename_pattern, get_observational_dir_for_job, get_geopackage_dir_for_job
from calibration.views import ngen_cal_input
from calibration.views.common import get_calibration_run, ResponseError, handle_exceptions, validate_response, validate_request, \
    png_str_to_base64_url, truncate_large_fields, get_valid_path
from calibration.views.data_services import get_geopackage_from_data_services, get_observational_data_from_data_services, \
    get_forcing_data_from_data_services, DataServicesException, get_module_metadata_from_data_services, clear_times

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
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    parameters=[
        OpenApiParameter(name='calibration_run_id', description='ID of the calibration run', required=True, type=int)
    ],
    description="Load gage tab data"
)
@api_view(['GET', 'POST'])
@handle_exceptions
def load_gage_tab(request: Request) -> Response:
    """
    Load gage tab data based on the calibration run.

    :param request: The HTTP request containing either POST data or query parameters.
    :return: A JSON response with gage data, available source options, and calibration run status.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()

    logger.debug(f'load_gage_tab() request from {request.user.email} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=list(StatusEnum))
    if error_return:
        return error_return

    # Retrieve active source and domain options
    forcing_source_values = ForcingSourceEnum.get_choices_with_fields(fields=['name', 'description'])
    observational_source_values = ObservationalSourceEnum.get_choices_with_fields(fields=['name', 'description'])
    geopackage_source_values = GeopackageSourceEnum.get_choices_with_fields(fields=['name', 'description'])
    domain_values = DomainEnum.get_choices_with_fields(fields=['name', 'description'])

    # Retrieve cached gages with necessary fields
    gages = [{
        'gage_id': gage.get('gage_id'),
        'nwm_v3_calibration': gage.get('nwm_v3_calibration'),
        'nws_id': gage.get('nws_id'),
        'domain': gage.get('domain')
    } for gage in get_cached_gages().values()]

    ngen_cal_input.ready_to_run(run)

    response = {'calibration_run_id': run.id,
                'status': run.status.name,
                'domain_values': domain_values,
                'forcing_source_values': forcing_source_values,
                'observational_source_values': observational_source_values,
                'geopackage_source_values': geopackage_source_values,
                'gages': gages}
    response = {key: value for key, value in response.items() if value not in [None, '', [], {}]}

    response_validator, error_response = validate_response(
        LoadGageResponseSerializer,
        response,
        fields_to_truncate=["gages", "geopackage_image_url"],
        max_length=50
    )
    if error_response:
        return error_response

    logger.debug(
        f'Returning to {request.user.email} from load_gage_tab() - '
        f'{json.dumps(truncate_large_fields(response_validator.data, fields_to_truncate=["gages", "geopackage_image_url"], max_length=50))}'
    )

    return Response(response_validator.data)


@extend_schema(
    request=GageIdSerializer,
    responses={
        200: GageSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    parameters=[
        OpenApiParameter(name='calibration_run_id', description='ID of the calibration run', required=True, type=int)
    ],
    description="Get details for a specific gage"
)
@api_view(['GET', 'POST'])
@handle_exceptions
def get_gage(request: Request) -> Response:
    """
    Retrieve details for a specific gage.

    :param request: The HTTP request containing either POST data or query parameters.
    :return: A JSON response with the details of the requested gage.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()

    logger.debug(f'get_gage() request from {request.user.email} - {data}')

    validator, error_return = validate_request(GageIdSerializer, data)
    if error_return:
        return error_return

    gage_id = validator.get('gage_id')
    gage = get_gage_by_id(gage_id)

    if not gage:
        return ResponseError(f"Gage '{gage_id}' does not exist", http_status=status.HTTP_404_NOT_FOUND)

    response_validator, error_response = validate_response(GageSerializer, gage)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user.email} from get_gage() - {json.dumps(response_validator.data)}')
    return Response(response_validator.data)


@extend_schema(
    request=SaveGageRequestSerializer,
    responses={
        200: SaveGageResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Save gage tab data"
)
@api_view(['POST'])
@handle_exceptions
def save_gage_tab(request: Request):
    """
    Save gage tab data and update the calibration run with new gage information.

    This function handles updating forcing, observational, and geopackage data sources, clearing previously
    uploaded files, and updating the calibration run status.

    :param request: The HTTP request containing POST data with gage and data source details.
    :return: A JSON response confirming the update and including any errors from data services.
    """
    data = request.data
    logger.debug(f'save_gage_tab() request from {request.user.email} - {data}')

    validator, error_return = validate_request(SaveGageRequestSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    gage_id = validator.get('gage_id')
    forcing_source_name = validator.get('forcing_source')
    observational_source_name = validator.get('observational_source')
    geopackage_source_name = validator.get('geopackage_source')

    run, error_return = get_calibration_run(calibration_run_id, request.user)
    if error_return:
        return error_return

    eds_errors = []

    geopackage_image_url = None
    if gage_id:
        try:
            eds_errors_entry = save_gage(run, gage_id)
            if eds_errors_entry:
                eds_errors.append(eds_errors_entry)
        except Gage.DoesNotExist:
            return ResponseError(f"Gage '{gage_id}' does not exist", http_status=status.HTTP_404_NOT_FOUND)

        # Process GeoPackage source and delete user-uploaded file if necessary
        if geopackage_source_name and geopackage_source_name != GeopackageSourceEnum.UPLOAD.value:
            # See if there's a user-uploaded file and delete it
            user_uploaded_geopackage_file = get_single_file(get_geopackage_dir_for_job(run))
            if user_uploaded_geopackage_file and os.path.exists(user_uploaded_geopackage_file):
                os.remove(user_uploaded_geopackage_file)
            if not run.geopackage_eds_file_path:
                try:
                    get_geopackage_from_data_services(run)
                except DataServicesException as e:
                    logger.exception("Error retrieving geopackage data from Data Services")
                    eds_errors.append({
                        'name': 'geopackage',
                        'message': str(e),
                        'status_code': e.status_code if e.status_code else None
                    })
        else:
            run.geopackage_eds_file_path = None

        run.geopackage_source = GeopackageSourceEnum.get_instance(geopackage_source_name) if geopackage_source_name else None

        geopackage_image_url = get_geopackage_image_url(run)

        # Process observational source and delete user-uploaded file if necessary
        if observational_source_name and observational_source_name != ObservationalSourceEnum.UPLOAD.value:
            # See if there's a user-uploaded file and delete it
            user_uploaded_observational_file = get_single_file(get_observational_dir_for_job(run))
            if user_uploaded_observational_file and os.path.exists(user_uploaded_observational_file):
                os.remove(user_uploaded_observational_file)
            if not run.observational_eds_file_path:
                try:
                    get_observational_data_from_data_services(run)
                except DataServicesException as e:
                    logger.exception("Error retrieving observational data from Data Services")
                    eds_errors.append({
                        'name': 'observational',
                        'message': str(e),
                        'status_code': e.status_code if e.status_code else None
                    })
        else:
            run.observational_eds_file_path = None

        run.observational_source = ObservationalSourceEnum.get_instance(observational_source_name) if observational_source_name else None

        # Process forcing source and delete user-uploaded files if necessary
        if forcing_source_name and forcing_source_name != ForcingSourceEnum.UPLOAD.value:
            # Delete any user-upload, if there
            user_uploaded_forcing_dir = get_forcing_dir_for_job(run)
            if user_uploaded_forcing_dir and os.path.exists(user_uploaded_forcing_dir):
                shutil.rmtree(user_uploaded_forcing_dir)
            if not run.forcing_eds_dir_path:
                try:
                    get_forcing_data_from_data_services(run)
                except DataServicesException as e:
                    logger.exception("Error retrieving forcing data from Data Services")
                    eds_errors.append({
                        'name': 'forcing',
                        'message': str(e),
                        'status_code': e.status_code if e.status_code else None
                    })
        else:
            run.forcing_eds_dir_path = None

        run.forcing_source = ForcingSourceEnum.get_instance(forcing_source_name) if forcing_source_name else None

    with transaction.atomic():
        run.save()

    ngen_cal_input.ready_to_run(run)

    response = {'message': f'Calibration Job {run.id} updated', 'calibration_run_id': run.id, 'status': run.status.name,
                'geopackage_image_url': geopackage_image_url}
    if eds_errors:
        response['eds_errors'] = eds_errors

    response_validator, error_response = validate_response(SaveGageResponseSerializer, response, fields_to_truncate=['geopackage_image_url'])
    if error_response:
        return error_response
    logger.debug(
        f'Returning to {request.user.email} from save_gage_tab() - '
        f'{json.dumps(truncate_large_fields(response_validator.data, fields_to_truncate=["geopackage_image_url"]))}'
    )

    return Response(response_validator.data)


def get_geopackage_image_url(run: CalibrationRun) -> str | None:
    """
    Convert a GeoPackage file to a PNG image URL if available.

    :param run: The calibration run instance containing the GeoPackage file information.
    :return: A base64 URL string of the PNG image if conversion is successful; otherwise, None.
    """
    geopackage_path = get_valid_path(run.geopackage_source, run.geopackage_eds_file_path,
                                     GeopackageSourceEnum.UPLOAD,
                                     lambda: get_single_file(get_geopackage_dir_for_job(run)))

    if geopackage_path and os.path.exists(geopackage_path):
        try:
            # Attempt to convert the GeoPackage to PNG for selected layers
            geopackage_png = gpkg_to_png_selected_layers(geopackage_path)
            return png_str_to_base64_url(geopackage_png.getvalue())
        except DataLayerError as e:
            # Log the error and return None if the layer could not be opened
            logger.exception(f"DataLayerError - {e} - while processing geopackage: {geopackage_path}")
            return None
        except Exception as e:
            # Handle any other exceptions
            logger.exception(f"An unexpected error occurred: {e} - while processing geopackage: {geopackage_path}")
            return None
    else:
        return None


def save_gage(run: CalibrationRun, gage_id: int) -> dict | None:
    """
    Update the calibration run with a new gage and remove any previously uploaded files.

    If the gage for the calibration run changes, this function clears any existing user-uploaded or EDS files and
    updates initial parameter values via data services.

    :param run: The calibration run instance to update.
    :param gage_id: The ID of the new gage.
    :return: A dictionary with error details if an error occurs; otherwise, None.
    :raises: Gage.DoesNotExist if the specified gage does not exist.
    """
    gage = Gage.objects.only('gage_id').get(gage_id=gage_id)

    # Only update if the gage has changed
    if run.gage != gage:
        if run.gage:
            # Delete any user-uploaded or EDS files associated with the previous gage
            # delete_all_files_in_directory(get_geopackage_dir_for_job(run))
            if os.path.exists(get_geopackage_dir_for_job(run)):
                logger.info(f"Deleting geopackage file in {get_geopackage_dir_for_job(run)}")
                shutil.rmtree(get_geopackage_dir_for_job(run))
            run.geopackage_eds_file_path = None

            uploaded_forcing_dir = get_forcing_dir_for_job(run)
            if os.path.exists(uploaded_forcing_dir):
                logger.info(f"Deleting all forcing files in {uploaded_forcing_dir}")
                shutil.rmtree(uploaded_forcing_dir)
            run.forcing_eds_dir_path = None

            uploaded_observational_file = get_observational_file_for_job(run)
            if os.path.exists(uploaded_observational_file):
                logger.info(f"Deleting observational file in {uploaded_observational_file}")
                os.remove(uploaded_observational_file)
            run.observational_eds_file_path = None

            clear_times(run)

        run.gage = gage

        # Update initial parameter values if formulations exist
        my_formulations = CalibrationFormulation.objects.filter(calibration_run=run)
        if my_formulations.exists():
            try:
                get_module_metadata_from_data_services(run, my_formulations, gage_changed=True)
            except DataServicesException as e:
                logger.exception("Error retrieving module parameter data from Data Services")
                return {
                    'name': 'parameters',
                    'message': str(e),
                    'status_code': e.status_code if e.status_code else None
                }


@extend_schema(
    request=UploadObservationalSerializer,
    responses={
        200: GenericResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Allow user to upload observational data"
)
@api_view(['POST'])
@handle_exceptions
def upload_observational_data(request: Request) -> Response:
    """
    Upload observational data for a calibration run.

    This function handles the upload of an observational file by saving it to the run-specific directory and updating the calibration run.

    :param request: The HTTP request containing the observational file data.
    :return: A JSON response confirming the upload or reporting errors.
    """
    data = request.data
    logger.debug(f'upload_observational_data() request from {request.user.email} - {data}')
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    cli = user_agent.startswith('curl')

    validator, error_return = validate_request(UploadObservationalSerializer, data, context={'request': request})
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_calibration_run(calibration_run_id, request.user)
    if error_return:
        return error_return

    run.observational_source = ObservationalSourceEnum.UPLOAD.db_instance

    # Save to the run-specific observational directory
    fs = FileSystemStorage(location=get_observational_dir_for_job(run))

    files = request.FILES.getlist('observational_file')

    user_observational_file = files[0]

    run.observational_eds_file_path = None

    # Delete the file if it's already there
    delete_all_files_in_directory(fs.location)
    logger.info(f"Saving user-uploaded observational file to {os.path.join(fs.location, user_observational_file.name)}")
    fs.save(user_observational_file.name, user_observational_file)

    clear_times(run, cli)

    with transaction.atomic():
        run.save()

    ngen_cal_input.ready_to_run(run)

    response = {'message': f"Observational file '{user_observational_file.name}' saved for Calibration Job {run.id}", 'calibration_run_id': run.id,
                'status': run.status.name}

    response_validator, error_response = validate_response(GenericResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user.email} from upload_observational_data() - {json.dumps(response_validator.data)}')
    return Response(response_validator.data)


@extend_schema(
    request=UploadForcingSerializer,
    responses={
        200: GenericResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Allow user to upload forcing data"
)
@api_view(['POST'])
@handle_exceptions
def upload_forcing_data(request: Request) -> Response:
    """
    Upload forcing data files for a calibration run.

    This function validates forcing file naming conventions, saves valid forcing files to the run-specific directory,
    and updates the calibration run.

    :param request: The HTTP request containing forcing file data.
    :return: A JSON response indicating the number of forcing files saved or reporting errors.
    """
    data = request.data
    logger.debug(f'upload_forcing_data() request from {request.user.email} - {data}')
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    cli = user_agent.startswith('curl')

    validator, error_return = validate_request(UploadForcingSerializer, data, context={'request': request})
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_calibration_run(calibration_run_id, request.user)
    if error_return:
        return error_return

    run.forcing_source = ForcingSourceEnum.UPLOAD.db_instance

    # Validate the file keys and how many there are
    key = 'forcing_files'
    files = request.FILES.getlist(key)

    run.forcing_eds_dir_path = None

    # Save to the run-specific forcing directory
    fs = FileSystemStorage(location=get_forcing_dir_for_job(run))

    # Delete existing files in directory
    delete_all_files_in_directory(fs.location)
    number_of_files = 0

    # Save each file if it meets naming conventions
    for forcing_file in files:
        if re.match(get_forcing_filename_pattern(), forcing_file.name):
            logger.info(f"Saving user-uploaded forcing file to {os.path.join(fs.location, forcing_file.name)}")
            fs.save(forcing_file.name, forcing_file)
            number_of_files += 1
        else:
            logger.warning(f'Skipping forcing file {forcing_file.name} - does not match naming convention')

    clear_times(run, cli)

    if number_of_files == 0:
        return ResponseError(f'No valid forcing files found')

    with transaction.atomic():
        run.save()

    ngen_cal_input.ready_to_run(run)

    response_message = f"{number_of_files} forcing file{'s' if len(files) > 1 else ''} saved for Calibration Job {run.id}"
    response = {'message': response_message, 'calibration_run_id': run.id, 'status': run.status.name}

    response_validator, error_response = validate_response(GenericResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user.email} from upload_forcing_data() - {json.dumps(response_validator.data)}')
    return Response(response_validator.data)


@extend_schema(
    request=UploadGeopackageSerializer,
    responses={
        200: GenericResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Allow user to upload geopackage data"
)
@api_view(['POST'])
@handle_exceptions
def upload_geopackage_data(request: Request) -> Response:
    """
    Upload a geopackage file for a calibration run.

    This function handles the geopackage file upload by saving it to the run-specific directory.
    If requested, it converts the geopackage to a PNG image and updates the calibration run.

    :param request: The HTTP request containing geopackage file data.
    :return: A JSON response confirming the upload and including the geopackage image URL if available.
    """
    data = request.data
    logger.debug(f'upload_geopackage_data() request from {request.user.email} - {data}')

    validator, error_return = validate_request(UploadGeopackageSerializer, data, context={'request': request})
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    return_geopackage_url = validator.get('return_geopackage_url')  # default=True

    run, error_return = get_calibration_run(calibration_run_id, request.user)
    if error_return:
        return error_return

    run.geopackage_source = GeopackageSourceEnum.UPLOAD.db_instance

    # Save to the run-specific geopackage directory
    fs = FileSystemStorage(location=get_geopackage_dir_for_job(run))

    files = request.FILES.getlist('geopackage_file')

    user_geopackage_file = files[0]

    run.geopackage_eds_file_path = None

    # Delete the file if it's already there
    delete_all_files_in_directory(fs.location)
    logger.info(f"Saving user-uploaded geopackage file to {os.path.join(fs.location, user_geopackage_file.name)}")
    fs.save(user_geopackage_file.name, user_geopackage_file)

    geopackage_image_url = get_geopackage_image_url(run) if return_geopackage_url else None

    with transaction.atomic():
        run.save()

    ngen_cal_input.ready_to_run(run)

    response = {
        'message': f"Geopackage file '{user_geopackage_file.name}' saved for Calibration Job {run.id}",
        'calibration_run_id': run.id,
        'status': run.status.name
    }
    if geopackage_image_url:
        response['geopackage_image_url'] = geopackage_image_url

    response_validator, error_response = validate_response(
        UploadGeopackageResponseSerializer,
        response,
        fields_to_truncate=['geopackage_image_url']
    )
    if error_response:
        return error_response
    logger.debug(
        f'Returning to {request.user.email} from upload_geopackage_data() - '
        f'{json.dumps(truncate_large_fields(response_validator.data, fields_to_truncate=["geopackage_image_url"]))}'
    )
    return Response(response_validator.data)


def get_data_files_status(run: CalibrationRun) -> dict:
    """
    Check the status of data files for a calibration run.

    This function verifies whether observational, forcing, and geopackage files are available for the given calibration run.

    :param run: The calibration run instance to check.
    :return: A dictionary with boolean values indicating the presence of observational, forcing, and geopackage files.
    """
    observation_path = get_valid_path(run.observational_source, run.observational_eds_file_path,
                                      ObservationalSourceEnum.UPLOAD,
                                      lambda: get_observational_file_for_job(run))

    forcing_path = get_valid_path(run.forcing_source, run.forcing_eds_dir_path,
                                  ForcingSourceEnum.UPLOAD,
                                  lambda: get_forcing_dir_for_job(run))

    geopackage_path = get_valid_path(run.geopackage_source, run.geopackage_eds_file_path,
                                     GeopackageSourceEnum.UPLOAD,
                                     lambda: get_single_file(get_geopackage_dir_for_job(run)))

    return {'observational': bool(observation_path),
            'forcing': bool(forcing_path),
            'geopackage': bool(geopackage_path)}
