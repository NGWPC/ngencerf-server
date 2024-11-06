import logging
import os
import shutil
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction, router
from django.db.models import F, Q, Count
from django.db.models.deletion import Collector
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.enums import StatusEnum, ValidationType, JobGenesis
from calibration.models import CalibrationRun
from calibration.util.calibration_validators import GetCalibrationJobsResponseSerializer, FooterResponseSerializer, \
    ErrorResponseSerializer, CreateCalibrationRunSerializer, \
    CalibrationRunSerializer, LoadCalibrationRunResponseSerializer, ImportResponseSerializer, \
    CreateValidationRunSerializer, CreateValidationRequestSerializer, \
    GetCalibrationJobsForEvaluationResponseSerializer, EmptySerializer
from calibration.views import ngen_cal_input
from calibration.views.calibration_import_export_views import load_calibration_run_data, import_calibration_run_data
from calibration.views.common import handle_exceptions, validate_response, get_calibration_run, create_calibration_run_internal, ResponseError, \
    validate_request, truncate_large_fields, create_validation_run_internal

logger = logging.getLogger(__name__)

User = get_user_model()


@extend_schema(
    request=EmptySerializer,
    responses={
        201: CreateCalibrationRunSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Create a new calibration"
)
@api_view(['POST'])
@handle_exceptions
def create_calibration_run(request) -> Response:
    """
    Handles creating a new calibration run for the requesting user.

    :param request: The HTTP request object, containing user and calibration run details.
    :return: A Response object with the serialized calibration run data.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'create_calibration_run() request from {request.user.email}')

    validator, error_return = validate_request(EmptySerializer, data)
    if error_return:
        return error_return

    with transaction.atomic():
        run = create_calibration_run_internal(request.user)

        response = {'message': f'Calibration Run {run.id} created', 'calibration_run_id': run.id}

        response_validator, error_response = validate_response(CreateCalibrationRunSerializer, response)
        if error_response:
            return error_response

        logger.debug(f'Returning to {request.user.email} from create_calibration_run() - {response_validator.data}')
        return Response(response_validator.data, status=status.HTTP_201_CREATED)


@extend_schema(
    request=CreateValidationRequestSerializer,
    responses={
        201: CreateValidationRunSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Create a new validation for a specific worker_name and iteration"
)
@api_view(['POST'])
@handle_exceptions
def create_validation_run(request) -> Response:
    """
    Creates a new validation run for a specified calibration run and iteration.

    :param request: The HTTP request object.
    :return: JSON response with validation run details or error information.
    """
    data = request.data
    logger.debug(f'create_validation_run() request from {request.user.email}')

    validator, error_return = validate_request(CreateValidationRequestSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    iteration_id = validator.get('iteration_id')

    run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=[StatusEnum.DONE])
    if error_return:
        return error_return

    validation = create_validation_run_internal(run, iteration_id, validation_type=ValidationType.VALID_ITERATION)

    response = {'message': f'Validation Run {validation.id} created for Calibration Run {run.id}', 'calibration_run_id': run.id,
                'validation_run_id': validation.id}

    response_validator, error_response = validate_response(CreateValidationRunSerializer, response)
    if error_response:
        return error_response

    logger.debug(f'Returning to {request.user.email} from create_validation_run() - {response_validator.data}')
    return Response(response_validator.data, status=status.HTTP_201_CREATED)


@extend_schema(
    request=EmptySerializer,
    responses={
        200: GetCalibrationJobsForEvaluationResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Get all Calibration jobs for Evaluation"
)
@api_view(['POST', 'GET'])
@handle_exceptions
def get_calibration_jobs_for_evaluation(request) -> Response:
    """
    Retrieves calibration jobs that are either DONE or FAILED for evaluation purposes.

    :param request: The HTTP request object.
    :return: JSON response with a list of calibration jobs or error information.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'get_calibration_jobs_for_evaluation() request from {request.user.email} - {data}')

    validator, error_return = validate_request(EmptySerializer, data)
    if error_return:
        return error_return

    jobs = get_jobs(request.user, include_validations=True, run_status=[StatusEnum.DONE, StatusEnum.FAILED])

    response = {'jobs': jobs}

    response_validator, error_response = validate_response(GetCalibrationJobsForEvaluationResponseSerializer, response, fields_to_truncate=['jobs'])
    if error_response:
        return error_response

    logger.debug(
        f'Returning to {request.user.email} from get_calibration_jobs_for_evaluation() - {truncate_large_fields(response_validator.data, fields_to_truncate=["jobs"], max_length=10)}')
    return Response(response_validator.data)


