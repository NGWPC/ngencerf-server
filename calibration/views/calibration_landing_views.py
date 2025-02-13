import json
import logging
import os
import shutil
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction, router
from django.db.models import F, Q
from django.db.models.deletion import Collector
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from calibration.enums import StatusEnum, ValidationType, JobGenesis, ForecastCycleEnum, GetValidationJobsScope
from calibration.models import CalibrationRun, ValidationRun, IterationParameter
from calibration.run_util.run_common import submit_job
from calibration.util.calibration_validators import GetCalibrationJobsResponseSerializer, FooterResponseSerializer, \
    ErrorResponseSerializer, CreateCalibrationRunResponseSerializer, \
    CalibrationRunSerializer, LoadCalibrationRunResponseSerializer, ImportResponseSerializer, \
    CreateAndRunValidationResponseSerializer, CreateValidationRequestSerializer, \
    GetCalibrationJobsForEvaluationResponseSerializer, EmptySerializer, CreateForecastRequestSerializer, CreateAndRunForecastResponseSerializer, \
    LoadCalibrationJobSerializer
from calibration.views import ngen_cal_input
from calibration.views.calibration_import_export_views import load_calibration_run_data, import_calibration_run_data
from calibration.views.common import handle_exceptions, validate_response, get_calibration_run, create_calibration_run_internal, ResponseError, \
    validate_request, truncate_large_fields, create_validation_run_internal, create_forecast_run_internal

logger = logging.getLogger(__name__)

User = get_user_model()


