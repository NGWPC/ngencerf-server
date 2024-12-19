import logging
import os

import pandas as pd
from datetimerange import DateTimeRange
from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.forms import model_to_dict
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiExample
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from calibration.enums import StatusEnum, JobType
from calibration.models import Iteration, ValidationRun, ForecastRun, Status
from calibration.run_util.run_common import cancel_job_common, submit_job
from calibration.run_util.run_ngen_cal_pw import SlurmStatusEnum, run_calibration_job_callback_pw, run_validation_job_callback_pw, \
    run_forecast_job_callback_pw, run_forecast_forcing_download_job_callback_pw
from calibration.util.calibration_validators import CalibrationRunSerializer, GenericResponseSerializer, \
    ErrorResponseSerializer, ReportIterationSerializer, SubmitCalibrationJobResponseSerializer, GetIterationsResponseSerializer, \
    CalibrationJobSlurmCallbackRequestSerializer, ValidationJobSlurmCallbackRequestSerializer, EmptySerializer, \
    GetJobDirResponseSerializer, GetStatusRequestSerializer, GetStatusResponseSerializer, CalibrationOrValidationOrForecastRunSerializer, \
    ForecastJobSlurmCallbackRequestSerializer, \
    ForecastForcingDownloadJobSlurmCallbackRequestSerializer, CancelJobResponseSerializer
from calibration.views import ngen_cal_input
from calibration.views.common import ResponseError, get_calibration_run, handle_exceptions, validate_response, validate_request, \
    generate_custom_token, token_slurm_scope, auth_scope_required, get_validation_run, get_forecast_run
from calibration.views.end_of_job_processing import read_calibration_output

logger = logging.getLogger(__name__)


