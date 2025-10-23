import json
import logging
import os
import shutil

import yaml
from django.conf import settings
from django.core.cache import cache
from django.core.files.storage import FileSystemStorage
from django.db import transaction, router
from django.db.models.deletion import Collector
from drf_spectacular.utils import OpenApiParameter, extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from calibration.enums import StatusEnum
from calibration.enums_vanilla import JobType
from calibration.models import VerificationRun
from calibration.run_util.run_common import submit_job
from calibration.util.calibration_validators import ErrorResponseSerializer, EmptySerializer, \
    VerificationJobsResponseSerializer, VerificationJobSerializer, CreateVerificationJobRequestSerializer, \
    CreateVerificationJobResponseSerializer, UploadVerificationYamlFileRequestSerializer, UploadVerificationYamlFileResponseSerializer, \
    RunVerificationJob, SubmitVerificationJobResponseSerializer, \
    GetVerificationStatusRequestSerializer, GetVerificationStatusResponseSerializer, \
    GetVerificationPlotNamesResponseSerializer, GetVerificationPlotRequestSerializer, GetVerificationPlotResponseSerializer, \
    DeleteVerificationJobResponseSerializer, ForecastRunSerializer
from calibration.util.file_util import delete_all_files_in_directory
from calibration.views.calibration_run_views import get_performance_metrics, should_include_metrics, parse_failure_messages, resolve_job_data_dir
from calibration.views.called_from import get_caller_name
from calibration.views.common import handle_exceptions, validate_response, validate_request, \
    get_forecast_run, get_verification_run, ResponseError, get_user_email, get_elapsed_str, \
    create_verification_job_internal, png_to_base64_url, truncate_large_fields, get_job_description
from calibration.views.verification_input import create_verification_input

logger = logging.getLogger(__name__)


