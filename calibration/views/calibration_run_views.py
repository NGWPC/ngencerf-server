import csv
import logging
import os
import re
from datetime import datetime, timezone
from itertools import groupby
from operator import attrgetter
from typing import Dict

import pandas as pd
from createInput import create_input
from datetimerange import DateTimeRange
from django.db import transaction
from django.db.models import Max, Sum
from drf_spectacular.utils import extend_schema, OpenApiResponse
from git import Repo
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.enums import StatusEnum, OptimizationEnum
from calibration.models import Metric, IterationMetric, Iteration, IterationParameter, \
    CalibrationParameter, CalibrationRun
from calibration.util.calibration_validators import CalibrationRunSerializer, IsReadyResponseSerializer, GenericResponseSerializer, \
    ErrorResponseSerializer, ReportIterationSerializer, SubmitJobResponseSerializer, GetIterationsResponseSerializer
from calibration.util.ngen_locations import get_global_best_params_file, get_realization_file_path, \
    get_worker_path, get_metrics_iteration_file, get_params_iteration_file, get_objective_log_best_file, get_output_calibration_run_dir, \
    get_metrics_iteration_file_from_worker_dir
from calibration.views import ngen_cal_input
from calibration.views.common import ResponseError, get_run, handle_exceptions, validate_response, CerfException, validate_request
from cerfServer.settings import NGEN_REPO_ROOT, NGEN_CAL_REPO_ROOT
from run_ngen_cal.run_ngen_cal import run_job, JobStage, terminate_job

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

    # Save the latest git hash or ngen and ngen-cal
    run.ngen_commit_hash = Repo(NGEN_REPO_ROOT).head.object.hexsha
    run.ngen_cal_commit_hash = Repo(NGEN_CAL_REPO_ROOT).head.object.hexsha
    run.run_date = datetime.now(timezone.utc)
    run.status = StatusEnum.from_enum(StatusEnum.RUNNING)
    run.save()

    run_job(run, JobStage.CALIBRATION)

    return None


# This is just a test endpoint to trigger read_output()
@api_view(['GET', 'POST'])
@handle_exceptions
def test_read_output(request):
    data = request.data if request.method == 'POST' else request.query_params
    calibration_run_id = data.get('calibration_run_id')

    run, error_return = get_run(calibration_run_id, request.user, run_status=[StatusEnum.DONE])
    print('run', run)

    if error_return:
        return error_return

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

    read_output(run)

    return Response(data={'calibration_run_id': calibration_run_id})


def create_iteration_objects_for_all_workers(run: CalibrationRun):
    worker_number = 0
    all_iteration_objects = []

    def create_iteration_objects_for_a_worker(worker_dir, run):  # noqa : F811
        nonlocal worker_number
        """
        Normally, ngen_cal sends us the iteration using the report_iteration endpoint.  We get the iteration # and worker name, and we create entries in the database.
        Until we get that interface working, we'll have to figure out the iteration by brute force
        We'll look for all the worker directories and create an iteration object for each record in the metrics_iteration.csv file
        :return:
        """
        # Create iteration object for a given worker
        worker_number += 1

        metrics_iteration_file = get_metrics_iteration_file_from_worker_dir(run, worker_dir)

        # Check if the file exists before proceeding
        if not os.path.exists(metrics_iteration_file):
            print(f'Metrics iteration file not found in {worker_dir}')
            return

        # Use pandas to read the CSV file into a DataFrame
        metrics_df = pd.read_csv(metrics_iteration_file)

        for _, row in metrics_df.iterrows():
            # TODO Why is this being read as a float
            iteration_number = row['iteration']

            print(f'Creating iteration {iteration_number} for worker {os.path.basename(worker_dir)}, worker number {worker_number}')
            all_iteration_objects.append(Iteration(
                iteration_num=iteration_number,
                calibration_run=run,
                worker_name=os.path.basename(worker_dir),
                worker_number=worker_number
            ))

    # Loop through all worker directories and apply create_iteration_objects_for_a_worker
    process_worker_dirs(run, create_iteration_objects_for_a_worker)

    Iteration.objects.bulk_create(all_iteration_objects)


