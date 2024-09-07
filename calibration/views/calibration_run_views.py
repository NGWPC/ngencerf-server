import csv
import logging
import os
from datetime import datetime, timezone
from itertools import groupby
from operator import attrgetter
from typing import Dict

import pandas as pd
from createInput import create_input
from datetimerange import DateTimeRange
from django.db import transaction
from django.db.models import Max
from drf_spectacular.utils import extend_schema, OpenApiResponse
from git import Repo
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.enums import StatusEnum, OptimizationEnum
from calibration.models import Metric, IterationMetric, Iteration, IterationParameter, \
    CalibrationParameter
from calibration.util.calibration_validators import CalibrationRunSerializer, IsReadyResponseSerializer, GenericResponseSerializer, \
    ErrorResponseSerializer, ReportIterationSerializer
from calibration.util.ngen_locations import get_gage_dir
from calibration.views import ngen_cal_input
from calibration.views.common import ResponseError, get_run, handle_exceptions, validate_request, validate_response, CerfException
from calibration.views.run_ngen_cal import run_job, CalibOrValid
from cerfServer.settings import NGEN_REPO_ROOT, NGEN_CAL_REPO_ROOT

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

    calibration_run_id = validator.data.get('calibration_run_id')

    run, errorReturn = get_run(calibration_run_id, request.user)
    if errorReturn:
        return errorReturn

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

    calibration_run_id = validator.data.get('calibration_run_id')

    run, errorReturn = get_run(calibration_run_id, request.user)
    if errorReturn:
        return errorReturn

    response = submit_job(run)
    if response:
        return response

    response = {'message': f'Calibration Run {run.id} has been submitted', 'calibration_run_id': calibration_run_id,
                'status': run.status.name}

    response_validator, error_response = validate_response(GenericResponseSerializer, response)
    logger.debug(f'Returning to {request.user} from run_calibration() - {response_validator.data}')

    return Response(response_validator.data)


def submit_job(run, config_file=None):
    # If config is passed, then don't need to validate
    if not config_file:
        messages, config_file = ngen_cal_input.ready_to_run(run, build=True)

        if messages:
            return ResponseError(f'Calibration Run {run.id} is not ready', validation_errors=messages)

    # Save the latest git hash or ngen and ngen-cal
    run.ngen_commit_hash = Repo(NGEN_REPO_ROOT).head.object.hexsha
    run.ngen_cal_commit_hash = Repo(NGEN_CAL_REPO_ROOT).head.object.hexsha
    run.run_date = datetime.now(timezone.utc)
    run.save()

    try:
        create_input(config_file)
    except Exception as e:
        return ResponseError(f'Exception from create_input - {str(e)}')

    run_job(run, CalibOrValid.CALIBRATION)

    return None


# This is just a test endpoint to trigger read_output()
@api_view(['GET', 'POST'])
@handle_exceptions
def test_read_output(request):
    data = request.data if request.method == 'POST' else request.query_params
    calibration_run_id = data.get('calibration_run_id')
    # optimization_name = data.get('optimization')
    # username = data.get('user')

    # TODO This should only be for DONE jobs
    # run, errorReturn = get_run(calibration_run_id, request.user, status=[StatusEnum.DONE])
    run, errorReturn = get_run(calibration_run_id, request.user)
    print('run', run)

    if errorReturn:
        return errorReturn
    # if not run:
    #     # create some dummies
    #     gage = Gage(gage_id='01123000')
    #     optimization = Optimization(name=optimization_name)
    #     owner = get_user_model()(username=username)
    #     objective_function = Metric(name='kge')
    #     run = CalibrationRun(optimization=optimization, ngen_formulation_name='cfe_noah', gage=gage,
    #                          objective_function=objective_function, owner=owner)

    # .
    # └── ngen-cal-work
    #     ├── bmi_config
    #     │   └── Noah-OWP
    #     ├── parquet
    #     └── run_calib                      NGEN_CAL_RUN_DIR
    #         ├── 100_peterx
    #         │   └── kge_dds
    #         │       └── cfe_noah
    #         │           └── 01123000
    #         ├── 101_peterx
    #         │   └── kge_gwo
    #         │       └── cfe_noah
    #         │           └── 01123000
    #         └── 102_peterx
    #             └── kge_pso
    #                 └── cfe_noah
    #                     └── 01123000

    gage_dir = get_gage_dir(run)
    print("gage_dir", gage_dir)

    read_output(gage_dir, run)

    return Response(data={'calibration_run_id': calibration_run_id})