@extend_schema(
    request=EmptySerializer,
    responses={
        201: CreateCalibrationRunResponseSerializer,
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
def create_calibration_run(request: Request) -> Response:
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

        response = {'message': f'Calibration Job {run.id} created', 'calibration_run_id': run.id}

        response_validator, error_response = validate_response(CreateCalibrationRunResponseSerializer, response)
        if error_response:
            return error_response

        logger.debug(f'Returning to {request.user.email} from create_calibration_run() - {json.dumps(json.dumps(response_validator.data))}')
        return Response(response_validator.data, status=status.HTTP_201_CREATED)


@extend_schema(
    request=CreateValidationRequestSerializer,
    responses={
        201: CreateAndRunValidationResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Create and run a new validation for a specific iteration"
)
@api_view(['POST'])
@handle_exceptions
def create_and_run_validation(request: Request) -> Response:
    """
    Creates and runs a new validation run for a specified calibration run and iteration.

    :param request: The HTTP request object containing calibration and iteration details.
    :return: JSON response with validation run details or error information.
    """
    data = request.data
    logger.debug(f'create_and_run_validation() request from {request.user.email}')

    validator, error_return = validate_request(CreateValidationRequestSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    iteration_id = validator.get('iteration_id')

    calibration_run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=[StatusEnum.DONE])
    if error_return:
        return error_return

    # Check if a ValidationRun already exists for this CalibrationRun and Iteration
    existing_validation_run = ValidationRun.objects.filter(
        calibration_run=calibration_run,
        iteration_id=iteration_id,
        status__in = [StatusEnum.DONE.db_instance, StatusEnum.RUNNING.db_instance]
    ).first()
    if existing_validation_run:
        return ResponseError(f'Validation Job {existing_validation_run.id} already exists for '
                             f'Calibration Job {calibration_run.id}, iteration id {iteration_id}')

    validation_run = create_validation_run_internal(
        calibration_run,
        iteration_id,
        validation_type=ValidationType.VALID_ITERATION
    )
    submit_job(validation_run)

    response = {
        'message': f'Validation Job {validation_run.id} created and submitted for Calibration Job {calibration_run.id}',
        'calibration_run_id': calibration_run.id,
        'validation_run_id': validation_run.id,
        'status': validation_run.status.name,
        'submit_date': validation_run.submit_date
    }

    response_validator, error_response = validate_response(CreateAndRunValidationResponseSerializer, response)
    if error_response:
        return error_response

    logger.debug(f'Returning to {request.user.email} from create_and_run_validation() - {json.dumps(response_validator.data)}')
    return Response(response_validator.data, status=status.HTTP_201_CREATED)


@extend_schema(
    request=CreateForecastRequestSerializer,
    responses={
        201: CreateAndRunForecastResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Create and run a new forecast"
)
@api_view(['POST'])
@handle_exceptions
def create_and_run_forecast(request: Request) -> Response:
    """
    Creates and runs a new forecast run for a specified calibration run and cycle_name name.

    :param request: The HTTP request object containing calibration and iteration details.
    :return: JSON response with validation run details or error information.
    """
    data = request.data
    logger.debug(f'create_and_run_forecast() request from {request.user.email}')

    validator, error_return = validate_request(CreateForecastRequestSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    cycle_name = validator.get('cycle_name')

    calibration_run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=[StatusEnum.DONE])
    if error_return:
        return error_return

    forecast_run = create_forecast_run_internal(
        calibration_run,
        ForecastCycleEnum.get_instance(cycle_name)
    )
    submit_job(forecast_run.forcing_download_run)

    response = {
        'message': f'Forcing download job for Forecast Job {forecast_run.id} created and submitted for Calibration Job {calibration_run.id}',
        'calibration_run_id': calibration_run.id,
        'forecast_run_id': forecast_run.id,
        'forecast_status': forecast_run.status.name,
        'forecast_forcing_download_status': forecast_run.forcing_download_run.status.name,
        'submit_date': forecast_run.forcing_download_run.submit_date
    }

    response_validator, error_response = validate_response(CreateAndRunForecastResponseSerializer, response)
    if error_response:
        return error_response

    logger.debug(f'Returning to {request.user.email} from create_and_run_validation() - {json.dumps(response_validator.data)}')
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
def get_calibration_jobs_for_evaluation(request: Request) -> Response:
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

    jobs = get_jobs(request.user, include_validation_data=GetValidationJobsScope.IDS,
                    run_status=[StatusEnum.DONE, StatusEnum.FAILED, StatusEnum.SERVER_ERROR, StatusEnum.CANCELLED])

    response = {'jobs': jobs}

    response_validator, error_response = validate_response(GetCalibrationJobsForEvaluationResponseSerializer, response, fields_to_truncate=['jobs'])
    if error_response:
        return error_response

    logger.debug(
        f'Returning to {request.user.email} from get_calibration_jobs_for_evaluation() - '
        f'{json.dumps(truncate_large_fields(response_validator.data, fields_to_truncate=["jobs"], max_length=10))}'
    )
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
def get_calibration_jobs_for_forecast(request: Request) -> Response:
    """
    Returns only DONE calibration jobs for forecasting purposes.

    :param request: The HTTP request object.
    :return: JSON response with a list of calibration jobs or error information.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'get_calibration_jobs_for_forecast() request from {request.user.email} - {data}')

    validator, error_return = validate_request(EmptySerializer, data)
    if error_return:
        return error_return

    jobs = get_jobs(request.user, run_status=[StatusEnum.DONE])

    response = {'jobs': jobs}

    response_validator, error_response = validate_response(GetCalibrationJobsResponseSerializer, response, fields_to_truncate=['jobs'], max_length=10)
    if error_response:
        return error_response

    logger.debug(
        f'Returning to {request.user.email} from get_calibration_jobs_for_forecast() - '
        f'{json.dumps(truncate_large_fields(response_validator.data, fields_to_truncate=["jobs"], max_length=10))}'
    )
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

    jobs = get_jobs(request.user, run_status=list(StatusEnum), include_validation_data=GetValidationJobsScope.STATUS)

    response = {'jobs': jobs}

    response_validator, error_response = validate_response(GetCalibrationJobsResponseSerializer, response, fields_to_truncate=['jobs'], max_length=10)
    if error_response:
        return error_response

    logger.debug(
        f'Returning to {request.user.email} from get_calibration_jobs() - '
        f'{json.dumps(truncate_large_fields(response_validator.data, fields_to_truncate=["jobs"], max_length=10))}'
    )
    return Response(response_validator.data)


def get_jobs(
        user: User,
        run_status: list[StatusEnum] = None,
        include_validation_data: GetValidationJobsScope = None
) -> list[dict[str, Any]]:
    """
    Retrieves calibration jobs for the given user with optional status filtering and validation data inclusion.

    :param user: The user for whom the jobs are being fetched.
    :param run_status: List of statuses to filter jobs (e.g., DONE, FAILED).
    :param include_validation_data: Determines the level of validation data to include:
        - 'ids': Includes validation_run_ids and their count in validation_runs.
        - 'status': Includes validation status details.
    :return: List of calibration jobs with selected fields.
    """
    # Base query to filter jobs for the given user, excluding deleted jobs
    query = Q(owner=user, is_deleted=False)

    # If a specific status list is provided, filter by those statuses
    if run_status:
        query &= Q(status__in=[status.db_instance for status in run_status])

    # Fetch calibration runs, annotating user-specific fields like formulation_name
    calibration_runs = (
        CalibrationRun.objects.filter(query)
        .annotate(formulation_name=F('user_formulation_name'))
        .values(
            'id', 'gage__gage_id', 'submit_date', 'formulation_name',
            'calibration_start_period', 'calibration_end_period',
            'status__name', 'job_genesis', 'created_at',
            'objective_function__name', 'optimization__name'
        )
    )

    results = []
    for run in calibration_runs:
        # Map fields from the query to the desired response format
        result = {
            'calibration_run_id': run.pop('id'),
            'gage_id': run.pop('gage__gage_id'),
            'status': run.pop('status__name'),
            'objective_function': run.pop('objective_function__name'),
            'optimization_algorithm': run.pop('optimization__name'),
            **run
        }

        # Include validation IDs and count if requested
        if include_validation_data == GetValidationJobsScope.IDS:
            validation_ids = get_validation_jobs_internal(
                calibration_run_id=result['calibration_run_id'],
                detail_level=include_validation_data
            )
            result['validation_run_ids'] = validation_ids
            result['validation_runs'] = len(validation_ids)

        # Include detailed validation status if requested
        elif include_validation_data == GetValidationJobsScope.STATUS:
            result['validations'] = get_validation_jobs_internal(
                calibration_run_id=result['calibration_run_id'],
                detail_level=include_validation_data
            )

        results.append(result)

    return results


def get_validation_jobs_internal(
        calibration_run_id: int,
        detail_level: GetValidationJobsScope = GetValidationJobsScope.IDS,
) -> list[dict[str, Any]] | list[int]:
    """
    Retrieves validation jobs for a specific calibration job.

    :param calibration_run_id: ID of the calibration run to fetch validation jobs for.
    :param detail_level: Determines the level of detail in the response:
        - 'ids': Returns only validation job IDs excluding VALID_CONTROL.
        - 'status': Returns validation_run_id, validation_type, and status, including VALID_CONTROL.
        - 'detailed': Returns full validation job details including parameters.
    :return: A list of validation job IDs, status summaries, or detailed dicts.
    """
    # Filter validation jobs based on the detail level
    if detail_level in [GetValidationJobsScope.IDS, GetValidationJobsScope.DETAILS]:
        # Exclude VALID_CONTROL for 'ids' detail level
        validation_filter_condition = ~Q(validation_type=ValidationType.VALID_CONTROL.value)
    else:
        # No filtering for other detail levels
        validation_filter_condition = Q()

    # Query for validation jobs associated with the given calibration run
    validation_jobs_query = ValidationRun.objects.filter(
        calibration_run_id=calibration_run_id
    ).filter(validation_filter_condition)

    if detail_level == GetValidationJobsScope.IDS:
        # Return a list of validation job IDs
        return list(validation_jobs_query.values_list('id', flat=True))

    if detail_level == GetValidationJobsScope.STATUS:
        # Include all validation types for status-level detail
        return [
            {
                "validation_run_id": job.id,
                "validation_type": job.validation_type,
                "status": job.status.name,
            }
            for job in validation_jobs_query
        ]

    if detail_level == GetValidationJobsScope.DETAILS:
        # Return a detailed list of validation job information, including parameters
        return [
            {
                "validation_run_id": job.id,
                "submit_date": job.submit_date,
                "status": job.status.name,
                "validation_type": job.validation_type,
                "iteration_num": job.iteration_num if job.iteration else None,
                "parameters": [
                    {"name": param["calibration_parameter__name"], "value": param["tuned_value"]}
                    for param in (
                        IterationParameter.objects.filter(
                            iteration__calibration_run=job.calibration_run,
                            iteration__best_params=True
                        )
                        if job.validation_type == ValidationType.VALID_BEST.value
                        else IterationParameter.objects.filter(iteration=job.iteration)
                    ).values("calibration_parameter__name", "tuned_value")
                ],
                "best": job.validation_type == ValidationType.VALID_BEST.value,
            }
            for job in validation_jobs_query
        ]

    # Raise an error for invalid detail levels
    raise ValueError(f"Invalid detail_level: {detail_level}")


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
@permission_classes([AllowAny])
def get_footer(request: Request) -> Response:
    """
    Retrieve footer data such as version and contact email.

    :param request: The HTTP request object.
    :return: A Response object with version and contact information.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    user = (
        request.user.email
        if getattr(request.user, "is_authenticated", False) and hasattr(request.user, "email")
        else "Anonymous"
    )

    logger.debug(f'get_footer() request from {user} - {data}')

    validator, error_return = validate_request(EmptySerializer, data)
    if error_return:
        return error_return

    response = {"version": settings.VERSION, "date": settings.DATE,
                "commit_hash": settings.COMMIT_HASH,
                "ngenCerf_version": settings.NGENCERF_VERSION,
                "ngenCerf_date": settings.NGENCERF_DATE,
                "contact_email": settings.CONTACT_EMAIL}

    response_validator, error_response = validate_response(FooterResponseSerializer, response)
    if error_response:
        return error_response

    logger.debug(f'Returning to {user} from get_footer() - {json.dumps(response_validator.data)}')
    return Response(response_validator.data)


@extend_schema(
    request=LoadCalibrationJobSerializer,
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
def load_calibration_run(request: Request) -> Response:
    """
    Load all data for a previously saved calibration run.

    :param request: The HTTP request object.
    :return: A Response object containing the serialized calibration run data.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'load_calibration_run() request from {request.user.email} - {data}')

    validator, error_return = validate_request(LoadCalibrationJobSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    include_gpkg_map = validator.get('include_gpkg_map')

    run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=list(StatusEnum))

    if error_return:
        return error_return

    calibration_run_data = load_calibration_run_data(run, export=False, include_gpkg_map=include_gpkg_map)

    response_validator, error_response = validate_response(LoadCalibrationRunResponseSerializer, calibration_run_data,
                                                           fields_to_truncate=['geopackage_image_url'])

    if error_response:
        return error_response
    logger.debug(
        f'Returning to {request.user.email} from load_calibration_run() - '
        f'{json.dumps(truncate_large_fields(response_validator.data, fields_to_truncate=["geopackage_image_url"]))}'
    )

    return Response(response_validator.data)


@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: ImportResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Clone a calibration job"
)
@api_view(['POST', 'GET'])
@handle_exceptions
def clone_job(request: Request) -> Response:
    """
    Clone an existing calibration job, creating a new calibration run with identical parameters.

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
    new_run.status = StatusEnum.SAVED.db_instance
    ready_to_run_messages = None
    if new_run.status in [StatusEnum.SAVED.db_instance, StatusEnum.RUNNING.db_instance]:
        ready_to_run_messages, _ = ngen_cal_input.ready_to_run(new_run)

    # noinspection PyUnresolvedReferences
    response = {'message': f'Calibration Job {run.id} has been cloned to Calibration Job {new_run.id}',
                'calibration_run_id': new_run.id,
                'status': new_run.status.name}
    # I agree that the message handling got out of hand
    if ready_to_run_messages:
        response['errors'] = ready_to_run_messages
    if messages:
        response.setdefault('errors', []).extend(messages)

    response_validator, error_response = validate_response(ImportResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user.email} from clone_job() - {json.dumps(response_validator.data)}')

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
    description="Delete a calibration job"
)
@api_view(['POST', 'GET'])
@handle_exceptions
def delete_job(request: Request) -> Response:
    """
    Delete a calibration job. Performs a hard delete if the run status is SAVED or READY, and a soft delete otherwise.

    :param request: The HTTP request object.
    :return: A Response object with the deletion confirmation.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'delete_job() request from {request.user.email} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=list(StatusEnum))
    if error_return:
        return error_return

    if run.status == StatusEnum.RUNNING.db_instance:
        return ResponseError(f'Calibration Job {run.id} is running.  Cannot delete a running job')

    run_id = run.id

    if run.status in [StatusEnum.SAVED.db_instance, StatusEnum.RUNNING.db_instance]:
        hard_delete(run)
    else:
        logger.debug(f"Deleting (soft delete) Calibration Job {run.id}")
        run.is_deleted = True
        run.save(update_fields=['is_deleted'])

    response = {'message': f'Calibration Id {run_id} and associated records have been deleted', 'calibration_run_id': run_id}

    response_validator, error_response = validate_response(CreateCalibrationRunResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user.email} from delete_job() - {json.dumps(response_validator.data)}')

    return Response(response_validator.data)


def hard_delete(run: CalibrationRun) -> None:
    """
    Perform a hard delete on a calibration run and its related records. Deletes associated files if they exist.

    :param run: The CalibrationRun instance to be deleted.
    """
    collector = Collector(using=router.db_for_write(run.__class__))

    # Collect related objects that will be deleted due to cascade
    collector.collect([run])

    logger.debug(f"Deleting (hard delete) Calibration Job {run.id}, associated records and files")
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