@extend_schema(
    request=EmptySerializer,
    responses={
        200: GetCalibrationJobsResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },

    description="Get all calibration jobs for Forecast"
)
@api_view(['POST', 'GET'])
@handle_exceptions
def get_calibration_jobs_for_forecast(request):
    """
    Return only DONE jobs for forecasting
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'get_calibration_jobs_for_forecast() request from {request.user.email} - {data}')

    validator, error_return = validate_request(EmptySerializer, data)
    if error_return:
        return error_return

    validator, error_return = validate_request(EmptySerializer, data)
    if error_return:
        return error_return

    jobs = get_jobs(request.user, run_status=[StatusEnum.DONE])

    response = {'jobs': jobs}
    print('jobs', jobs)

    response_validator, error_response = validate_response(GetCalibrationJobsResponseSerializer, response, fields_to_truncate=['jobs'], max_length=10)
    if error_response:
        return error_response

    logger.debug(
        f'Returning to {request.user.email} from get_calibration_jobs_for_forecast() - {truncate_large_fields(response_validator.data, fields_to_truncate=["jobs"], max_length=10)}')
    return Response(response_validator.data)


@extend_schema(
    request=EmptySerializer,
    responses={
        200: GetCalibrationJobsResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },

    description="Get all calibration jobs"
)
@api_view(['POST', 'GET'])
@handle_exceptions
def get_calibration_jobs(request):
    """
    Return all jobs
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'get_calibration_jobs() request from {request.user.email} - {data}')

    validator, error_return = validate_request(EmptySerializer, data)
    if error_return:
        return error_return

    jobs = get_jobs(request.user, run_status=list(StatusEnum))

    response = {'jobs': jobs}

    response_validator, error_response = validate_response(GetCalibrationJobsResponseSerializer, response, fields_to_truncate=['jobs'], max_length=10)
    if error_response:
        return error_response

    logger.debug(
        f'Returning to {request.user.email} from get_calibration_jobs() - {truncate_large_fields(response_validator.data, fields_to_truncate=["jobs"], max_length=10)}')
    return Response(response_validator.data)


def get_jobs(user: User, run_status: list[StatusEnum] = None, include_validations=False) -> list[dict[str, Any]]:
    """
    Retrieves calibration jobs for the given user, optionally filtering by status and including validation information.

    :param user: The user for whom the jobs are being fetched.
    :param run_status: List of statuses to filter jobs (e.g., DONE, FAILED).
    :param include_validations: Boolean to indicate if validation run information should be included.
    :return: List of calibration jobs with selected fields.
    """
    # Construct the base query to filter jobs for the given user and exclude deleted jobs
    query = Q(owner=user) & Q(is_deleted=False)

    # Filter jobs by run_status if specified
    if run_status:
        model_status_values = [StatusEnum.from_enum(status_enum) for status_enum in run_status]
        query &= Q(status__in=model_status_values)

    # Base query without extra info
    runs_query = CalibrationRun.objects.filter(query)

    # Annotate fields to rename 'user_formulation_name' to 'formulation_name'
    runs_query = runs_query.annotate(formulation_name=F('user_formulation_name'))

    # Define the fields for selection
    default_fields = ['id', 'gage__gage_id', 'run_date', 'formulation_name', 'calibration_start_period', 'calibration_end_period', 'status__name',
                      'job_genesis']
    additional_fields = ['objective_function__name', 'optimization__name']

    selected_fields = default_fields

    # If including validations, add additional fields and annotate validation count
    if include_validations:
        selected_fields = default_fields + additional_fields
        # Add validation_runs_count if include_validations is True.  Don't include the Control run
        runs_query = runs_query.annotate(
            validation_runs_count=Count('validations', filter=~Q(validations__validation_type=ValidationType.VALID_CONTROL.value))
        ).filter(validation_runs_count__gt=0)
        selected_fields.append('validation_runs_count')

    runs = runs_query.values(*selected_fields)

    # Process the results to map the final field names
    for r in runs:
        r['calibration_run_id'] = r.pop('id')
        r['gage_id'] = r.pop('gage__gage_id')
        r['status'] = r.pop('status__name')

        if include_validations:
            r['objective_function'] = r.pop('objective_function__name')
            r['optimization_algorithm'] = r.pop('optimization__name')
            r['validation_runs'] = r.pop('validation_runs_count', 0)

    return list(runs)


@extend_schema(
    request=EmptySerializer,
    responses={
        200: FooterResponseSerializer,
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Get footer data"
)
@api_view(['POST', 'GET'])
@handle_exceptions
def get_footer(request):
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'get_footer() request from {request.user.email} - {data}')

    validator, error_return = validate_request(EmptySerializer, data)
    if error_return:
        return error_return

    response = {"version": settings.VERSION, "contact_email": settings.CONTACT_EMAIL}

    response_validator, error_response = validate_response(FooterResponseSerializer, response)
    if error_response:
        return error_response

    logger.debug(f'Returning to {request.user.email} from get_footer() - {response_validator.data}')
    return Response(response_validator.data)


