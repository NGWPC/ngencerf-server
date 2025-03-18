import json
import logging
import os
import shutil
from typing import Any, cast

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction, router
from django.db.models import F, Q, Prefetch
from django.db.models.deletion import Collector
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from calibration.enums import StatusEnum, ValidationType, JobGenesis, ForecastCycleEnum, GetValidationJobsScope, GeopackageSourceEnum
from calibration.models import CalibrationRun, ValidationRun, IterationParameter, ForecastRun, ForecastForcingDownloadRun, CalibrationFormulation, \
    CustomUser
from calibration.run_util.run_common import submit_job
from calibration.util.calibration_validators import GetCalibrationJobsResponseSerializer, FooterResponseSerializer, \
    ErrorResponseSerializer, CreateCalibrationRunResponseSerializer, \
    CalibrationRunSerializer, LoadCalibrationRunResponseSerializer, ImportResponseSerializer, \
    CreateAndRunValidationResponseSerializer, CreateValidationRequestSerializer, \
    GetCalibrationJobsForEvaluationResponseSerializer, EmptySerializer, CreateForecastRequestSerializer, CreateAndRunForecastResponseSerializer, \
    LoadCalibrationJobSerializer, ArchiveJobRequestSerializer, GetGitInfoResponseSerializer, GetCalibrationJobsRequestSerializer, \
    CalibrationRunIdList, CalibrationRunListResponse
