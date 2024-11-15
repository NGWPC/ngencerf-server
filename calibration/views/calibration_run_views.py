import logging
import os

import pandas as pd
from datetimerange import DateTimeRange
from django.db import transaction
from django.db.models import Max
from django.forms import model_to_dict
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiExample
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.enums import StatusEnum
from calibration.models import Iteration, ValidationRun
from calibration.run_util.run_common import cancel_job_common, submit_calibration_job
from calibration.run_util.run_ngen_cal_pw import run_calibration_job_callback_slurm, SlurmStatusEnum, run_validation_job_callback_slurm
from calibration.util.calibration_validators import CalibrationRunSerializer, GenericResponseSerializer, \
    ErrorResponseSerializer, ReportIterationSerializer, SubmitCalibrationJobResponseSerializer, GetIterationsResponseSerializer, \
    CalibrationJobSlurmCallbackRequestSerializer, ValidationJobSlurmCallbackRequestSerializer, CalibrationOrValidationRunSerializer, EmptySerializer, \
    GetJobDirResponseSerializer, GetStatusRequestSerializer, GetStatusResponseSerializer, GenericResponseSerializerWithValidation
from calibration.views import ngen_cal_input
from calibration.views.common import ResponseError, get_calibration_run, handle_exceptions, validate_response, validate_request, \
    generate_custom_token, token_slurm_scope, auth_scope_required, get_validation_run