@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: LoadCalibrationRunResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Load all data for a previously saved calibration"
)
@api_view(['POST', 'GET'])
@handle_exceptions
def load_calibration_run(request) -> Response:
    """
    Load all data for a previously saved calibration run.

    :param request: The HTTP request object.
    :return: A Response object containing the serialized calibration run data.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'load_calibration_run() request from {request.user.email} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=list(StatusEnum))

    if error_return:
        return error_return

    calibration_run_data = load_calibration_run_data(run, export=False)

    response_validator, error_response = validate_response(LoadCalibrationRunResponseSerializer, calibration_run_data,
                                                           fields_to_truncate=['geopackage_image_url'])

    if error_response:
        return error_response
    logger.debug(
        f'Returning to {request.user.email} from load_calibration_run() - {truncate_large_fields(response_validator.data, fields_to_truncate=["geopackage_image_url"])}')

    return Response(response_validator.data)


@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: CalibrationRunSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Clone a calibration run job"
)
@api_view(['POST', 'GET'])
@handle_exceptions
def clone_job(request) -> Response:
    """
    Clone an existing calibration run job, creating a new calibration run with identical parameters.

    :param request: The HTTP request object.
    :return: A Response object with the cloned calibration run data.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'clone_job() request from {request.user.email} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=list(StatusEnum))
    if error_return:
        return error_return

    calibration_run_data = load_calibration_run_data(run, export=True)
    new_run, messages, fatal_error = import_calibration_run_data(request, calibration_run_data, JobGenesis.CLONE)
    if fatal_error:
        return fatal_error

    # Set the new status to Saved and then we check it
    new_run.status = StatusEnum.from_enum(StatusEnum.SAVED)
    ready_to_run_messages = None
    if new_run.status in [StatusEnum.from_enum(StatusEnum.SAVED), StatusEnum.from_enum(StatusEnum.READY)]:
        ready_to_run_messages, _ = ngen_cal_input.ready_to_run(new_run)

    # noinspection PyUnresolvedReferences
    response = {'message': f'Calibration Id {run.id} has been cloned to Calibration Id {new_run.id}',
                'calibration_run_id': new_run.id,
                'status': new_run.status.name}
    # I agree that the message handling got out of hand
    if ready_to_run_messages:
        response['errors'] = ready_to_run_messages
    if messages:
        response['errors'] += messages

    response_validator, error_response = validate_response(ImportResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user.email} from clone_job() - {response_validator.data}')

    return Response(response_validator.data)


@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: CalibrationRunSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Delete a calibration run job"
)
@api_view(['POST', 'GET'])
@handle_exceptions
def delete_job(request) -> Response:
    """
    Delete a calibration run job. Performs a hard delete if the run status is SAVED or READY, and a soft delete otherwise.

    :param request: The HTTP request object.
    :return: A Response object with the deletion confirmation.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'delete_run() request from {request.user.email} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=list(StatusEnum))
    if error_return:
        return error_return

    if run.status == StatusEnum.from_enum(StatusEnum.RUNNING):
        return ResponseError(f'Calibration Run {run.id} is running.  Cannot delete a running job')

    run_id = run.id

    if run.status in [StatusEnum.from_enum(StatusEnum.SAVED), StatusEnum.from_enum(StatusEnum.READY)]:
        hard_delete(run)
    else:
        logger.debug(f"Deleting (soft delete) Calibration Run {run.id}")
        run.is_deleted = True
        run.save(update_fields=['is_deleted'])

    response = {'message': f'Calibration Id {run_id} and associated records have been deleted', 'calibration_run_id': run_id}

    response_validator, error_response = validate_response(CreateCalibrationRunSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user.email} from delete_run() - {response_validator.data}')

    return Response(response_validator.data)


def hard_delete(run: CalibrationRun) -> None:
    """
    Perform a hard delete on a calibration run and its related records. Deletes associated files if they exist.

    :param run: The CalibrationRun instance to be deleted.
    """
    collector = Collector(using=router.db_for_write(run.__class__))

    # Collect related objects that will be deleted due to cascade
    collector.collect([run])

    logger.debug(f"Deleting (hard delete) Calibration Run {run.id}, associated records and files")
    # Iterate through the collected objects and list IDs and other fields
    for model, instances in collector.data.items():
        logger.debug(f"{model.__name__}: {len(instances)} instance(s) will be deleted")
        for instance in instances:
            # Customize the fields you want to display
            logger.debug(f' -{instance}')

    job_data_dir = run.job_data_dir
    run.delete()
    logger.debug(f'Deleting directory {job_data_dir}')
    if os.path.exists(job_data_dir):
        shutil.rmtree(job_data_dir)