@extend_schema(
    request=EmptySerializer,
    responses={
        200: VerificationJobsResponseSerializer,
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
        OpenApiParameter(name='verification_job_id', description='ID of the verification run', required=True, type=int)
    ],
    description="Load verification job data"
)
@api_view(['GET', 'POST'])
@handle_exceptions
def load_verification_job(request: Request) -> Response:
    """
    Load data for a verification job.

    - Calls create_verification_input(verification_job) to generate the config

    :param request: HTTP request containing verification_job_id
    :return: JSON response with forecast cycle values.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {data}')

    validator, error_return = validate_request(VerificationJobSerializer, data)
    if error_return:
        return error_return

    verification_job_id = validator.get('verification_job_id')

    verification_job, error_return = get_verification_run(verification_job_id, request.user, run_status=list(StatusEnum))
    if error_return:
        return error_return

    # Check settings to see if this run type is supported
    if verification_job.forecast_run and 'ngen' not in settings.VERF_MODES_SUPPORTED:
        return ResponseError('Verification Jobs from Ngen forecasts are not supported.')
    elif not verification_job.forecast_run and 'nwm' not in settings.VERF_MODES_SUPPORTED:
        return ResponseError('Verification Jobs requiring NWM forecast data downloads are not supported.')

    yaml_config_data = {}
    yaml_config_error_message = None

    cycle_date = None

    if verification_job.forecast_run:
        cycle_date = verification_job.forecast_run.cycle_date

        if not verification_job.verification_config or not os.path.exists(verification_job.verification_config):
            # Auto-generate YAML file in our run-specific YAML directory
            verif_output_dir = resolve_job_data_dir(verification_job)
            fs = FileSystemStorage(location=os.path.join(verif_output_dir, 'Verification_YAML'))

            # Create the directory
            os.makedirs(fs.location, exist_ok=True)

            # Delete the file if it's already there
            delete_all_files_in_directory(fs.location)

            try:
                error, config_file = create_verification_input(verification_job, None)
                if error.has_errors():
                    return ResponseError(error)
                verification_job.verification_config = config_file
                verification_job.status = StatusEnum.READY.db_instance
            except Exception as e:
                logger.info(f"Error: {e}")

        with transaction.atomic():
            verification_job.save()

    if verification_job.verification_config:
        try:
            with open(verification_job.verification_config, 'r') as file:
                yaml_config_data = yaml.safe_load(file)
        except FileNotFoundError:
            yaml_config_error_message = "Error: Uploaded YAML file not readable."
        except yaml.YAMLError as exc:
            yaml_config_error_message = f"Error parsing YAML file: {exc}"

    response = {
        'verification_job_id': verification_job.id,
        'status': verification_job.status.name,
        'created_at': verification_job.created_at,
        'submit_date': verification_job.submit_date,
        'run_start': verification_job.run_start,
        'run_end': verification_job.run_end,
        'verification_yaml_file_path': verification_job.verification_config,
        'yaml_config_data': yaml_config_data,
        'yaml_config_error_message': yaml_config_error_message,
        'job_data_dir': verification_job.job_data_dir
    }

    if verification_job.forecast_run:
        forecast_run, error_return = get_forecast_run(verification_job.forecast_run.id, request.user, run_status=list(StatusEnum))
        if error_return:
            return error_return
        response['forecast_run_id'] = forecast_run.id
        response['forecast_run'] = {
            'calibration_run_id': forecast_run.calibration_run.id,
            'domain_name': forecast_run.calibration_run.gage.domain.name,
            'forecast_run_id': forecast_run.id,
            'configuration': forecast_run.configuration.name,
            'cycle_date': cycle_date,
            'cold_start_date': forecast_run.cold_start_run.cold_start_date if forecast_run.cold_start_run else None,
            'gage_id': forecast_run.calibration_run.gage_id,
            'forecast_status': forecast_run.status.name,
            'submit_date': forecast_run.submit_date
        }

    response_validator, error_response = validate_response(VerificationJobsResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {json.dumps(response_validator.data)}')

    return Response(response_validator.data)


@extend_schema(
    request=CreateVerificationJobRequestSerializer,
    responses={
        201: CreateVerificationJobResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Create a new verification"
)
@api_view(['POST'])
@handle_exceptions
def create_verification_job(request: Request) -> Response:
    """
    Creates a new verification job for the requesting user.

    Handles the creation process by accepting verification details in the request, validating them,
    and creating a new verification job if the request is valid.

    :param request: The HTTP request object, containing user and verification job details.
    :return: A Response object with the serialized verification job data.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} ')

    validator, error_return = validate_request(CreateVerificationJobRequestSerializer, data)
    if error_return:
        return error_return

    forecast_run_id = validator.get('forecast_run_id')

    # TODO Need to be cleaned up more so we validate the Forecast Run, but waiting for David to refactor to get rid of the 'ngen' case
    forecast_run = None
    if forecast_run_id:
        forecast_run, error_return = get_forecast_run(forecast_run_id, request.user)
        if error_return:
            return error_return

    if forecast_run_id and 'ngen' not in settings.VERF_MODES_SUPPORTED:
        return ResponseError('Verification Jobs from Ngen forecasts are not supported.')
    elif not forecast_run_id and 'nwm' not in settings.VERF_MODES_SUPPORTED:
        return ResponseError('Verification Jobs requiring NWM forecast data downloads are not supported.')

    with transaction.atomic():
        # TODO This should take a Forecast_run, not a Forecast_run_id
        run = create_verification_job_internal(request.user, forecast_run_id)

        response = {'message': f'Verification Job {run.id} created', 'verification_job_id': run.id,
                    # TODO This isn't right.  Do we need to return this?
                    'job_data_dir': resolve_job_data_dir(forecast_run.calibration_run)}

        response_validator, error_response = validate_response(CreateVerificationJobResponseSerializer, response)
        if error_response:
            return error_response

        logger.debug(
            f'Returning to {get_user_email(request)} from {get_caller_name()}(){get_elapsed_str(request)} - {json.dumps(json.dumps(response_validator.data))}')
        return Response(response_validator.data, status=status.HTTP_201_CREATED)