from calibration.views.read_output import read_calibration_output

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
    description="Return the status of a calibration job and associated validation jobs"
)
@api_view(['GET', 'POST'])
@handle_exceptions
def get_status(request):
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

    # Helper function to retrieve performance metrics if available
    def get_performance_metrics(performance_metrics):
        fields = ["elapsed_time", "num_cpus", "cpu_time", "max_rss", "max_disk_read", "max_disk_write", "reserved_time"]
        return model_to_dict(performance_metrics, fields=fields) if performance_metrics else {field: None for field in fields}

    # Check if the job's status allows retrieving performance metrics
    def should_include_metrics(status):
        return include_performance_metrics and status in [StatusEnum.from_enum(StatusEnum.DONE), StatusEnum.from_enum(StatusEnum.FAILED)]

    # Conditionally retrieve calibration performance metrics
    calibration_metrics = get_performance_metrics(calibration_run.performance_metrics) if should_include_metrics(calibration_run.status) else None

    # Retrieve validation runs with related PerformanceMetrics data
    validation_runs = ValidationRun.objects.filter(calibration_run=calibration_run).select_related(
        "performance_metrics"
    ).only(
        "id", "status__name", "validation_type", "run_date",
        "performance_metrics__elapsed_time", "performance_metrics__num_cpus",
        "performance_metrics__cpu_time", "performance_metrics__max_rss",
        "performance_metrics__max_disk_read", "performance_metrics__max_disk_write",
        "performance_metrics__reserved_time"
    )

    # Construct validation response with performance metrics as needed
    validation_response = []
    for run in validation_runs:
        validation_data = {
            'validation_run_id': run.id,
            'status': run.status.name,
            'validation_type': run.validation_type,
            'run_date': run.run_date,
            'run_end': run.run_end,
            'elapsed_time': run.performance_metrics.elapsed_time if run.performance_metrics else None
        }
        if should_include_metrics(run.status):
            validation_data['performance_metrics'] = get_performance_metrics(run.performance_metrics)
        validation_response.append(validation_data)

    # Prepare the main response without calibration performance metrics if not requested
    response = {
        'message': f'Calibration Run {calibration_run.id}, status is {calibration_run.status.name}',
        'calibration_run_id': calibration_run.id,
        'status': calibration_run.status.name,
        'run_date': calibration_run.run_date,
        'run_end': calibration_run.run_end,
        'elapsed_time': calibration_run.performance_metrics.elapsed_time if calibration_run.performance_metrics else None,
        'validations': validation_response
    }

    # Conditionally add calibration run performance metrics to response if requested and status is DONE or FAIL
    if calibration_metrics:
        response['performance_metrics'] = calibration_metrics

    # Add error messages if applicable
    if calibration_run.status in [StatusEnum.from_enum(StatusEnum.SAVED), StatusEnum.from_enum(StatusEnum.READY)]:
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
def run_calibration(request):
    data = request.data
    logger.debug(f'run_calibration() request from {request.user.email} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_calibration_run(calibration_run_id, request.user)
    if error_return:
        return error_return

    response = submit_calibration_job(run)
    if response:
        return response

    response = {'message': f'Calibration Run {run.id} has been submitted', 'calibration_run_id': calibration_run_id,
                'status': run.status.name, 'run_date': run.run_date}

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
     This endpoint is mostly for testing, to kick of the processing of output for a completed job
     Normally read_output() is called automatically when a job completes.
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

    response = {'message': f"End of job processing completed for Calibration Run {run.id}",
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

        response = {'message': f"Iteration {iteration_number} for worker_name '{worker_name}' set for Calibration Run {run.id}",
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
def get_iteration(request):
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'get_iteration() request from {request.user.email} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    # We allow the Ready status since when a job is submitted, it doesn't go to Running right away.  This allows the UI to poll
    run, error_return = get_calibration_run(calibration_run_id, request.user,
                                            run_status=[StatusEnum.READY, StatusEnum.RUNNING, StatusEnum.DONE, StatusEnum.FAILED,
                                                        StatusEnum.SERVER_ERROR])
    if error_return:
        return error_return

    high_iteration = Iteration.objects.filter(calibration_run=run, worker_number=1).order_by('-iteration_num').first()
    high_iteration_number = high_iteration.iteration_num if high_iteration else None

    response = {'message': f'Calibration Run {run.id} has completed {high_iteration_number} iterations',
                'calibration_run_id': run.id,
                'status': run.status.name,
                'iteration': high_iteration_number}

    response_validator, error_response = validate_response(GetIterationsResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user.email} from get_iteration() - {response_validator.data}')

    return Response(response_validator.data)


@extend_schema(
    request=CalibrationOrValidationRunSerializer,
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
def cancel_job(request):
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'cancel_job() request from {request.user.email} - {data}')

    validator, error_return = validate_request(CalibrationOrValidationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    validation_run_id = validator.get('validation_run_id')

    # Determine job type and run function
    run_func = get_calibration_run if calibration_run_id else get_validation_run
    run_id = calibration_run_id or validation_run_id

    run, error_return = run_func(run_id, request.user, run_status=[StatusEnum.RUNNING])
    if error_return:
        return error_return

    if not cancel_job_common(run):
        return ResponseError(f"{'Calibration' if calibration_run_id else 'Validation'} Run {run.id} is not running")

    run.status = StatusEnum.from_enum(StatusEnum.CANCELLED)
    run.save(update_fields=['status'])

    response = {
        'message': f"{'Calibration' if calibration_run_id else 'Validation'} Run job {run.id} has been canceled",
        f"{'calibration_run_id' if calibration_run_id else 'validation_run_id'}": run.id,
        'status': run.status.name  # type: ignore[attr-defined]
    }
    response_validator, error_response = validate_response(GenericResponseSerializerWithValidation, response)
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
def get_job_dir(request):
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'cancel_job() request from {request.user.email} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_calibration_run(calibration_run_id, request.user,
                                            run_status=[StatusEnum.DONE, StatusEnum.RUNNING, StatusEnum.FAILED, StatusEnum.SERVER_ERROR])
    if error_return:
        return error_return

    response = {
        'message': f"Calibration Run job {run.id} data directory is {run.job_data_dir}",
        'calibration_run_id': run.id,
        'data_dir': run.job_data_dir,
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
    description="Callback for slurm to call when a calibration job ends"
)
@api_view(['POST'])
@handle_exceptions
@auth_scope_required(token_slurm_scope)
def calibration_job_slurm_callback(request):
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
    run_calibration_job_callback_slurm(calibration_run, slurm_status)

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
    description="Callback for slurm to call when a validation job ends"
)
@api_view(['POST'])
@handle_exceptions
@auth_scope_required(token_slurm_scope)
def validation_job_slurm_callback(request):
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
    run_validation_job_callback_slurm(validation_run, slurm_status)

    logger.debug(f'Returning to {request.user.email} from validation_job_slurm_callback()')

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
    description="Return a token for use by slurm"
)
@api_view(['GET'])
@handle_exceptions
def get_slurm_token(request):
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'get_slurm_token() request from {request.user.email} - {data}')

    validator, error_return = validate_request(EmptySerializer, data)
    if error_return:
        return error_return

    return Response({'access': generate_custom_token(request.user, token_slurm_scope)})


def subset_directory_by_time_range(input_directory, output_directory, date_time_range: DateTimeRange):
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
    logger.info(f'Subsetting file {input_file} to {output_file}')

    # Read the CSV into a DataFrame, parsing dates in the first column
    df = pd.read_csv(input_file, delimiter=',', parse_dates=[0], infer_datetime_format=True)

    df['dateTime'] = df['dateTime'].dt.tz_localize('UTC')

    # Efficiently filter rows using DataFrame.loc
    subset_df = df.loc[
        (df['dateTime'] >= date_time_range.start_datetime) &
        (df['dateTime'] <= date_time_range.end_datetime)
        ]

    # Write the filtered DataFrame to the output CSV file
    subset_df.to_csv(output_file, index=False)