# This is not an endpoint, but will be automatically called
# when we get a notification (somehow) that a run has completed
def read_output(run):
    """
    Normally, ngen_cal sends us the iteration using the report_iteration endpoint.  We get the iteration # and worker name, and we create entries in the database.
    Until we get that interface working, we'll create all the Iteration objects here
    We'll look for all the worker directories and create an iteration object for each record in the metrics_iteration.csv file
    """
    # TODO For dev only, we'll delete the objects first
    Iteration.objects.filter(calibration_run=run).delete()
    create_iteration_objects_for_all_workers(run)

    # TODO Read best params for GWO and PSO
    # global_best_params_list = {}
    # if run.optimization.name != OptimizationEnum.DDS.value:
    #     # global_best_params_file = get_global_best_params_file(run)
    #     if not os.path.exists(global_best_params_file):
    #         raise CerfException(f"{global_best_params_file} does not exist")
    #     # For non-DDS, we get the best parameters
    #     with open(global_best_params_file) as global_best_params:
    #         next(global_best_params)  # Skip header
    #         global_best_params_list = list(csv.DictReader(global_best_params, fieldnames=['value', 'name', 'model']))
    # print('global_best_params', global_best_params_list)

    run.realization_file_path = get_realization_file_path(run)

    with transaction.atomic():
        run.save()
        process_iterations_for_all_workers(run)


def process_iterations_for_all_workers(run: CalibrationRun):
    # Query all Iteration objects for the given calibration_run
    iterations = Iteration.objects.filter(calibration_run=run).order_by('worker_name', 'iteration_num')

    # Group the iterations by worker_name using groupby
    grouped_iterations = groupby(iterations, key=attrgetter('worker_name'))

    # Process iterations by worker
    for worker_name, group in grouped_iterations:
        process_iterations_for_a_worker(run, worker_name, group)


def process_iterations_for_a_worker(run: CalibrationRun, worker_name: str, iterations):
    worker_path = get_worker_path(run, worker_name)
    if not os.path.exists(worker_path):
        # TODO Need to make sure we're handling exceptions
        raise CerfException(f"{worker_path} does not exist")

    metrics_iteration_file = get_metrics_iteration_file(run, worker_name)
    params_iteration_file = get_params_iteration_file(run, worker_name)
    # Contains the best for DDS
    objective_log_best_file = get_objective_log_best_file(run, worker_name)

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
            process_metrics_row(iteration, metrics_row, metrics_to_create)
            process_params_row(run, iteration, params_row, params_to_create, best_iteration_for_worker)

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
        print(f'Creating Iteration metric for {metric_obj}')
        metrics_to_create.append(metric_obj)