# This is not an endpoint, but will be automatically called
# when we get a notification (somehow) that a run has completed
def read_output(gage_dir, run):
    print('Reading output from', gage_dir)

    if not os.path.isdir(gage_dir):
        raise Exception(f'Directory {gage_dir} does not exist or is not a directory')

    output_calibration_run_dir = os.path.join(gage_dir, 'Output/Calibration_Run')

    # TODO Read best params for GWO and PSO
    global_best_params_list = {}
    if run.optimization.name != 'DDS':
        global_best_params_file = os.path.join(output_calibration_run_dir, f'{run.gage.gage_id}_global_best_params.csv')
        if not os.path.exists(global_best_params_file):
            raise CerfException(f"{global_best_params_file} does not exist")
        # For non-DDS, we get the best parameters
        with open(global_best_params_file) as global_best_params:
            next(global_best_params)  # Skip header
            global_best_params_list = list(csv.DictReader(global_best_params, fieldnames=['value', 'name', 'model']))
    print('global_best_params', global_best_params_list)

    realization_filename = f'{run.gage.gage_id}_realization_config_bmi_calib.json'
    run.realization_filename = realization_filename

    with transaction.atomic():
        run.save()
        process_workers(run, output_calibration_run_dir, global_best_params_list)


def process_workers(run, output_calibration_run_dir, global_best_params_list):
    # Query all Iteration objects for the given calibration_run
    iterations = Iteration.objects.filter(calibration_run=run).order_by('worker_name', 'iteration_num')

    # Group the iterations by worker_name using groupby
    grouped_iterations = groupby(iterations, key=attrgetter('worker_name'))

    # Process each group of iterations
    for worker_name, group in grouped_iterations:
        process_iteration(run, output_calibration_run_dir, worker_name, group, global_best_params_list)


def process_iteration(run, output_calibration_run_dir, worker_name: str, iterations, global_best_params_list):
    worker_path = os.path.join(output_calibration_run_dir, worker_name)
    if not os.path.exists(worker_path):
        # TODO Need to make sure we're handling exceptions
        raise CerfException(f"{worker_path} does not exist")

    metrics_iteration_file = os.path.join(worker_path, f'{run.gage.gage_id}_metrics_iteration.csv')
    params_iteration_file = os.path.join(worker_path, f'{run.gage.gage_id}_params_iteration.csv')
    # Contains the best for DDS
    objective_log_best_file = os.path.join(worker_path, f'{run.gage.gage_id}_objective_log.txt')

    if not os.path.exists(metrics_iteration_file):
        raise CerfException(f'{metrics_iteration_file} does not exist')
    if not os.path.exists(params_iteration_file):
        raise CerfException(f'{params_iteration_file} does not exist')
    print('optimization', run.optimization.name)
    best_iteration_for_worker = -1
    if run.optimization.name == 'DDS':
        print(f'checking if {objective_log_best_file} exists')
        if not os.path.exists(objective_log_best_file):
            raise CerfException(f'{objective_log_best_file} does not exist')
        # Get the best iteration number
        last_line = read_last_line(objective_log_best_file)
        best_iteration_for_worker = int(last_line.split(',')[2])
    else:
        # for GWO and PSO, we can't get the best iteration number.  We need to read the actual best parameters and then try to match them up when we read the parameter file later
        pass

    #########
    # TODO For dev only, we will delete entries first
    #########
    IterationMetric.objects.filter(iteration__calibration_run=run).delete()
    IterationParameter.objects.filter(iteration__calibration_run=run).delete()
    #####

    metrics_to_create = []
    params_to_create = []

    update_output_variables(metrics_iteration_file, run, worker_name)

    # Read the metrics and parameter files and update values
    with open(metrics_iteration_file) as metrics_file, open(params_iteration_file) as params_file:
        metrics_reader = csv.DictReader(metrics_file)
        params_reader = csv.DictReader(params_file)

        for iteration, metrics_row, params_row in zip(iterations, metrics_reader, params_reader):
            print(f'iteration number: {iteration.iteration_num}')
            process_metrics_row(iteration, metrics_row, metrics_to_create)
            process_params_row(iteration, params_row, params_to_create, best_iteration_for_worker, global_best_params_list)

    # Bulk create IterationMetric and IterationParameter objects
    IterationMetric.objects.bulk_create(metrics_to_create)
    IterationParameter.objects.bulk_create(params_to_create)