@extend_schema(
    request=GetStatusRequestSerializer,
    responses={
        200: GetStatusResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Return the status of a calibration job and associated validation and forecast jobs"
)
@api_view(['GET', 'POST'])
@handle_exceptions
def get_status(request: Request) -> Response:
    """
    Retrieves the status of a calibration job, including associated validation and forecast jobs.
    Optionally includes performance metrics based on the request parameters.

    :param request: HTTP request containing calibration run details.
    :return: JSON response with the status and associated job details.
    """
    data = request.data
    logger.debug(f'get_status() request from {request.user.email} - {data}')

    validator, error_return = validate_request(GetStatusRequestSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    include_performance_metrics = validator.get('include_performance_metrics')

    calibration_run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=list(StatusEnum))
    if error_return:
        return error_return

    def get_performance_metrics(performance_metrics):
        """
        Helper function to retrieve selected performance metrics, converting numeric fields to 'K' units.
        """
        if not performance_metrics:
            return {field: None for field in [
                "elapsed_time", "num_cpus", "cpu_time", "max_rss", "max_disk_read", "max_disk_write", "reserved_time", "io_throughput"
            ]}

        # Convert numeric fields to kilobytes
        metrics_dict = model_to_dict(performance_metrics, fields=[
            "elapsed_time", "num_cpus", "cpu_time", "max_rss", "max_disk_read", "max_disk_write", "reserved_time"
        ])
        # Manually add io_throughput since it's a generated field
        metrics_dict["io_throughput"] = performance_metrics.io_throughput

        # Convert relevant fields to 'K' units
        for field in ["max_rss", "max_disk_read", "max_disk_write"]:
            value = metrics_dict.get(field)
            if value is not None:  # Only convert non-null values
                metrics_dict[field] = f"{value:.2f}K"

        # Format io_throughput in 'K/s'
        io_throughput = metrics_dict.get("io_throughput")
        if io_throughput is not None:
            metrics_dict["io_throughput"] = f"{io_throughput:.2f}K/s"

        return metrics_dict

    def should_include_metrics(run_status: Status):
        """
        Determines if performance metrics should be included based on job status and request parameters.
        """
        return include_performance_metrics and run_status in [StatusEnum.DONE.db_instance, StatusEnum.FAILED.db_instance]

    # Conditionally retrieve calibration performance metrics
    calibration_metrics = get_performance_metrics(calibration_run.performance_metrics) if should_include_metrics(calibration_run.status) else None

    # Retrieve validation runs with related PerformanceMetrics data
    validation_runs = ValidationRun.objects.filter(calibration_run=calibration_run).select_related(
        "performance_metrics"
    ).only(
        "id", "status__name", "validation_type", "submit_date",
        "performance_metrics__elapsed_time", "performance_metrics__num_cpus",
        "performance_metrics__cpu_time", "performance_metrics__max_rss",
        "performance_metrics__max_disk_read", "performance_metrics__max_disk_write",
        "performance_metrics__reserved_time"
    )

    # Retrieve forecast runs with related PerformanceMetrics data
    forecast_runs = ForecastRun.objects.filter(calibration_run=calibration_run).select_related(
        "performance_metrics", "forcing_download_run"
    ).only(
        "id", "status__name", "submit_date",
        "performance_metrics__elapsed_time", "performance_metrics__num_cpus",
        "performance_metrics__cpu_time", "performance_metrics__max_rss",
        "performance_metrics__max_disk_read", "performance_metrics__max_disk_write",
        "performance_metrics__reserved_time",
        "forcing_download_run__status__name",
        "forcing_download_run__performance_metrics__elapsed_time",
        "forcing_download_run__performance_metrics__num_cpus",
        "forcing_download_run__performance_metrics__cpu_time",
        "forcing_download_run__performance_metrics__max_rss",
        "forcing_download_run__performance_metrics__max_disk_read",
        "forcing_download_run__performance_metrics__max_disk_write",
        "forcing_download_run__performance_metrics__reserved_time"
    )

    # Construct validation response with performance metrics as needed
    validation_response = []
    for run in validation_runs:
        validation_data = {
            'validation_run_id': run.id,
            'status': run.status.name,
            'validation_type': run.validation_type,
            'iteration_num': run.iteration_num,
            'submit_date': run.submit_date,
            'run_start': run.run_start,
            'run_end': run.run_end,
            'elapsed_time': run.performance_metrics.elapsed_time if run.performance_metrics else None
        }
        if should_include_metrics(run.status):
            validation_data['performance_metrics'] = get_performance_metrics(run.performance_metrics)
        validation_response.append(validation_data)

    # Construct validation response with performance metrics as needed
    forecast_response = []
    for run in forecast_runs:
        forcing_download = run.forcing_download_run
        forecast_data = {
            'forecast_run_id': run.id,
            'status': run.status.name,
            'submit_date': run.submit_date,
            'run_start': run.run_start,
            'run_end': run.run_end,
            'elapsed_time': run.performance_metrics.elapsed_time if run.performance_metrics else None,
            'forcing_download': {
                'forcing_download_run_id': forcing_download.id,
                'status': forcing_download.status.name,
                'elapsed_time': forcing_download.performance_metrics.elapsed_time if forcing_download.performance_metrics else None,
                'performance_metrics': get_performance_metrics(forcing_download.performance_metrics) if should_include_metrics(forcing_download.status) else None
            } if forcing_download else None
        }
        if should_include_metrics(run.status):
            forecast_data['performance_metrics'] = get_performance_metrics(run.performance_metrics)
        forecast_response.append(forecast_data)

    # Prepare the main response without calibration performance metrics if not requested
    response = {
        'message': f'Calibration Job {calibration_run.id}, status is {calibration_run.status.name}',
        'calibration_run_id': calibration_run.id,
        'status': calibration_run.status.name,
        'submit_date': calibration_run.submit_date,
        'run_start': calibration_run.run_start,
        'run_end': calibration_run.run_end,
        'elapsed_time': calibration_run.performance_metrics.elapsed_time if calibration_run.performance_metrics else None,
        'validations': validation_response,
        'forecasts': forecast_response
    }

    # Conditionally add calibration run performance metrics to response if requested and status is DONE or FAIL
    if calibration_metrics:
        response['performance_metrics'] = calibration_metrics

    # Add error messages if applicable
    if calibration_run.status in [StatusEnum.SAVED.db_instance, StatusEnum.RUNNING.db_instance]:
        messages, _ = ngen_cal_input.ready_to_run(calibration_run)
        if messages:
            response['errors'] = messages

    response_validator, error_response = validate_response(GetStatusResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user.email} from get_status() - {response_validator.data}')
    return Response(response_validator.data)


@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: SubmitCalibrationJobResponseSerializer,
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
def run_calibration(request: Request) -> Response:
    """
    Submits a calibration job for processing.

    :param request: HTTP request containing calibration run details.
    :return: JSON response indicating job submission status.
    """
    data = request.data
    logger.debug(f'run_calibration() request from {request.user.email} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_calibration_run(calibration_run_id, request.user)
    if error_return:
        return error_return

    response = submit_job(run)
    if response:
        return response

    response = {'message': f'Calibration Job {run.id} has been submitted', 'calibration_run_id': calibration_run_id,
                'status': run.status.name, 'submit_date': run.submit_date}

    response_validator, error_response = validate_response(SubmitCalibrationJobResponseSerializer, response)
    logger.debug(f'Returning to {request.user.email} from run_calibration() - {response_validator.data}')

    return Response(response_validator.data)


@extend_schema(
    request=CalibrationRunSerializer,
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
    description="Process the output of a calibration run"
)
@api_view(['GET', 'POST'])
@handle_exceptions
def process_calibration_output(request):
    """
    This endpoint is mostly for testing, to kick off the processing of output for a completed job.
    Normally read_calibration_output() is called automatically when a job completes.
    This endpoint can be used in case the output processing doesn't work.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()

    logger.debug(f'process_calibration_output() request from {request.user.email} - {data}')
    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=[StatusEnum.DONE])

    if error_return:
        return error_return

    read_calibration_output(run)

    response = {'message': f"End of job processing completed for Calibration Job {run.id}",
                'calibration_run_id': run.id,
                'status': run.status.name}

    response_validator, error_response = validate_response(GenericResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user.email} from process_calibration_output() - {response_validator.data}')

    return Response(response_validator.data)


@extend_schema(
    request=ReportIterationSerializer,
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
    description="Report iteration of a running calibration"
)
# Called by ngen_cal
@api_view(['POST'])
@handle_exceptions
def report_iteration(request):
    """
    Reports an iteration for a running calibration job. This endpoint updates or creates an
    iteration record for a specific worker in the calibration job.

    :param request: HTTP request containing iteration details.
    :return: JSON response indicating the success of the operation.
    """
    data = request.data
    logger.debug(f'report_iteration() request from {request.user.email} - {data}')

    validator, error_return = validate_request(ReportIterationSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    iteration_number = validator.get('iteration')
    worker_name = validator.get('worker_name')
    first_iteration_for_worker = validator.get('first_iteration_for_worker')

    logger.debug(
        f'Report Iteration for calibration_run_id {calibration_run_id}, iteration number: {iteration_number}, worker: {worker_name}, first_iteration: {first_iteration_for_worker}')

    run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=[StatusEnum.RUNNING])
    if error_return:
        return error_return

    with transaction.atomic():
        if first_iteration_for_worker:
            # New worker
            max_worker_number = Iteration.objects.filter(calibration_run=run).aggregate(Max('worker_number'))['worker_number__max']
            worker_number = (max_worker_number or 0) + 1
            logger.debug(f"Creating new worker: '{worker_name}' #{worker_number}")
        else:
            # Use get() to fetch the latest iteration for the given worker_name and run
            existing_iteration = Iteration.objects.filter(calibration_run=run, worker_name=worker_name).order_by('-iteration_num').first()
            if existing_iteration:
                worker_number = existing_iteration.worker_number
            else:
                return ResponseError(f"Worker '{worker_name}' not found for calibration run {run.id}.")

        iteration_object, created = Iteration.objects.get_or_create(calibration_run=run, iteration_num=iteration_number, worker_name=worker_name,
                                                                    defaults={'worker_number': worker_number})
        if not created:
            return ResponseError(f'Iteration object already exists for calibration run {run.id}, worker {worker_name}, iteration {iteration_number}')

        response = {'message': f"Iteration {iteration_number} for worker_name '{worker_name}' set for Calibration Job {run.id}",
                    'calibration_run_id': run.id,
                    'status': run.status.name}

        response_validator, error_response = validate_response(GenericResponseSerializer, response)
        if error_response:
            return error_response
        logger.debug(f'Returning to {request.user.email} from report_iteration() - {response_validator.data}')

        return Response(response_validator.data)


@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: GetIterationsResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Get iteration of a running calibration"
)
@api_view(['GET', 'POST'])
@handle_exceptions
def get_iteration(request: Request) -> Response:
    """
    Retrieves the current iteration of a running calibration job.

    :param request: HTTP request containing calibration run details.
    :return: JSON response with the current iteration details.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'get_iteration() request from {request.user.email} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    # Allow status Ready for UI polling immediately after submission.
    run, error_return = get_calibration_run(calibration_run_id, request.user,
                                            run_status=[StatusEnum.READY, StatusEnum.RUNNING, StatusEnum.DONE, StatusEnum.FAILED,
                                                        StatusEnum.SERVER_ERROR])
    if error_return:
        return error_return

    high_iteration = Iteration.objects.filter(calibration_run=run, worker_number=1).order_by('-iteration_num').first()
    high_iteration_number = high_iteration.iteration_num if high_iteration else None

    response = {'message': f'Calibration Job {run.id} has completed {high_iteration_number} iterations',
                'calibration_run_id': run.id,
                'status': run.status.name,
                'iteration': high_iteration_number}

    response_validator, error_response = validate_response(GetIterationsResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user.email} from get_iteration() - {response_validator.data}')

    return Response(response_validator.data)


@extend_schema(
    request=CalibrationOrValidationOrForecastRunSerializer,
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
    description="Cancel a running job"
)
@api_view(['GET', 'POST'])
@handle_exceptions
def cancel_job(request: Request) -> Response:
    """
    Cancel a running job for CalibrationRun, ValidationRun, or ForecastRun.

    :param request: The HTTP request containing the run ID to cancel.
    :return: A Response indicating the cancellation result.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'cancel_job() request from {request.user.email} - {data}')

    validator, error_return = validate_request(CalibrationOrValidationOrForecastRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    validation_run_id = validator.get('validation_run_id')
    forecast_run_id = validator.get('forecast_run_id')

    # Determine job type and retrieve the appropriate run instance
    if calibration_run_id:
        run_func = get_calibration_run
        run_id = calibration_run_id
        run_type = JobType.CALIBRATION.value.capitalize()
    elif validation_run_id:
        run_func = get_validation_run
        run_id = validation_run_id
        run_type = JobType.VALIDATION.value.capitalize()
    else:
        run_func = get_forecast_run
        run_id = forecast_run_id
        run_type = JobType.FORECAST.value.capitalize()

    run, error_return = run_func(run_id, request.user, run_status=[StatusEnum.RUNNING])
    if error_return:
        return error_return

    if not cancel_job_common(run):
        return ResponseError(f"Unable to cancel {run_type} Job {run.id}")

    run.status = StatusEnum.CANCELLED.db_instance
    run.save(update_fields=['status'])

    response = {
        'message': f"{run_type} Run job {run.id} has been canceled",
        f"{run_type.lower()}_run_id": run.id,
        'status': run.status.name  # type: ignore[attr-defined]
    }
    response_validator, error_response = validate_response(CancelJobResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user.email} from cancel_job() - {response_validator.data}')

    return Response(response_validator.data)


@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: GetJobDirResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Return the directory where a jobs data is stored"
)
@api_view(['GET', 'POST'])
@handle_exceptions
def get_job_dir(request: Request) -> Response:
    """
    Retrieves the directory path where the data for a specific calibration run is stored.

    :param request: HTTP request containing calibration run details.
    :return: JSON response with the data directory path.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'get_job_dir() request from {request.user.email} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_calibration_run(calibration_run_id, request.user,
                                            run_status=[StatusEnum.DONE, StatusEnum.RUNNING, StatusEnum.FAILED, StatusEnum.SERVER_ERROR])
    if error_return:
        return error_return

    if settings.NGEN_CAL_DATA_PATH and settings.NGEN_CAL_DATA_PATH != settings.NGEN_CAL_MOUNT_POINT:
        # Convert path inside the container to the mapped host pth outside the container
        container_job_data_dir = run.job_data_dir
        # Ensure the absolute path starts with the old root
        if not os.path.isabs(container_job_data_dir):
            raise ValueError(f"The path '{container_job_data_dir}' is not absolute.")
        if not container_job_data_dir.startswith(settings.NGEN_CAL_MOUNT_POINT):
            raise ValueError(f"The path '{container_job_data_dir}' does not start with the old root '{settings.NGEN_CAL_MOUNT_POINT}'.")

        # Replace the old root with the new root
        relative_path = os.path.relpath(container_job_data_dir, start=settings.NGEN_CAL_MOUNT_POINT)
        new_job_data_dir = os.path.join(settings.NGEN_CAL_DATA_PATH, relative_path)
    else:
        new_job_data_dir = run.job_data_dir

    response = {
        'message': f"Calibration Job {run.id} data directory is {new_job_data_dir}",
        'calibration_run_id': run.id,
        'data_dir': new_job_data_dir,
        'status': run.status.name
    }

    response_validator, error_response = validate_response(GetJobDirResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user.email} from get_job_dir() - {response_validator.data}')

    return Response(response_validator.data)


@extend_schema(
    request=CalibrationJobSlurmCallbackRequestSerializer,
    responses={
        202: None,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Callback for Slurm to call when a calibration job ends"
)
@api_view(['POST'])
@handle_exceptions
@auth_scope_required(token_slurm_scope)
def calibration_job_slurm_callback(request: Request) -> Response:
    """
    Handles a callback from Slurm to update the status of a calibration job.

    :param request: HTTP request containing Slurm job details and status.
    :return: HTTP 202 response indicating the callback was processed.
    """
    data = request.data
    logger.debug(f'calibration_job_slurm_callback() request from {request.user.email} - {data}')

    validator, error_return = validate_request(CalibrationJobSlurmCallbackRequestSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    job_status = validator.get('job_status')

    calibration_run, error_return = get_calibration_run(calibration_run_id, request.user, run_status=[StatusEnum.RUNNING])
    if error_return:
        return error_return

    slurm_status = SlurmStatusEnum(job_status)
    run_calibration_job_callback_pw(calibration_run, slurm_status)

    logger.debug(f'Returning to {request.user.email} from calibration_job_slurm_callback()')

    return Response(status=status.HTTP_202_ACCEPTED)


@extend_schema(
    request=ValidationJobSlurmCallbackRequestSerializer,
    responses={
        202: None,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Callback for Slurm to call when a validation job ends"
)
@api_view(['POST'])
@handle_exceptions
@auth_scope_required(token_slurm_scope)
def validation_job_slurm_callback(request: Request) -> Response:
    """
    Handles a callback from Slurm to update the status of a validation job.

    :param request: HTTP request containing Slurm job details and status.
    :return: HTTP 202 response indicating the callback was processed.
    """
    data = request.data
    logger.debug(f'validation_job_slurm_callback() request from {request.user.email} - {data}')

    validator, error_return = validate_request(ValidationJobSlurmCallbackRequestSerializer, data)
    if error_return:
        return error_return

    validation_run_id = validator.get('validation_run_id')
    job_status = validator.get('job_status')

    validation_run, error_return = get_validation_run(validation_run_id, None, run_status=[StatusEnum.RUNNING])
    if error_return:
        return error_return

    slurm_status = SlurmStatusEnum(job_status)
    run_validation_job_callback_pw(validation_run, slurm_status)

    logger.debug(f'Returning to {request.user.email} from validation_job_slurm_callback()')

    return Response(status=status.HTTP_202_ACCEPTED)


@extend_schema(
    request=ForecastJobSlurmCallbackRequestSerializer,
    responses={
        202: None,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Callback for Slurm to call when a forecast job ends"
)
@api_view(['POST'])
@handle_exceptions
@auth_scope_required(token_slurm_scope)
def forecast_job_slurm_callback(request: Request) -> Response:
    """
    Handles a callback from Slurm to update the status of a forecast job.

    :param request: HTTP request containing Slurm job details and status.
    :return: HTTP 202 response indicating the callback was processed.
    """
    data = request.data
    logger.debug(f'forecast_job_slurm_callback() request from {request.user.email} - {data}')

    validator, error_return = validate_request(ForecastJobSlurmCallbackRequestSerializer, data)
    if error_return:
        return error_return

    forecast_run_id = validator.get('forecast_run_id')
    job_status = validator.get('job_status')

    forecast_run, error_return = get_forecast_run(forecast_run_id, None, run_status=[StatusEnum.RUNNING])
    if error_return:
        return error_return

    slurm_status = SlurmStatusEnum(job_status)
    run_forecast_job_callback_pw(forecast_run, slurm_status)

    logger.debug(f'Returning to {request.user.email} from forecast_job_slurm_callback()')

    return Response(status=status.HTTP_202_ACCEPTED)


@extend_schema(
    request=ForecastForcingDownloadJobSlurmCallbackRequestSerializer,
    responses={
        202: None,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Callback for Slurm to call when a forecast forcing download job ends"
)
@api_view(['POST'])
@handle_exceptions
@auth_scope_required(token_slurm_scope)
def forecast_forcing_download_job_slurm_callback(request: Request) -> Response:
    """
    Handles a callback from Slurm to update the status of a forecast forcing download job.

    :param request: HTTP request containing Slurm job details and status.
    :return: HTTP 202 response indicating the callback was processed.
    """
    data = request.data
    logger.debug(f'forecast_forcing_download_job_slurm_callback() request from {request.user.email} - {data}')

    validator, error_return = validate_request(ForecastForcingDownloadJobSlurmCallbackRequestSerializer, data)
    if error_return:
        return error_return

    forecast_forcing_download_run_id = validator.get('forecast_forcing_download_run_id')
    job_status = validator.get('job_status')

    forecast_forcing_download_run, error_return = get_forecast_run(forecast_forcing_download_run_id, None, run_status=[StatusEnum.RUNNING])
    if error_return:
        return error_return

    slurm_status = SlurmStatusEnum(job_status)
    run_forecast_forcing_download_job_callback_pw(forecast_forcing_download_run, slurm_status)

    logger.debug(f'Returning to {request.user.email} from forecast_forcing_download_job_slurm_callback()')

    return Response(status=status.HTTP_202_ACCEPTED)


@extend_schema(
    request=EmptySerializer,
    responses={
        200: OpenApiResponse(
            response=OpenApiTypes.OBJECT,  # Indicates the response is an object
            description="Success",
            examples=[
                OpenApiExample(
                    'Example response',
                    value={'access': 'your_access_token_here'}
                )
            ],  # Defines the example using OpenApiExample
        ),
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Return a token for use by Slurm"
)
@api_view(['GET'])
@handle_exceptions
def get_slurm_token(request: Request) -> Response:
    """
    Generates and returns a token for use by Slurm.

    :param request: HTTP request.
    :return: JSON response containing the generated token.
    """
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'get_slurm_token() request from {request.user.email} - {data}')

    validator, error_return = validate_request(EmptySerializer, data)
    if error_return:
        return error_return

    return Response({'access': generate_custom_token(request.user, token_slurm_scope)})


def subset_directory_by_time_range(input_directory, output_directory, date_time_range: DateTimeRange):
    """
    Subsets the files in a directory based on a provided time range and saves the filtered
    files into an output directory.

    :param input_directory: Path to the input directory.
    :param output_directory: Path to the output directory.
    :param date_time_range: DateTimeRange object specifying the time range for filtering.
    """
    logger.info(f'Subsetting directory {input_directory}')

    if not os.path.isdir(output_directory):
        os.makedirs(output_directory, exist_ok=True)

    for filename in os.listdir(input_directory):
        input_file_path = os.path.join(input_directory, filename)
        output_file_path = os.path.join(output_directory, filename)

        if os.path.isfile(input_file_path):  # Ensure it's a file
            subset_by_time_range(input_file_path, output_file_path, date_time_range)

    logger.info(f'Done subsetting directory {input_directory}')


def subset_by_time_range(input_file, output_file, date_time_range: DateTimeRange):
    """
    Reads a CSV file, filters rows based on a time range, and writes the filtered data
    to an output file with the original column names and timezone-naive datetime values.

    :param input_file: Path to the input CSV file.
    :param output_file: Path to the output CSV file.
    :param date_time_range: DateTimeRange object specifying the time range for filtering.
    """
    logger.info(f'Subsetting file {input_file} to {output_file} with date range {date_time_range}')

    # Ensure the output directory exists
    output_dir = os.path.dirname(output_file)
    os.makedirs(output_dir, exist_ok=True)

    # Read the CSV into a DataFrame, parsing dates in the first column
    df = pd.read_csv(input_file, delimiter=',', parse_dates=[0])

    # Get the original first column name
    original_time_column = df.columns[0]

    # Dynamically rename the first column to a consistent name
    df.rename(columns={original_time_column: 'dateTime'}, inplace=True)

    # Localize datetime column to UTC to make it timezone-aware for comparison
    df['dateTime'] = df['dateTime'].dt.tz_localize('UTC')

    # Log the original start and end ranges in the file
    original_start = df['dateTime'].min()
    original_end = df['dateTime'].max()
    logger.info(f'File {input_file} original date range: {original_start} - {original_end}')

    # Efficiently filter rows using DataFrame.loc and create a copy to avoid warnings
    subset_df = df.loc[
        (df['dateTime'] >= date_time_range.start_datetime) &
        (df['dateTime'] <= date_time_range.end_datetime)
    ].copy()  # Explicitly create a copy

    # Convert timezone-aware datetime column to naive timestamps
    subset_df['dateTime'] = subset_df['dateTime'].dt.tz_convert(None)

    # Rename the datetime column back to its original name
    subset_df.rename(columns={'dateTime': original_time_column}, inplace=True)

    # Write the filtered DataFrame to the output CSV file
    subset_df.to_csv(output_file, index=False)