@extend_schema(
    request=UploadVerificationYamlFileRequestSerializer,
    responses={
        200: UploadVerificationYamlFileResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Allow user to upload verification YAML file"
)
@api_view(['POST'])
@handle_exceptions
def upload_verification_yaml_file(request: Request) -> Response:
    """
    Upload YAML file for a verification job.

    This function handles the upload of a YAML file by saving it to the job-specific directory and updating the verification job.

    :param request: The HTTP request containing the YAML file data.
    :return: A JSON response confirming the upload or reporting errors.
    """
    data = request.data
    logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {data}')

    validator, error_return = validate_request(UploadVerificationYamlFileRequestSerializer, data, context={'request': request})
    if error_return:
        return error_return

    verification_job_id = validator.get('verification_job_id')

    run, error_return = get_verification_run(verification_job_id, request.user)
    if error_return:
        return error_return

    # Save to the run-specific YAML directory
    verif_output_dir = resolve_job_data_dir(run)
    fs = FileSystemStorage(location=os.path.join(verif_output_dir, 'Verification_YAML'))

    # Create the directory
    os.makedirs(fs.location, exist_ok=True)

    files = request.FILES.getlist('verification_yaml_file')

    verification_yaml_file = files[0]

    # Delete the file if it's already there
    delete_all_files_in_directory(fs.location)
    verification_yaml_file_path = os.path.join(fs.location, verification_yaml_file.name)
    logger.info(f"Saving user-uploaded verification YAML file to {verification_yaml_file_path}")
    fs.save(verification_yaml_file.name, verification_yaml_file)

    message = f"YAML file '{verification_yaml_file.name}' saved for Verification Job {run.id}"

    try:
        with open(verification_yaml_file_path, 'r') as file:
            yaml_config_data = yaml.safe_load(file)
            error, config_file = create_verification_input(run, yaml_config_data)
            if error.has_errors():
                return ResponseError(error)
            run.verification_config = config_file

            # Set run status to Ready only if the file can be read (validation to be added later)
            run.status = StatusEnum.READY.db_instance
    except Exception as exc:
        message = f"Error: {exc}"
        run.status = StatusEnum.SAVED.db_instance

    with transaction.atomic():
        run.save()

    response = {
        'message': message,
        'verification_job_id': run.id,
        'verification_yaml_file': verification_yaml_file.name,
        'verification_yaml_file_path': verification_yaml_file_path,
        'yaml_config_data': yaml_config_data,
        'status': run.status.name
    }

    response_validator, error_response = validate_response(UploadVerificationYamlFileResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(
        f'Returning to {get_user_email(request)} from {get_caller_name()}(){get_elapsed_str(request)} - {json.dumps(response_validator.data)}')
    return Response(response_validator.data)


# Commenting out this endpoint for now since the file upload handles the save already
# @extend_schema(
#     request=SaveVerificationSetupRequestSerializer,
#     responses={
#         200: SaveVerificationSetupResponseSerializer,
#         400: OpenApiResponse(
#             response=ErrorResponseSerializer,
#             description="Validation error or parsing error"
#         ),
#         500: OpenApiResponse(
#             response=ErrorResponseSerializer,
#             description="Internal server error"
#         )
#     },
#     description="Save gage tab data"
# )
# @api_view(['POST'])
# @handle_exceptions
# def save_verification_setup(request: Request) -> Response:
#     """
#     Save verification setup and update the verification job with new information.

#     This function handles updating the YAML file, clearing previously ploaded files, and updating the 
#     verification job status.

#     :param request: The HTTP request containing POST data with verification setup details.
#     :return: A JSON response confirming the update and including any errors.
#     """
#     data = request.data
#     logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {data}')

#     validator, error_return = validate_request(SaveVerificationSetupRequestSerializer, data)
#     if error_return:
#         return error_return

#     verification_job_id = validator.get('verification_job_id')
#     verification_yaml_file = validator.get('verification_yaml_file')

#     run, error_return = get_verification_job(verification_job_id, request.user)
#     if error_return:
#         return error_return

#     # Update the YAML file path - this might not be needed if the upload endpoint takes care of it
#     if run.verification_yaml_file_path != verification_yaml_file:
#         run.verification_yaml_file_path = verification_yaml_file

#     #Set run status to Ready
#     run.status = StatusEnum.READY

#     with transaction.atomic():
#         run.save()

#     response = {'message': f'Verification Job {run.id} updated', 'verification_job_id': run.id, 'status': run.status.name,
#                 'verification_yaml_file_path': verification_yaml_file}

#     response_validator, error_response = validate_response(SaveVerificationSetupResponseSerializer, response)
#     if error_response:
#         return error_response
#     logger.debug(
#         f'Returning to {get_user_email(request)} from {get_caller_name()}(){get_elapsed_str(request)} - '
#         f'{json.dumps(response_validator.data)}'
#     )

#     return Response(response_validator.data)


@extend_schema(
    request=RunVerificationJob,
    responses={
        200: SubmitVerificationJobResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Run a calibration"
)
@api_view(['POST'])
@handle_exceptions
def run_verification(request: Request) -> Response:
    """
    Submits a verification job for processing.

    :param request: HTTP request containing calibration run details.
    :return: JSON response indicating job submission status.
    """
    data = request.data
    logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {data}')

    validator, error_return = validate_request(RunVerificationJob, data)
    if error_return:
        return error_return

    verification_job_id = validator.get('verification_job_id')
    logging_config = validator.get('logging_config')

    run, error_return = get_verification_run(verification_job_id, request.user)
    if error_return:
        return error_return

    # Check settings to see if this run type is supported
    if run.forecast_run and 'ngen' not in settings.VERF_MODES_SUPPORTED:
        return ResponseError('Verification Jobs from Ngen forecasts are not supported.')
    elif not run.forecast_run and 'nwm' not in settings.VERF_MODES_SUPPORTED:
        return ResponseError('Verification Jobs requiring NWM forecast data downloads are not supported.')

    error_response = submit_job(run, logging_config=logging_config)
    if error_response:
        return error_response

    response = {'message': f'Verification Job {run.id} has been submitted',
                'verification_job_id': verification_job_id,
                'status': run.status.name,
                'submit_date': run.submit_date}

    response_validator, error_return = validate_response(SubmitVerificationJobResponseSerializer, response)
    if error_return:
        return error_return

    logger.debug(
        f'Returning to {get_user_email(request)} from {get_caller_name()}(){get_elapsed_str(request)} - {json.dumps(response_validator.data)}')

    return Response(response_validator.data)


@extend_schema(
    request=GetVerificationStatusRequestSerializer,
    responses={
        200: GetVerificationStatusResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Return the status of a verification job"
)
@api_view(['GET', 'POST'])
@handle_exceptions
def get_verification_status(request: Request) -> Response:
    """
    Retrieves the status of a verification job.
    Optionally includes performance metrics based on the request parameters.

    :param request: HTTP request containing verification run details.
    :return: JSON response with the status and associated job details.
    """
    data = request.data
    logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {data}')

    validator, error_return = validate_request(GetVerificationStatusRequestSerializer, data)
    if error_return:
        return error_return

    verification_job_id = validator.get('verification_job_id')
    include_performance_metrics = validator.get('include_performance_metrics')

    verification_job, error_return = get_verification_run(verification_job_id, request.user, run_status=list(StatusEnum))
    if error_return:
        return error_return

    # Check settings to see if this run type is supported
    if verification_job.forecast_run and 'ngen' not in settings.VERF_MODES_SUPPORTED:
        return ResponseError('Verification Jobs from Ngen forecasts are not supported.')
    elif not verification_job.forecast_run and 'nwm' not in settings.VERF_MODES_SUPPORTED:
        return ResponseError('Verification Jobs requiring NWM forecast data downloads are not supported.')

    # Prepare the main response
    response = {
        'message': f'Verification Job {verification_job.id}, status is {verification_job.status.name}',
        'verification_job_id': verification_job.id,
        'status': verification_job.status.name,
        'submit_date': verification_job.submit_date,
        'run_start': verification_job.run_start,
        'run_end': verification_job.run_end,
        'elapsed_time': verification_job.performance_metrics.elapsed_time if verification_job.performance_metrics else None
    }

    # Conditionally retrieve verification performance metrics
    verification_metrics = get_performance_metrics(verification_job.performance_metrics) if should_include_metrics(verification_job.status,
                                                                                                                   include_performance_metrics) else None

    # Conditionally add verification run performance metrics to response if requested and status is DONE or FAIL
    if verification_metrics:
        response['performance_metrics'] = verification_metrics

    fm_ver = parse_failure_messages(verification_job.failure_messages)
    if fm_ver is not None:
        response['failure_messages'] = fm_ver

    response_validator, error_response = validate_response(GetVerificationStatusResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(
        f'Returning to {get_user_email(request)} from {get_caller_name()}(){get_elapsed_str(request)} - '
        f'{json.dumps(response_validator.data)}'
    )
    logger.debug(f"[DEBUG] view request type: {type(request)}")
    logger.debug(f"[DEBUG] request._request type: {type(getattr(request, '_request', None))}")
    logger.debug(f"[DEBUG] elapsed_time on _request: {getattr(getattr(request, '_request', None), 'elapsed_time', 'MISSING')}")

    return Response(response_validator.data)


@extend_schema(
    request=VerificationJobSerializer,
    responses={
        200: GetVerificationPlotNamesResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Get a list of plot names"
)
@api_view(['GET', 'POST'])
@handle_exceptions
def get_verification_plot_names(request: Request) -> Response:
    """
    Retrieves the list of plot images for a verification job, filtered by applicable optimizations.

    :param request: The request containing either POST data or query parameters.
    :return: A JSON response with the run ID, list of plot images, and run status.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {data}')

    validator, error_return = validate_request(VerificationJobSerializer, data)
    if error_return:
        return error_return

    verification_job_id = validator.get('verification_job_id')

    run, error_return = get_verification_run(verification_job_id, request.user,
                                             run_status=[StatusEnum.RUNNING, StatusEnum.DONE, StatusEnum.CANCELLED, StatusEnum.FAILED,
                                                         StatusEnum.SERVER_ERROR])
    if error_return:
        return error_return

    plot_names = []

    # For now, get verification plots directly from the file system
    try:
        with open(run.verification_config, 'r') as file:
            yaml_config_data = yaml.safe_load(file)
            if 'general' in yaml_config_data and 'nwm_configuration' in yaml_config_data['general']:
                verification_plot_location = os.path.join(run.job_data_dir, 'plots', yaml_config_data['general']['nwm_configuration'])
                for root, dirs, files in os.walk(verification_plot_location):
                    if files:
                        for file_name in files:
                            plot_names.append({
                                'name': os.path.relpath(os.path.join(root, file_name), run.job_data_dir),
                                'display_name': file_name,
                                'description': f'Placeholder description of {file_name}',
                                'timeseries_available': False
                            })
    except Exception as e:
        logger.warning(f"Unable to get plots for {get_job_description(run)} due to error: {e}")

    response = {
        "verification_job_id": run.id,
        'plot_names': plot_names,
        'status': run.status.name
    }

    response_validator, error_response = validate_response(
        GetVerificationPlotNamesResponseSerializer,
        response,
        fields_to_truncate=['plot_names'], max_length=3

    )
    if error_response:
        return error_response
    logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {json.dumps(response_validator.data)}')
    logger.debug(
        f'Returning to {get_user_email(request)} from {get_caller_name()}(){get_elapsed_str(request)} - '
        f'{json.dumps(truncate_large_fields(response_validator.data, fields_to_truncate=["plot_names"], max_length=3))}'
    )

    return Response(response_validator.data)


@extend_schema(
    request=GetVerificationPlotRequestSerializer,
    responses={
        200: GetVerificationPlotResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Return a base64 URL for a verification plot image and the associated data"
)
@api_view(['GET', 'POST'])
@handle_exceptions
def get_verification_plot(request: Request) -> Response:
    """
    Retrieves a specific plot for a verification run, returning the plot file location.

    :param request: The request containing plot name.
    :return: A JSON response with plot details, or an error if the plot is not found.
    :raises ResponseError: If the plot cannot be found or an error occurs.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {data}')

    validator, error_return = validate_request(GetVerificationPlotRequestSerializer, data)
    if error_return:
        return error_return

    verification_job_id = validator.get('verification_job_id')

    plot_name = validator.get('plot_name')

    # Replace spaces with underscores in plot_name to avoid CacheKeyWarning
    sanitized_plot_name = plot_name.replace(" ", "_").replace("/", "_")
    # Base cache key common part
    cache_key_base = f"{sanitized_plot_name}_{verification_job_id}"
    cache_key_plot_url = f"plot_url_{cache_key_base}"

    plot_url = cache.get(cache_key_plot_url)
    plot_file_path = None
    plot_url_calculated = False  # Tracks if plot_url was calculated in this request

    run, error_return = get_verification_run(verification_job_id, request.user, run_status=[StatusEnum.RUNNING, StatusEnum.DONE])
    if error_return:
        return error_return

    # Check settings to see if this run type is supported
    if run.forecast_run and 'ngen' not in settings.VERF_MODES_SUPPORTED:
        return ResponseError('Verification Jobs from Ngen forecasts are not supported.')
    elif not run.forecast_run and 'nwm' not in settings.VERF_MODES_SUPPORTED:
        return ResponseError('Verification Jobs requiring NWM forecast data downloads are not supported.')

    # Just retrieve the file for now
    plot_file_path = os.path.join(run.job_data_dir, plot_name)
    logger.info(f'Plot file path: {plot_file_path}')
    if os.path.exists(plot_file_path):
        plot_url = png_to_base64_url(plot_file_path)
        logger.info(f'Retrieving plot from {plot_file_path}')

        # Cache the plot_url
        cache.set(cache_key_plot_url, plot_url, timeout=3600)
    else:
        return ResponseError(
            f"Error while checking existence of plot '{plot_name}' for {JobType.VERIFICATION.value.capitalize()} {run.id}: File Not Found")

    response = {
        'plot_name': plot_name,
        'plot_url': plot_url,
        'plot_file_path': plot_file_path,
        'verification_job_id': verification_job_id
    }

    # Validate and return response
    response_validator, error_response = validate_response(
        GetVerificationPlotResponseSerializer, response,
        fields_to_truncate=['plot_url', 'plot_data'], max_length=10
    )
    if error_response:
        return error_response
    logger.debug(
        f'Returning to {get_user_email(request)} from {get_caller_name()}(){get_elapsed_str(request)} - '
        f'{json.dumps(truncate_large_fields(response_validator.data, fields_to_truncate=["plot_url"], max_length=10))}'
    )

    return Response(response_validator.data)


@extend_schema(
    request=VerificationJobSerializer,
    responses={
        200: DeleteVerificationJobResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Delete a verification job"
)
@api_view(['POST', 'GET'])
@handle_exceptions
def delete_verification_job(request: Request) -> Response:
    """
    Delete a verification job. Performs a hard delete if the run status is SAVED or READY, 
    and a soft delete otherwise.

    :param request: The HTTP request object.
    :return: A Response object with the deletion confirmation.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {data}')

    validator, error_return = validate_request(VerificationJobSerializer, data)
    if error_return:
        return error_return

    verification_job_id = validator.get('verification_job_id')

    run, error_return = get_verification_run(verification_job_id, request.user, run_status=list(StatusEnum))
    if error_return:
        return error_return

    if run.status in [StatusEnum.RUNNING.db_instance, StatusEnum.SUBMITTED.db_instance]:
        return ResponseError(f'Verification Job {run.id} is running.  Cannot delete a running job')

    run_id = run.id

    # Proceed with deletion
    hard_delete(run)

    response = {'message': f'Verification Job {run.id} and associated records have been deleted', 'verification_job_id': run_id}

    response_validator, error_response = validate_response(DeleteVerificationJobResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(
        f'Returning to {get_user_email(request)} from {get_caller_name()}(){get_elapsed_str(request)} - {json.dumps(response_validator.data)}')

    return Response(response_validator.data)


def hard_delete(run: VerificationRun) -> None:
    """
    Perform a hard delete on a verification run and its related records. Deletes associated files if they exist.

    :param run: The VerificationRun instance to be deleted.
    """
    collector = Collector(using=router.db_for_write(run.__class__))

    # Collect related objects that will be deleted due to cascade
    collector.collect([run])

    with transaction.atomic():
        # Collect related objects that will be deleted due to cascade
        collector.collect([run])

        logger.debug(f"Deleting (hard delete) Verification Job {run.id}, associated records and files")
        # Iterate through the collected objects and list IDs and other fields
        for model, instances in collector.data.items():
            logger.debug(f"Verification Job {run.id} - {model.__name__}: {len(instances)} instance(s) will be deleted")
            for instance in instances:
                logger.debug(f' - {instance}')

        job_data_dir = run.job_data_dir
        run.delete()
        logger.debug(f'Deleting directory {job_data_dir} for Calibration Job {run.id}')
        if os.path.exists(job_data_dir):
            shutil.rmtree(job_data_dir)