def process_metrics_row(iteration, metrics_row, metrics_to_create):
    """Process a single row from the metrics file and create IterationMetric objects."""

    # Get rid of 'iteration' and 'objFunVal' columns
    metrics_row = {k: v for k, v in metrics_row.items() if k not in ['iteration', 'objFunVal']}

    for metric_name, value in metrics_row.items():
        # Do a case-insensitive match
        metric = Metric.objects.filter(name__iexact=metric_name).first()
        if not metric:
            raise CerfException(f"Could not find metric '{metric_name}' referenced in metrics_iteration_file")

        metric_value = float(value) if value else None
        metric_obj = IterationMetric(
            iteration=iteration,
            metric=metric,
            metric_value=metric_value
        )
        metrics_to_create.append(metric_obj)


def process_params_row(iteration, params_row, params_to_create, best_iteration_for_worker, global_best_params_list):
    """Process a single row from the params file and create IterationParameter objects."""

    # Get rid of the 'iteration' column
    params_row = {k: v for k, v in params_row.items() if k != 'iteration'}

    # Check if this row matches global_best_params

    # Convert global_best_params to a dictionary for easier comparison
    best_params_dict = {
        param['name']: float(param['value'])
        for param in global_best_params_list
    }

    is_best_match = True

    # Ensure params_row contains exactly the same parameters as global_best_params
    if len(params_row) != len(best_params_dict):
        is_best_match = False
    else:
        # Check if all params in params_row match those in best_params_dict
        for param_name, value in params_row.items():
            if param_name not in best_params_dict or float(value) != best_params_dict[param_name]:
                is_best_match = False
                break

        # Check if all keys in best_params_dict are present in params_row
        for best_param_name in best_params_dict:
            if best_param_name not in params_row:
                is_best_match = False
                break

    for param_name, value in params_row.items():
        # Do a case-insensitive match
        parameter = CalibrationParameter.objects.filter(name__iexact=param_name).first()
        if not parameter:
            raise CerfException(f"Could not find parameter '{param_name}' referenced in params_iteration_file")

        # Determine if this param should be marked as best
        # Either the iteration number matches (for DDS); or the parameter values match (for GWO or PSO)
        best = is_best_match or iteration.iteration_num == best_iteration_for_worker

        param_value = float(value) if value else None
        param_obj = IterationParameter(
            iteration=iteration,
            parameter=parameter,
            param_value=param_value,
            best=best

        )
        params_to_create.append(param_obj)


def update_output_variables(metrics_iteration_file, run, worker_name):
    # Prefetch all relevant Iteration objects and create a dictionary keyed by iteration_num
    iterations_dict = {
        iteration.iteration_num: iteration
        for iteration in Iteration.objects.filter(calibration_run=run, worker_name=worker_name)
    }

    iterations_to_update = []

    # We read the metrics_iteration_file to get the output variable value for the Iteration object
    with open(metrics_iteration_file) as file:
        reader = csv.DictReader(file)
        # iteration,objFunVal,Corr,MAE,RMSE,RSR,PBIAS,NSE,NSELog,NSEWt,KGE,POD,FAR,CSI,FBIAS,HSEG_FDC,MSEG_FDC,LSEG_FDC
        row_dict: Dict[str, str]
        for row_dict in reader:
            iteration_num = int(row_dict['iteration'])
            obj_fun_val = row_dict['objFunVal']

            # Retrieve the iteration object from the dictionary
            iteration = iterations_dict.get(iteration_num)
            if not iteration:
                raise CerfException(
                    f"Cannot find Iteration object for calibration run {run.id}, worker {worker_name}, iteration {iteration_num}.  Ngen-cal did not report this iteration")

            iteration.calibration_output_variable_value = obj_fun_val

            # Add the modified object to the list
            iterations_to_update.append(iteration)

    # Perform a bulk update for all iterations in the list
    Iteration.objects.bulk_update(iterations_to_update, ['calibration_output_variable_value'])