def process_params_row(run, iteration, params_row, params_to_create, best_iteration_for_worker):
    """Process a single row from the params file and create IterationParameter objects."""

    # Get rid of the 'iteration' column
    params_row = {k: v for k, v in params_row.items() if k != 'iteration'}

    # Check if this row matches global_best_params

    global_best_params_list = []
    if run.optimization != OptimizationEnum.from_enum(OptimizationEnum.DDS):
        global_best_params_file = get_global_best_params_file(run)
        if not os.path.exists(global_best_params_file):
            raise CerfException(f"{global_best_params_file} does not exist")
        # For non-DDS, we get the best parameters
        with open(global_best_params_file) as global_best_params:
            next(global_best_params)  # Skip header
            global_best_params_list = list(csv.DictReader(global_best_params, fieldnames=['value', 'name', 'model']))

    print('global_best_params', global_best_params_list)
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
        print(f'Comparing global_best_params_list with {params_row.itmes()}')
        # Check if all params in params_row match those in best_params_dict
        for param_name, value in params_row.items():
            if param_name not in best_params_dict or float(value) != best_params_dict[param_name]:
                is_best_match = False
                break
        print('is_best_match', is_best_match)

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

        tuned_value = float(value) if value else None
        param_obj = IterationParameter(
            iteration=iteration,
            calibration_parameter=parameter,
            tuned_value=tuned_value,
            best=best
        )
        print(f'Creating Iteration parameter for {param_obj}')

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

            print(f'Updating iteration {iteration_num} for worker {worker_name} with output variable value {obj_fun_val}')
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
        200: GenericResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: ErrorResponseSerializer
    },
    description="Get iteration of a running calibration"
)
@api_view(['POST'])
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

    # Log and return the total iterations
    logger.debug(f'Total iterations: {total_iterations}')
    print('total iterations', total_iterations)

    # Add all iterations (1 for each worker)
    total_iteration_num = Iteration.objects.filter(calibration_run=run).aggregate(total=Sum('iteration_num'))['total'] or 0
    response = {'message': f'Last iteration for Calibration Run {run.id}, across all workers, is {total_iteration_num}', 'calibration_run_id': run.id,
                'status': run.status.name, 'iterations': total_iteration_num}

    response_validator, error_response = validate_response(GetIterationsResponseSerializer, response)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user} from get_iteration() - {response_validator.data}')

    return Response(response_validator.data)


# Regular expression pattern to match directories like "ngen_xxxxxxx_worker"
worker_directory_pattern = re.compile(r'ngen_\w+_worker')


def process_worker_dirs(run, worker_lambda):
    """
    Loops through directories matching the pattern "ngen_xxxxx_worker" and applies the worker_lambda function.

    :param run: The run object to process
    :param worker_lambda: A lambda function that processes each worker directory
    """
    output_calibration_run_dir = get_output_calibration_run_dir(run)
    for item in os.listdir(output_calibration_run_dir):
        item_path = os.path.join(output_calibration_run_dir, item)
        # Check if the item is a directory and matches the pattern
        if os.path.isdir(item_path) and worker_directory_pattern.match(item):
            worker_dir = os.path.join(output_calibration_run_dir, item)
            print('Processing worker directory:', worker_dir)
            worker_lambda(worker_dir, run)


def accumulate_iterations(run: CalibrationRun):
    """
    This function loops through worker directories, counts the iterations in each worker's metrics file,
    and returns the total iterations across all workers.

    :param run: The run object to process
    :return: Total number of iterations across all worker directories
    """
    total_iterations = 0  # Initialize the accumulator

    # Define the lambda function to process each worker directory
    def process_worker(worker_dir, run: CalibrationRun):  # noqa : F811
        nonlocal total_iterations
        metrics_iteration_file = get_metrics_iteration_file_from_worker_dir(run, worker_dir)

        if not os.path.exists(metrics_iteration_file):
            print(f'File {metrics_iteration_file} not found in {worker_dir}')
        else:
            # Count rows in the CSV file and add to total iterations
            rows = count_rows_in_csv(metrics_iteration_file)
            print(f'{rows} in {metrics_iteration_file}')
            total_iterations += rows

    # Call process_worker_dirs with the defined lambda function
    process_worker_dirs(run, process_worker)

    return total_iterations  # Return the accumulated total iterations


def count_rows_in_csv(file_path):
    with open(file_path, 'r') as file:
        # Count the lines and subtract 1 for the header
        return sum(1 for line in file) - 1


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
def cancel_job(request):
    data = request.data if request.method == 'POST' else request.query_params
    logger.debug(f'get_iteration() request from {request.user} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.get('calibration_run_id')

    run, error_return = get_run(calibration_run_id, request.user, run_status=[StatusEnum.RUNNING])
    if error_return:
        return error_return

    if not terminate_job(run.id):
        return ResponseError(f"Calibration Run {run.id} is not running")
    else:
        run.status = StatusEnum.from_enum(StatusEnum.CANCELLED)
        run.save(update_fields=['status'])
        print('run', run)

    response = {'message': f'Calibration Run job {run.id} has been canceled', 'calibration_run_id': run.id,
                'status': run.status.name, }

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
