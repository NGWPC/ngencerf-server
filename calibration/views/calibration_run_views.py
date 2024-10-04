import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from createInput import create_input
from datetimerange import DateTimeRange
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Max
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiExample
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.enums import StatusEnum
from calibration.models import Iteration
from calibration.run_util.run_common import run_calibration_job, cancel_job_common, JobStage
from calibration.run_util.run_ngen_cal_pw import run_calibration_job_callback_slurm, SlurmStatusEnum
from calibration.util.calibration_validators import CalibrationRunSerializer, IsReadyResponseSerializer, GenericResponseSerializer, \
    ErrorResponseSerializer, ReportIterationSerializer, SubmitJobResponseSerializer, GetIterationsResponseSerializer, SlurmCallbackRequestSerializer, \
    ReadOutputRequestSerializer
from calibration.views import ngen_cal_input
from calibration.views.common import ResponseError, get_run, handle_exceptions, validate_response, validate_request, generate_custom_token, \
    token_slurm_scope, auth_scope_required
from calibration.views.read_output import read_output, accumulate_iterations

logger = logging.getLogger(__name__)


@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: IsReadyResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal server error"
        )
    },
    description="Return the status of a job"
)
@api_view(['GET', 'POST'])
# @permission_classes([AllowAny])()
@handle_exceptions
def get_status(request):
    data = request.data
    logger.debug(f'get_status() request from {request.user} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_run(calibration_run_id, request.user, list(StatusEnum))
    if error_return:
        return error_return

    messages = None
    if run.status in [StatusEnum.from_enum(StatusEnum.SAVED), StatusEnum.from_enum(StatusEnum.READY)]:
        messages, _ = ngen_cal_input.ready_to_run(run)

    response = {'message': f'Calibration Run {run.id}, status is {run.status.name}', 'calibration_run_id': run.id, 'status': run.status.name}
    if messages:
        response['errors'] = messages

    response_validator, error_response = validate_response(IsReadyResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user} from get_status() - {response_validator.data}')
    return Response(response_validator.data)


@extend_schema(
    request=None,
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
    description="Run a calibration"
)
@api_view(['POST'])
@handle_exceptions
def run_calibration(request):
    data = request.data
    logger.debug(f'run_calibration() request from {request.user} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_run(calibration_run_id, request.user)
    if error_return:
        return error_return

    # TODO Need to Catch exception from Slurm
    response = submit_job(run)
    if response:
        return response

    response = {'message': f'Calibration Run {run.id} has been submitted', 'calibration_run_id': calibration_run_id,
                'status': run.status.name, 'run_date': run.run_date}

    response_validator, error_response = validate_response(SubmitJobResponseSerializer, response)
    logger.debug(f'Returning to {request.user} from run_calibration() - {response_validator.data}')

    return Response(response_validator.data)


def submit_job(run, config_file=None):
    # If config is passed, then don't need to validate
    if not config_file:
        messages, config_file = ngen_cal_input.ready_to_run(run, build=True)

        if messages:
            return ResponseError(f'Calibration Run {run.id} is not ready', validation_errors=messages)

    try:
        logger.info(f'Running create_input for Calibration Run {run.id}')
        create_input(config_file)
    except Exception as e:
        return ResponseError(f'Exception from create_input - {str(e)}')

    logger.info(f'Return from create_input for Calibration Run {run.id}')

    # Need to return the commit hash as part of the Slurm job
    # Save the latest git hash or ngen and ngen-cal
    # run.ngen_commit_hash = Repo(settings.NGEN_REPO_ROOT).head.object.hexsha
    # run.ngen_cal_commit_hash = Repo(settings.NGEN_CAL_REPO_ROOT).head.object.hexsha

    run.run_date = datetime.now(timezone.utc)
    run.status = StatusEnum.from_enum(StatusEnum.RUNNING)
    run.save()

    run_calibration_job(run, JobStage.CALIBRATION)

    return None


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

    logger.debug(f'process_calibration_output() request from {request.user} - {data}')
    validator, error_return = validate_request(ReadOutputRequestSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    job_stage = validator.get('job_stage')

    run, error_return = get_run(calibration_run_id, request.user, run_status=[StatusEnum.DONE])

    if error_return:
        return error_return

    read_output(run, JobStage.from_string(job_stage))

    response = {'message': f"End of job processing completed for Calibration Run {run.id}",
                'calibration_run_id': run.id,
                'status': run.status.name}

    response_validator, error_response = validate_response(GenericResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user} from process_calibration_output() - {response_validator.data}')

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
    logger.debug(f'report_iteration() request from {request.user} - {data}')

    validator, error_return = validate_request(ReportIterationSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    iteration_number = validator.get('iteration')
    worker_name = validator.get('worker_name')
    first_iteration_for_worker = validator.get('first_iteration_for_worker')

    logger.debug(
        f'Report Iteration for calibration_run_id {calibration_run_id}, iteration number: {iteration_number}, worker: {worker_name}, first_iteration: {first_iteration_for_worker}')

    # TODO Only Running
    # run, error_return = get_run(calibration_run_id, request.user, run_status=[StatusEnum.SAVED, StatusEnum.RUNNING])
    run, error_return = get_run(calibration_run_id, request.user, run_status=[StatusEnum.RUNNING])
    if error_return:
        return error_return

    with transaction.atomic():
        if first_iteration_for_worker:
            # New worker
            max_worker_number = Iteration.objects.filter(calibration_run=run).aggregate(Max('worker_number'))['worker_number__max']
            worker_number = (max_worker_number or 0) + 1
            print(f"Creating new worker: '{worker_name}' #{worker_number}")
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
        logger.debug(f'Returning to {request.user} from report_iteration() - {response_validator.data}')

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
    logger.debug(f'get_iteration() request from {request.user} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_run(calibration_run_id, request.user, run_status=[StatusEnum.RUNNING, StatusEnum.DONE, StatusEnum.FAILED])
    if error_return:
        return error_return

    # Use accumulate_iterations to get the total iterations
    total_iterations = accumulate_iterations(run)

    response = {'message': f'Iterations so far for Calibration Run {run.id}, across all workers, is {total_iterations}', 'calibration_run_id': run.id,
                'status': run.status.name, 'iterations': total_iterations}

    response_validator, error_response = validate_response(GetIterationsResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user} from get_iteration() - {response_validator.data}')

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
    description="Cancel a running job"
)
@api_view(['GET', 'POST'])
@handle_exceptions
def cancel_job(request):
    data = request.data if request.method == 'POST' else request.query_params.dict()
    logger.debug(f'cancel_job() request from {request.user} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_run(calibration_run_id, request.user, run_status=[StatusEnum.RUNNING])
    if error_return:
        return error_return

    if not cancel_job_common(run):
        return ResponseError(f"Calibration Run {run.id} is not running")
    else:
        run.status = StatusEnum.from_enum(StatusEnum.CANCELLED)
        run.save(update_fields=['status'])

    response = {'message': f'Calibration Run job {run.id} has been canceled', 'calibration_run_id': run.id,
                'status': run.status.name}  # type: ignore[attr-defined]

    response_validator, error_response = validate_response(GenericResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user} from cancel_job() - {response_validator.data}')

    return Response(response_validator.data)


@extend_schema(
    request=SlurmCallbackRequestSerializer,
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
    description="Callback for slurm to call when a job ends"
)
@api_view(['POST'])
@handle_exceptions
@auth_scope_required(token_slurm_scope)
def slurm_callback(request):
    data = request.data
    logger.debug(f'slurm_callback() request from {request.user} - {data}')

    validator, error_return = validate_request(SlurmCallbackRequestSerializer, data)
    if error_return:
        return error_return

    process_id = validator.get('process_id')
    current_stage = validator.get('stage')
    job_status = validator.get('job_status')

    calibration_run_id, owner_name = process_id.split('_')
    owner = get_user_model().objects.get(username=owner_name)

    run, error_return = get_run(calibration_run_id, owner, run_status=[StatusEnum.RUNNING])
    if error_return:
        return error_return

    slurm_status = SlurmStatusEnum[job_status]
    run_calibration_job_callback_slurm(JobStage[current_stage], process_id, run, slurm_status)

    logger.debug(f'Returning to {request.user} from slurm_callback()')

    return Response(status=status.HTTP_202_ACCEPTED)


@extend_schema(
    request=None,
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
    return Response({'access': generate_custom_token(request.user, token_slurm_scope)})


def subset_directory_by_time_range(input_directory, output_directory, date_time_range: DateTimeRange):
    logger.info(f'Subsetting directory {input_directory}')

    if not Path(output_directory).is_dir():
        Path(output_directory).mkdir(parents=True, exist_ok=True)

    for filename in Path(input_directory).iterdir():
        input_file_path = Path(input_directory) / filename
        output_file_path = Path(output_directory) / filename

        if input_file_path.is_file():  # Ensure it's a file
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