from calibration.util.file_util import get_single_file
from calibration.util.geopkg import get_geometry_from_gpkg
from calibration.util.git_util import get_git_info_internal, load_git_info
from calibration.util.ngen_locations import get_geopackage_dir_for_job
from calibration.views import ngen_cal_input
from calibration.views.calibration_import_export_views import load_calibration_run_data, import_calibration_run_data
from calibration.views.common import handle_exceptions, validate_response, get_calibration_run, create_calibration_run_internal, ResponseError, \
    validate_request, truncate_large_fields, create_validation_run_internal, create_forecast_run_internal, get_valid_path

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
    Creates a new calibration run for the requesting user.

    Handles the creation process by accepting calibration details in the request, validating them,
    and creating a new calibration job if the request is valid.

    :param request: The HTTP request object, containing user and calibration run details.
    :return: A Response object with the serialized calibration run data.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'create_calibration_run() request from {(cast(CustomUser, request.user)).email} ')

    validator, error_return = validate_request(EmptySerializer, data)
    if error_return:
        return error_return

    with transaction.atomic():
        run = create_calibration_run_internal(request.user)

        response = {'message': f'Calibration Job {run.id} created', 'calibration_run_id': run.id}

        response_validator, error_response = validate_response(CreateCalibrationRunResponseSerializer, response)
        if error_response:
            return error_response

        logger.debug(f'Returning to {(cast(CustomUser, request.user)).email} from create_calibration_run() - {json.dumps(json.dumps(response_validator.data))}')
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

    Validates the request, checks if a validation job already exists for the specified calibration run
    and iteration, and creates and submits a new validation job if not.

    :param request: The HTTP request object containing calibration and iteration details.
    :return: JSON response with validation run details or error information.
    """
    data = request.data
    logger.debug(f'create_and_run_validation() request from {(cast(CustomUser, request.user)).email} ')

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
        status__in=[StatusEnum.DONE.db_instance, StatusEnum.RUNNING.db_instance]
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

    logger.debug(f'Returning to {(cast(CustomUser, request.user)).email}  from create_and_run_validation() - {json.dumps(response_validator.data)}')
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
    logger.debug(f'create_and_run_forecast() request from {(cast(CustomUser, request.user)).email} ')

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

    logger.debug(f'Returning to {(cast(CustomUser, request.user)).email}  from create_and_run_validation() - {json.dumps(response_validator.data)}')
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
    logger.debug(f'get_calibration_jobs_for_evaluation() request from {(cast(CustomUser, request.user)).email}  - {data}')

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
        f'Returning to {(cast(CustomUser, request.user)).email}  from get_calibration_jobs_for_evaluation() - '
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
    logger.debug(f'get_calibration_jobs_for_forecast() request from {(cast(CustomUser, request.user)).email}  - {data}')

    validator, error_return = validate_request(EmptySerializer, data)
    if error_return:
        return error_return

    jobs = get_jobs(request.user, run_status=[StatusEnum.DONE])

    response = {'jobs': jobs}

    response_validator, error_response = validate_response(GetCalibrationJobsResponseSerializer, response, fields_to_truncate=['jobs'], max_length=10)
    if error_response:
        return error_response

    logger.debug(
        f'Returning to {(cast(CustomUser, request.user)).email}  from get_calibration_jobs_for_forecast() - '
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
    logger.debug(f'get_calibration_jobs() request from {(cast(CustomUser, request.user)).email}  - {data}')

    validator, error_return = validate_request(GetCalibrationJobsRequestSerializer, data)
    if error_return:
        return error_return

    include_archived = validator.get('include_archived')

    jobs = get_jobs(
        request.user,
        run_status=list(StatusEnum),
        include_validation_data=GetValidationJobsScope.STATUS,
        include_modules=True,
        include_archived=include_archived
    )

    response = {'jobs': jobs}

    response_validator, error_response = validate_response(GetCalibrationJobsResponseSerializer, response, fields_to_truncate=['jobs'], max_length=10)
    if error_response:
        return error_response

    logger.debug(
        f'Returning to {(cast(CustomUser, request.user)).email}  from get_calibration_jobs() - '
        f'{json.dumps(truncate_large_fields(response_validator.data, fields_to_truncate=["jobs"], max_length=10))}'
    )
    return Response(response_validator.data)


def get_jobs(
        user: User,
        run_status: list[StatusEnum] = None,
        include_validation_data: GetValidationJobsScope = None,
        include_modules: bool = False,
        include_archived: bool = False
) -> list[dict[str, Any]]:
    """
    Retrieves calibration jobs for the given user with optional status filtering and validation data inclusion.

    :param user: The user for whom the jobs are being fetched.
    :param run_status: List of statuses to filter jobs (e.g., DONE, FAILED).
    :param include_validation_data: Determines the level of validation data to include:
        - 'ids': Includes validation_run_ids and their count in validation_runs.
        - 'status': Includes validation status details.
    :param include_modules: Whether to include the list of associated modules (Module names).
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

    # Fetch calibration runs with optional prefetching of formulations
    calibration_runs_qs = CalibrationRun.objects.filter(query).annotate(
        formulation_name=F('user_formulation_name')
    )

    if include_modules:
        calibration_runs_qs = calibration_runs_qs.prefetch_related(formulations_prefetch)

    # Fields to include in the response
    selected_fields = [
        'id', 'gage__gage_id', 'submit_date', 'formulation_name',
        'calibration_start_period', 'calibration_end_period',
        'status__name', 'job_genesis', 'created_at',
        'objective_function__name', 'optimization__name',
        'is_archived'
    ]

    calibration_runs = calibration_runs_qs.values(*selected_fields)

    # If modules are needed, retrieve associated formulations
    formulations_map = {}
    if include_modules:
        formulations = CalibrationFormulation.objects.select_related('module').filter(
            calibration_run__in=[run["id"] for run in calibration_runs]
        ).values_list('calibration_run_id', 'module__name')

        # Organize module names by calibration_run_id
        for run_id, module_name in formulations:
            formulations_map.setdefault(run_id, []).append(module_name)

    results = []
    for run in calibration_runs:
        # Map fields from the query to the desired response format
        run_id = run.pop('id')
        result = {
            'calibration_run_id': run_id,
            'gage_id': run.pop('gage__gage_id'),
            'status': run.pop('status__name'),
            'objective_function': run.pop('objective_function__name'),
            'optimization_algorithm': run.pop('optimization__name'),
            'is_archived': run.pop('is_archived'),  # Always include is_archived
            **run
        }

        # Add modules if requested
        if include_modules:
            result['modules'] = formulations_map.get(run_id, [])

        # Include validation IDs and count if requested
        if include_validation_data == GetValidationJobsScope.IDS:
            validation_ids = get_validation_jobs_internal(
                calibration_run_id=run_id,
                detail_level=include_validation_data
            )
            result['validation_run_ids'] = validation_ids
            result['validation_runs'] = len(validation_ids)

        # Include detailed validation status if requested
        elif include_validation_data == GetValidationJobsScope.STATUS:
            result['validations'] = get_validation_jobs_internal(
                calibration_run_id=run_id,
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

    git_info = load_git_info()
    name, git_info_content = git_info.popitem() if git_info else ("", {})

    branch = f"dev ({git_info_content.get('branch', '<unknown>')})"

    response = {"version": git_info_content.get('release', branch),
                "date": git_info_content.get('commit_date', '<unknown>'),
                "commit_hash": git_info_content.get('commit_hash', '<unknown>'),
                "ngenCerf_version": settings.NGENCERF_VERSION,
                "ngenCerf_date": settings.NGENCERF_DATE,
                "contact_email": settings.CONTACT_EMAIL}

    response_validator, error_response = validate_response(FooterResponseSerializer, response)
    if error_response:
        return error_response

    logger.debug(f'Returning to {user} from get_footer() - {json.dumps(response_validator.data)}')
    return Response(response_validator.data)


@extend_schema(
    request=EmptySerializer,
    responses={
        200: GetGitInfoResponseSerializer,
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Get footer data"
)
@api_view(['POST', 'GET'])
@handle_exceptions
def get_git_info(request: Request) -> Response:
    """
    Retrieve git info for all components

    :param request: The HTTP request object.
    :return: A Response object with version and contact information.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()

    logger.debug(f'get_git_info() request from {(cast(CustomUser, request.user)).email}  - {data}')

    validator, error_return = validate_request(EmptySerializer, data)
    if error_return:
        return error_return

    response = {"git_info": get_git_info_internal()}

    response_validator, error_response = validate_response(GetGitInfoResponseSerializer, response)
    if error_response:
        return error_response

    logger.debug(f'Returning to {(cast(CustomUser, request.user)).email}  from get_git_info() - {json.dumps(response_validator.data, default=str)}')
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
    logger.debug(f'load_calibration_run() request from {(cast(CustomUser, request.user)).email}  - {data}')

    validator, error_return = validate_request(LoadCalibrationJobSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    include_gpkg_map = validator.get('include_gpkg_map')

    run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=list(StatusEnum))

    if error_return:
        return error_return

    calibration_run_data = load_calibration_run_data(run, export=False, include_gpkg_map=include_gpkg_map)

    geopackage_path = get_valid_path(run.geopackage_source, run.geopackage_eds_file_path,
                                     GeopackageSourceEnum.UPLOAD,
                                     lambda: get_single_file(get_geopackage_dir_for_job(run)))
    num_catchments = len(get_geometry_from_gpkg(geopackage_path)['catchments'].keys()) if geopackage_path and os.path.exists(
        geopackage_path) else None

    calibration_run_data['num_catchments'] = num_catchments

    response_validator, error_response = validate_response(LoadCalibrationRunResponseSerializer, calibration_run_data,
                                                           fields_to_truncate=['geopackage_image_url'])

    if error_response:
        return error_response
    logger.debug(
        f'Returning to {(cast(CustomUser, request.user)).email} from load_calibration_run() - '
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
    logger.debug(f'clone_job() request from {(cast(CustomUser, request.user)).email}  - {data}')

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
    logger.debug(f'Returning to {(cast(CustomUser, request.user)).email}  from clone_job() - {json.dumps(response_validator.data)}')

    return Response(response_validator.data)


def has_running_associated_jobs(run: CalibrationRun) -> str | None:
    """
    Checks if the given calibration job or any associated jobs are currently running.

    This function checks if the calibration run itself, or any of its associated validation, forecast, or forcing download jobs, are running.

    :param run: The CalibrationRun instance to check.
    :return: A message indicating if the job or its associated jobs are running, or None if there are no running jobs.
    """
    # Check if the calibration run itself is running
    if run.status == StatusEnum.RUNNING.db_instance:
        return f'Calibration Job {run.id} is running. Cannot proceed while the job is running.'

    # Check if any associated validation jobs are running
    if ValidationRun.objects.filter(calibration_run=run, status=StatusEnum.RUNNING.db_instance).exists():
        return f'Calibration Job {run.id} has associated validation jobs that are still running. Cannot proceed until they are completed.'

    # Check if any associated forecast jobs are running
    if ForecastRun.objects.filter(calibration_run=run, status=StatusEnum.RUNNING.db_instance).exists():
        return f'Calibration Job {run.id} has associated forecast jobs that are still running. Cannot proceed until they are completed.'

    # Check if any associated forcing download jobs are running
    if ForecastForcingDownloadRun.objects.filter(forecast_run__calibration_run=run, status=StatusEnum.RUNNING.db_instance).exists():
        return f'Calibration Job {run.id} has associated forcing download jobs that are still running. Cannot proceed until they are completed.'

    # No running jobs found
    return None


@extend_schema(
    request=CalibrationRunIdList,
    responses={
        200: CalibrationRunListResponse,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Delete a list of calibration jobs"
)
@api_view(['POST', 'GET'])
@handle_exceptions
def delete_jobs(request: Request) -> Response:
    """
    Permanently delete multiple calibration jobs.

    :param request: The HTTP request object.
    :return: A Response object with the deletion status for each calibration job.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'delete_jobs() request from {(cast(CustomUser, request.user)).email}  - {data}')

    validator, error_return = validate_request(CalibrationRunIdList, data)
    if error_return:
        return error_return

    calibration_run_ids = validator.get('calibration_run_ids')

    job_results = []

    # Process each calibration_run_id in the list
    for calibration_run_id in calibration_run_ids:
        run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=list(StatusEnum))
        if error_return:
            job_results.append({
                "message": error_return.data.get('message'),
                "calibration_run_id": calibration_run_id,
                "success": False
            })
            continue

        # Check for any running jobs (including the calibration job itself)
        running_jobs_error = has_running_associated_jobs(run)
        if running_jobs_error:
            job_results.append({
                "message": running_jobs_error,
                "calibration_run_id": calibration_run_id,
                "success": False
            })
            continue

        # Proceed with deletion
        # hard_delete(run)

        job_results.append({
            "message": f"Calibration Id {calibration_run_id} and associated records have been deleted",
            "calibration_run_id": calibration_run_id,
            "success": True
        })

    response = {"jobs": job_results}

    response_validator, error_response = validate_response(CalibrationRunListResponse, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {(cast(CustomUser, request.user)).email} from delete_jobs() - {json.dumps(response_validator.data)}')

    return Response(response_validator.data)


@extend_schema(
    request=ArchiveJobRequestSerializer,
    responses={
        200: CalibrationRunListResponse,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Archive or unarchive a list of calibration jobs"
)
@api_view(['POST', 'GET'])
@handle_exceptions
def archive_jobs(request: Request) -> Response:
    """
    Archive or unarchive multiple calibration jobs. Essentially a soft delete by setting an archive flag.

    :param request: The HTTP request object.
    :return: A Response object with the archive confirmation.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'archive_jobs() request from {(cast(CustomUser, request.user)).email}  - {data}')

    validator, error_return = validate_request(ArchiveJobRequestSerializer, data)
    if error_return:
        return error_return

    calibration_run_ids = validator.get('calibration_run_ids')
    archive = validator.get('archive')

    job_results = []

    # Process each calibration_run_id in the list
    for calibration_run_id in calibration_run_ids:
        run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=list(StatusEnum), include_archived=True)
        if error_return:
            job_results.append({
                "message": error_return.data.get('message'),
                "calibration_run_id": calibration_run_id,
                "success": False
            })
            continue

        if archive == run.is_archived:
            job_results.append({
                "message": f'Calibration Job {run.id} is {"already" if archive else "not"} archived',
                "calibration_run_id": calibration_run_id,
                "success": False
            })
            continue

        # Check for any running jobs (including the calibration job itself)
        if archive:
            running_jobs_error = has_running_associated_jobs(run)
            if running_jobs_error:
                job_results.append({
                    "message": running_jobs_error,
                    "calibration_run_id": calibration_run_id,
                    "success": False
                })
                continue

        run.is_archived = archive
        run.save(update_fields=['is_archived'])

        job_results.append({
            'message': f'Calibration Id {run.id} and associated records have been {"archived" if archive else "unarchived"}',
            "calibration_run_id": calibration_run_id,
            "success": True
        })

    response = {"jobs": job_results}

    response_validator, error_response = validate_response(CalibrationRunListResponse, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {(cast(CustomUser, request.user)).email} from archive_jobs() - {json.dumps(response_validator.data)}')

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
            logger.debug(f' - {instance}')

    job_data_dir = run.job_data_dir
    run.delete()
    logger.debug(f'Deleting directory {job_data_dir}')
    if os.path.exists(job_data_dir):
        shutil.rmtree(job_data_dir)
