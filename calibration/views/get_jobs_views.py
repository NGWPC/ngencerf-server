import json
import logging
from typing import Any

from django.contrib.auth import get_user_model
from django.db.models import Q, Prefetch
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from calibration.enums import GetValidationJobsScope, StatusEnum, ValidationType
from calibration.models import CalibrationFormulation, CalibrationRun, ValidationRun, IterationParameter, ForecastRun
from calibration.util.calibration_validators import EmptySerializer, GetCalibrationJobsForEvaluationResponseSerializer, ErrorResponseSerializer, \
    GetCalibrationJobsResponseSerializer, GetCalibrationJobsRequestSerializer, CalibrationRunSerializer, GetValidationJobsResponseSerializer, \
    GetForecastJobsResponseSerializer
from calibration.views.calibration_evaluation_views import downloadable_statuses
from calibration.views.called_from import get_caller_name
from calibration.views.common import handle_exceptions, validate_request, validate_response, truncate_large_fields, get_calibration_run, \
    get_user_email

logger = logging.getLogger(__name__)

User = get_user_model()


@extend_schema(
    request=GetCalibrationJobsRequestSerializer,
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
    logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {data}')

    validator, error_return = validate_request(GetCalibrationJobsRequestSerializer, data)
    if error_return:
        return error_return

    include_archived = validator.get('include_archived')

    jobs = get_jobs(request.user,
                    include_validation_data=GetValidationJobsScope.IDS,
                    run_status=[StatusEnum.DONE],
                    include_archived=include_archived
                    )

    response = {'jobs': jobs}

    response_validator, error_response = validate_response(GetCalibrationJobsForEvaluationResponseSerializer, response, fields_to_truncate=['jobs'])
    if error_response:
        return error_response

    logger.debug(
        f'Returning to {get_user_email(request)} from {get_caller_name()}() - '
        f'{json.dumps(truncate_large_fields(response_validator.data, fields_to_truncate=["jobs"], max_length=10))}'
    )
    return Response(response_validator.data)


@extend_schema(
    request=GetCalibrationJobsRequestSerializer,
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
    logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {data}')

    validator, error_return = validate_request(GetCalibrationJobsRequestSerializer, data)
    if error_return:
        return error_return

    include_archived = validator.get('include_archived')

    jobs = get_jobs(request.user,
                    run_status=[StatusEnum.DONE],
                    include_archived=include_archived
                    )

    response = {'jobs': jobs}

    response_validator, error_response = validate_response(GetCalibrationJobsResponseSerializer, response, fields_to_truncate=['jobs'], max_length=10)
    if error_response:
        return error_response

    logger.debug(
        f'Returning to {get_user_email(request)} from {get_caller_name()}() - '
        f'{json.dumps(truncate_large_fields(response_validator.data, fields_to_truncate=["jobs"], max_length=10))}'
    )
    return Response(response_validator.data)


@extend_schema(
    request=GetCalibrationJobsRequestSerializer,
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
    Return all calibration jobs, including archived ones.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {data}')

    validator, error_return = validate_request(GetCalibrationJobsRequestSerializer, data)
    if error_return:
        return error_return

    include_archived = validator.get('include_archived')

    jobs = get_jobs(
        request.user,
        run_status=list(StatusEnum),
        include_validation_data=GetValidationJobsScope.STATUS,
        include_archived=include_archived
    )

    response = {'jobs': jobs}

    response_validator, error_response = validate_response(GetCalibrationJobsResponseSerializer, response, fields_to_truncate=['jobs'], max_length=10)
    if error_response:
        return error_response

    logger.debug(
        f'Returning to {get_user_email(request)} from {get_caller_name()}() - '
        f'{json.dumps(truncate_large_fields(response_validator.data, fields_to_truncate=["jobs"], max_length=10))}'
    )
    return Response(response_validator.data)


def get_jobs(
        user: User,
        run_status: list[StatusEnum] = None,
        include_validation_data: GetValidationJobsScope = None,
        include_archived: bool = False
) -> list[dict[str, Any]]:
    """
    Retrieves calibration jobs for the given user with optional status filtering and validation data inclusion.

    :param user: The user for whom the jobs are being fetched.
    :param run_status: List of statuses to filter jobs (e.g., DONE, FAILED).
    :param include_validation_data: Determines the level of validation data to include:
        - 'ids': Includes validation_run_ids and their count in validation_runs.
        - 'status': Includes validation status details.
    :param include_archived: Whether to include archived jobs in the queryset.
    :return: List of calibration jobs with selected fields.
    """
    # Base query: filter jobs for the user
    query = Q(owner=user)

    # If include_archived=False, exclude archived jobs
    if not include_archived:
        query &= Q(is_archived=False)

    # If a specific status list is provided, filter by those statuses
    if run_status:
        query &= Q(status__in=[s.db_instance for s in run_status])

    # Prepare Prefetch object to optimize fetching formulations, ensuring we get module names
    formulations_prefetch = Prefetch(
        'calibrationformulation_set',
        queryset=CalibrationFormulation.objects.select_related('module').only('calibration_run_id', 'module__name'),
        to_attr='prefetched_formulations'
    )

    calibration_runs_qs = CalibrationRun.objects.filter(query).only(
        'id', 'gage__gage_id', 'submit_date', 'user_formulation_name',
        'calibration_start_period', 'calibration_end_period',
        'status__name', 'job_genesis', 'created_at',
        'objective_function__name', 'optimization__name',
        'is_archived', 'is_locked'
    ).select_related(
        'gage', 'status', 'objective_function', 'optimization'
    ).prefetch_related(formulations_prefetch)

    calibration_runs = list(calibration_runs_qs)

    # Retrieve associated formulations
    formulations_map = {
        run.id: [f.module.name for f in run.prefetched_formulations]  # type: ignore[attr-defined]
        for run in calibration_runs
    }

    results = []
    for run in calibration_runs:
        result = {
            'calibration_run_id': run.id,
            'gage_id': run.gage.gage_id if run.gage else None,
            'status': run.status.name,
            'objective_function': run.objective_function.name if run.objective_function else None,
            'optimization_algorithm': run.optimization.name if run.optimization else None,
            'is_archived': run.is_archived,
            'is_locked': run.is_locked,
            'submit_date': run.submit_date,
            'formulation_name': run.user_formulation_name,
            'calibration_start_period': run.calibration_start_period,
            'calibration_end_period': run.calibration_end_period,
            'job_genesis': run.job_genesis,
            'created_at': run.created_at,
            'modules': formulations_map.get(run.id, []),
            'is_downloadable': StatusEnum.from_name(run.status.name) in downloadable_statuses
        }

        # Include validation IDs and count if requested
        if include_validation_data == GetValidationJobsScope.IDS:
            validation_ids = get_validation_jobs_internal(run.id, include_validation_data)
            result['validation_run_ids'] = validation_ids
            result['validation_runs'] = len(validation_ids)

        # Include detailed validation status if requested
        elif include_validation_data == GetValidationJobsScope.STATUS:
            result['validations'] = get_validation_jobs_internal(run.id, include_validation_data)

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
    request=CalibrationRunSerializer,
    responses={
        200: GetValidationJobsResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Retrieve validation jobs along with their starting parameter values"
)
@api_view(['GET', 'POST'])
@handle_exceptions
def get_validation_jobs(request: Request) -> Response:
    """
    Retrieves validation jobs for a specific calibration run along with initial parameter values.

    - Handles user authentication and request validation.
    - Fetches validation jobs linked to a calibration run.
    - Constructs and validates the response with serialized data.

    :param request: The HTTP request object containing calibration run data.
    :return: JSON response containing validation jobs or error details.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    calibration_run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=[StatusEnum.DONE])
    if error_return:
        return error_return

    # Retrieve validation jobs using internal helper
    validation_jobs = get_validation_jobs_internal(calibration_run_id, detail_level=GetValidationJobsScope.DETAILS)

    response = {'validation_jobs': validation_jobs}
    response_validator, error_response = validate_response(GetValidationJobsResponseSerializer, response)
    if error_response:
        return error_response

    logger.debug(f'Returning to {get_user_email(request)} from {get_caller_name()}() - {json.dumps(response_validator.data)}')
    return Response(response_validator.data)


@extend_schema(
    request=EmptySerializer,
    responses={
        200: GetForecastJobsResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Get forecast jobs"
)
@api_view(['POST', 'GET'])
@handle_exceptions
def get_forecast_jobs(request: Request) -> Response:
    """
    Retrieves all forecast jobs for a user

    :param request: The HTTP request object containing calibration run data.
    :return: JSON response with validation jobs or error information.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'{get_caller_name()}() request from {get_user_email(request)} - {data}')

    validator, error_return = validate_request(EmptySerializer, data)
    if error_return:
        return error_return

    forecast_jobs = list(ForecastRun.objects
                         .filter(calibration_run__owner=request.user)
                         .values('id', 'calibration_run_id', 'cycle__name', 'submit_date', 'calibration_run__gage__gage_id', 'status__name',
                                 'forcing_download_run__status__name'))
    for f in forecast_jobs:
        f['forecast_run_id'] = f.pop('id')
        f['cycle'] = f.pop('cycle__name')
        f['gage_id'] = f.pop('calibration_run__gage__gage_id')
        f['forecast_status'] = f.pop('status__name')
        f['forcing_download_status'] = f.pop('forcing_download_run__status__name')

    response = {'forecast_jobs': forecast_jobs}
    response_validator, error_response = validate_response(GetForecastJobsResponseSerializer, response, fields_to_truncate=['forecast_jobs'],
                                                           max_length=10)
    if error_response:
        return error_response

    logger.debug(
        f'Returning to {get_user_email(request)} from {get_caller_name()}() - '
        f'{json.dumps(truncate_large_fields(response_validator.data, fields_to_truncate=["forecast_jobs"], max_length=10))}'
    )
    return Response(response_validator.data)
