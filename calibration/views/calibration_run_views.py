import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from createInput import create_input
from datetimerange import DateTimeRange
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Max
from drf_spectacular.utils import extend_schema, OpenApiResponse
from git import Repo
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.enums import StatusEnum, OptimizationEnum
from calibration.models import Iteration
from calibration.util.calibration_validators import CalibrationRunSerializer, IsReadyResponseSerializer, GenericResponseSerializer, \
    ErrorResponseSerializer, ReportIterationSerializer, SubmitJobResponseSerializer, GetIterationsResponseSerializer, ProcessCalibrationOutputRequest
from calibration.views import ngen_cal_input
from calibration.views.common import ResponseError, get_run, handle_exceptions, validate_response, validate_request
from calibration.views.read_output import read_output, accumulate_iterations
from cerfServer.settings import NGEN_REPO_ROOT, NGEN_CAL_REPO_ROOT
from run_ngen_cal.run_ngen_cal import run_job, JobStage, cancel_local_job
from run_ngen_cal.run_ngen_cal_docker import run_job_callback_slurm

logger = logging.getLogger(__name__)


@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: IsReadyResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: ErrorResponseSerializer
    },
    description="Check if a job is ready to run"
)
@api_view(['GET', 'POST'])
# @permission_classes([AllowAny])()
@handle_exceptions
def is_ready(request):
    data = request.data
    logger.debug(f'is_ready() request from {request.user} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_run(calibration_run_id, request.user)
    if error_return:
        return error_return

    messages, _ = ngen_cal_input.ready_to_run(run)

    response = {'calibration_run_id': run.id, 'status': run.status.name}
    ready_not_ready = 'not ready' if messages else 'ready'
    response['message'] = f'Calibration Run {run.id} is {ready_not_ready}'
    if messages:
        response['errors'] = messages

    response_validator, error_response = validate_response(IsReadyResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user} from is_ready() - {response_validator.data}')
    return Response(response_validator.data)


@extend_schema(
    request=None,
    responses={
        200: GenericResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: ErrorResponseSerializer
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
        print(f'Running create_input for Calibration Run {run.id}')
        create_input(config_file)
    except Exception as e:
        return ResponseError(f'Exception from create_input - {str(e)}')

    print(f'Return from create_input for Calibration Run {run.id}')

    if not Path(NGEN_REPO_ROOT).exists():
        # Save the latest git hash or ngen and ngen-cal
        run.ngen_commit_hash = Repo(NGEN_REPO_ROOT).head.object.hexsha
        run.ngen_cal_commit_hash = Repo(NGEN_CAL_REPO_ROOT).head.object.hexsha

    run.run_date = datetime.now(timezone.utc)
    run.status = StatusEnum.from_enum(StatusEnum.RUNNING)
    run.save()

    run_job(run, JobStage.CALIBRATION)

    return None


@extend_schema(
    request=ProcessCalibrationOutputRequest,
    responses={
        200: ProcessCalibrationOutputRequest,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: ErrorResponseSerializer
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
     It does not hurt to run this endpoint more than once.
     The 'rerun' option will delete any Iteration and related objects and re-create them
    """
    data = request.data if request.method == 'POST' else request.query_params

    logger.debug(f'process_calibration_output() request from {request.user} - {data}')
    validator, error_return = validate_request(ProcessCalibrationOutputRequest, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    rerun = validator.get('rerun')

    run, error_return = get_run(calibration_run_id, request.user, run_status=[StatusEnum.DONE])

    if error_return:
        return error_return

    iteration_objects = Iteration.objects.filter(calibration_run=run)
    if iteration_objects.exists():
        if rerun:
            iteration_objects.delete()
        else:
            return ResponseError(f"End of job processing has already been completed Calibration Run {run.id}")

    # If we have a repeat option then iteration_objects.delete()

    read_output(run)

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
        500: ErrorResponseSerializer
    },
    description="Report iteration of a running calibration"
)
# Called by ngen_cal
@api_view(['POST'])
# @permission_classes([AllowAny])
@handle_exceptions
def report_iteration(request):
    data = request.data
    logger.debug(f'report_iteration() request from {request.user} - {data}')

    validator, error_return = validate_request(ReportIterationSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')
    optimization = validator.get('optimization')
    iteration_number = validator.get('iteration')
    worker_name = validator.get('worker_name')

    starting_iteration = 0 if optimization == OptimizationEnum.DDS.value else 1

    run, error_return = get_run(calibration_run_id, request.user, run_status=[StatusEnum.SAVED, StatusEnum.READY])
    # run, error_return = get_run(calibration_run_id, request.user, run_status=[StatusEnum.RUNNING])
    if error_return:
        return error_return

    with transaction.atomic():
        if iteration_number == starting_iteration:
            # New worker_name, get a new worker_number
            max_worker_number = Iteration.objects.filter(calibration_run=run).aggregate(Max('worker_number'))['worker_number__max']
            worker_number = (max_worker_number or 0) + 1
        else:
            # Existing worker, find the worker_number
            existing_iteration = Iteration.objects.filter(calibration_run=run, worker_name=worker_name).order_by('-iteration_num').first()
            if existing_iteration:
                worker_number = existing_iteration.worker_number
            else:
                # Handle case where worker_name does not exist
                return ResponseError(f"Worker '{worker_name}' not found in calibration run {run.id}.")

        if Iteration.objects.filter(calibration_run=run, iteration_num=iteration_number, worker_name=worker_name).exists():
            return ResponseError(f'Iteration object already exists for calibration run {run.id}, worker {worker_name}, iteration {iteration_number}')

        Iteration.objects.create(calibration_run=run, iteration_num=iteration_number, worker_name=worker_name, worker_number=worker_number)
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
        500: ErrorResponseSerializer
    },
    description="Get iteration of a running calibration"
)
@api_view(['GET', 'POST'])
@handle_exceptions
def get_iteration(request):
    data = request.data if request.method == 'POST' else request.query_params
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
        500: ErrorResponseSerializer
    },
    description="Cancel a running job"
)
@api_view(['GET', 'POST'])
@handle_exceptions
def cancel_job(request):
    data = request.data if request.method == 'POST' else request.query_params
    logger.debug(f'cancel_job() request from {request.user} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_run(calibration_run_id, request.user, run_status=[StatusEnum.RUNNING])
    if error_return:
        return error_return

    if not cancel_local_job(run.id):
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
    request=CalibrationRunSerializer,
    responses={
        200: GenericResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: ErrorResponseSerializer
    },
    description="Cancel a running job"
)
@api_view(['POST'])
@handle_exceptions
def slurm_callback(request):
    data = request.data
    logger.debug(f'slurm_callback() request from {request.user} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
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

    run_job_callback_slurm(current_stage, process_id, job_status)

    logger.debug(f'Returning to {request.user} from slurm_callback()')

    return Response(status=status.HTTP_202_ACCEPTED)


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