# # Read backwards from the end of the file until we find linefeed.  Then read the line
def read_last_line(filename):
    with open(filename, 'rb') as file:
        # Move the cursor to the end of the file
        file.seek(-2, 2)
        while file.read(1) != b'\n':
            file.seek(-2, 1)
        last_line = file.readline().decode()
        return last_line


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

    calibration_run_id = validator.data.get('calibration_run_id')
    optimization = validator.data.get('optimization')
    iteration_number = validator.data.get('iteration')
    worker_name = validator.data.get('worker_name')

    starting_iteration = 0 if optimization == OptimizationEnum.DDS else 1

    run, errorReturn = get_run(calibration_run_id, request.user, run_status=[StatusEnum.SAVED, StatusEnum.READY])
    # run, errorReturn = get_run(calibration_run_id, request.user, run_status=[StatusEnum.RUNNING])
    if errorReturn:
        return errorReturn

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
        200: GenericResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: ErrorResponseSerializer
    },
    description="Get iteration of a running calibration"
)
# Called by ngen_cal
@api_view(['POST'])
# @permission_classes([AllowAny])
@handle_exceptions
def get_iteration(request):
    data = request.data if request.method == 'POST' else request.query_params
    logger.debug(f'get_iteration() request from {request.user} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    # TODO Running jobs (or Done?)
    calibration_run_id = validator.data.get('calibration_run_id')

    # TODO read output file

    run, errorReturn = get_run(calibration_run_id, request.user, run_status=[StatusEnum.RUNNING, StatusEnum.DONE, StatusEnum.FAILED])
    if errorReturn:
        return errorReturn

    # TODO Need to figure out iterations with respect to multiple workers
    iteration = 1
    response = {'message': f'Last iteration for Calibration Run {run.id} is {iteration}', 'calibration_run_id': run.id,
                'status': run.status.name, 'iteration': iteration}

    response_validator, error_response = validate_response(GenericResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user} from get_iteration() - {response_validator.data}')

    return Response(response_validator.data)


def subset_directory_by_time_range(input_directory, output_directory, date_time_range: DateTimeRange):
    logger.info(f'Subsetting directory {input_directory}')

    if not os.path.exists(output_directory):
        os.makedirs(output_directory, exist_ok=True)

    for filename in os.listdir(input_directory):
        input_file_path = os.path.join(input_directory, filename)
        output_file_path = os.path.join(output_directory, filename)

        if os.path.isfile(input_file_path):  # Ensure it's a file
            subset_by_time_range(input_file_path, output_file_path, date_time_range)

    logger.info(f'Done subsetting directory {input_directory}')


# I changed this to use multiprocessing in the hopes of speeding it up a bit, but did not seem to have any affect
# mostly likely because the S3 file processing is the bottleneck
# def subset_directory_by_time_range(input_directory, output_directory, date_time_range: DateTimeRange):
#     logger.info(f'Subsetting directory {input_directory}')
#
#     if not os.path.exists(output_directory):
#         os.makedirs(output_directory, exist_ok=True)
#
#     with ThreadPoolExecutor() as executor:
#         futures = []
#         for filename in os.listdir(input_directory):
#             input_file_path = os.path.join(input_directory, filename)
#             output_file_path = os.path.join(output_directory, filename)
#
#             if os.path.isfile(input_file_path):
#                 future = executor.submit(subset_by_time_range, input_file_path, output_file_path, date_time_range)
#                 futures.append(future)
#
#         for future in as_completed(futures):
#             future.result()  # Propagate any exceptions
#
#     logger.info(f'Done subsetting directory {input_directory}')


def subset_by_time_range(input_file, output_file, date_time_range: DateTimeRange):
    logger.info(f'Subsetting file {input_file} to {output_file}')

    # Read the CSV into a DataFrame, parsing dates in the first column
    df = pd.read_csv(input_file, delimiter=',', parse_dates=[0])

    # Ensure the first column is converted to UTC and timezone aware
    df['dateTime'] = pd.to_datetime(df.iloc[:, 0], errors='coerce')

    # If the datetime is naive, localize it to UTC
    if df['dateTime'].dt.tz is None:
        df['dateTime'] = df['dateTime'].dt.tz_localize('UTC', ambiguous='NaT', nonexistent='shift_forward')

    # Filter the rows based on the date range
    mask = (df['dateTime'] >= date_time_range.start_datetime) & (df['dateTime'] <= date_time_range.end_datetime)
    subset_df = df[mask]

    # Write the filtered DataFrame to the output CSV file
    subset_df.to_csv(output_file, index=False)


# def subset_by_time_range(input_file, output_file, date_time_range: DateTimeRange):
#     logger.info(f'Subsetting file {input_file} to {output_file}')
#     os.makedirs(os.path.dirname(output_file), exist_ok=True)
#     with open(input_file, 'r', buffering=32768) as infile, open(output_file, 'w', newline='', buffering=32768) as outfile:
#         reader = csv.reader(infile)
#         writer = csv.writer(outfile)
#
#         header = next(reader)  # Read the header
#         writer.writerow(header)  # Write the header to the output file
#
#         for row in reader:
#             row_date = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
#             if row_date in date_time_range:
#                 writer.writerow(row)
#
#     logger.info(f'Done subsetting file {input_file} to {output_file}')
