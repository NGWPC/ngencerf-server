import logging
import re
from collections import deque
from datetime import datetime, timezone
from itertools import groupby
from operator import attrgetter
from pathlib import Path
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

BULK_CREATE_BATCH_SIZE = 1000  # Define a reasonable batch size


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
        if not Path(metrics_iteration_file).is_file():
            print(f'Metrics iteration file not found in {worker_dir}')
            return

        # Use pandas to read the CSV file into a DataFrame
        metrics_df = pd.read_csv(metrics_iteration_file, dtype={'iteration': int})

        for _, row in metrics_df.iterrows():
            iteration_number = row['iteration']

            print(f'Creating iteration {iteration_number} for worker {Path(worker_dir).name}, worker number {worker_number}')
            all_iteration_objects.append(Iteration(
                iteration_num=iteration_number,
                calibration_run=run,
                worker_name=Path(worker_dir).name,
                worker_number=worker_number
            ))

    # Loop through all worker directories and apply create_iteration_objects_for_a_worker
    process_worker_dirs(run, create_iteration_objects_for_a_worker)

    if all_iteration_objects:
        with transaction.atomic():  # Ensure atomicity of bulk update
            for i in range(0, len(all_iteration_objects), BULK_CREATE_BATCH_SIZE):
                Iteration.objects.bulk_update(all_iteration_objects[i:i + BULK_CREATE_BATCH_SIZE], ['calibration_output_variable_value'])


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

    run.realization_file_path = get_realization_file_path(run)

    with transaction.atomic():
        run.save()
        process_iterations_for_all_workers(run)


def process_iterations_for_all_workers(run: CalibrationRun):
    # Query all Iteration objects for the given calibration_run
    iterations = Iteration.objects.filter(calibration_run=run).order_by('worker_name', 'iteration_num').prefetch_related('iterationmetric_set',
                                                                                                                         'iterationparameter_set')

    # Use itertools.groupby to efficiently group in memory
    for worker_name, worker_iterations in groupby(iterations, key=attrgetter('worker_name')):
        process_iterations_for_a_worker(run, worker_name, list(worker_iterations))


def process_iterations_for_a_worker(run: CalibrationRun, worker_name: str, iterations):
    worker_path = get_worker_path(run, worker_name)
    if not Path(worker_path).is_dir():
        # TODO Need to make sure we're handling exceptions
        raise CerfException(f"{worker_path} does not exist")

    metrics_iteration_file = get_metrics_iteration_file(run, worker_name)
    params_iteration_file = get_params_iteration_file(run, worker_name)
    # Contains the best for DDS
    objective_log_best_file = get_objective_log_best_file(run, worker_name)

    if not Path(metrics_iteration_file).is_file():
        raise CerfException(f'{metrics_iteration_file} does not exist')
    if not Path(params_iteration_file).is_file():
        raise CerfException(f'{params_iteration_file} does not exist')

    best_iteration_for_worker = -1
    if run.optimization.name == 'DDS':
        if not Path(objective_log_best_file).is_file():
            raise CerfException(f'{objective_log_best_file} does not exist')
        # Get the best iteration number
        last_line = read_last_line(objective_log_best_file)
        best_iteration_for_worker = int(last_line.split(',')[2])
    else:
        # for GWO and PSO, we can't get the best iteration number.  We need to read the actual best parameters and then try to match them up when we read the parameter file later
        pass

    # Prefetch Iteration objects for efficiency
    iteration_dict = {it.iteration_num: it for it in iterations}

    #########
    # TODO For dev only, we will delete entries first
    #########
    IterationMetric.objects.filter(iteration__calibration_run=run).delete()
    IterationParameter.objects.filter(iteration__calibration_run=run).delete()
    #####

    # Use pandas for reading both files efficiently
    metrics_df = pd.read_csv(metrics_iteration_file)
    params_df = pd.read_csv(params_iteration_file)

    # Ensure the CSV files have the same number of rows (sanity check)
    if len(metrics_df) != len(params_df):
        raise CerfException(f'Mismatch in the number of rows between {metrics_iteration_file} and {params_iteration_file}')

    metrics_to_create = []
    params_to_create = []

    # Call the function to update the output variable values for iterations
    update_output_variables(metrics_iteration_file, run, worker_name)

    # Loop over both DataFrames row by row
    for _, (metrics_row, params_row) in enumerate(zip(metrics_df.iterrows(), params_df.iterrows())):
        iteration_num = metrics_row[1]['iteration']
        iteration = iteration_dict.get(iteration_num)
        if not iteration:
            raise CerfException(f"Iteration {iteration_num} not found for worker {worker_name}")

        process_metrics_row(iteration, metrics_row[1], metrics_to_create)
        process_params_row(run, iteration, params_row[1], params_to_create, best_iteration_for_worker)

    # # Bulk create IterationMetric and IterationParameter objects
    # IterationMetric.objects.bulk_create(metrics_to_create)
    # IterationParameter.objects.bulk_create(params_to_create)

    # Bulk create IterationMetric and IterationParameter objects in chunks
    if metrics_to_create:
        for i in range(0, len(metrics_to_create), BULK_CREATE_BATCH_SIZE):
            IterationMetric.objects.bulk_create(metrics_to_create[i:i + BULK_CREATE_BATCH_SIZE])

    if params_to_create:
        for i in range(0, len(params_to_create), BULK_CREATE_BATCH_SIZE):
            IterationParameter.objects.bulk_create(params_to_create[i:i + BULK_CREATE_BATCH_SIZE])


def process_metrics_row(iteration, metrics_row, metrics_to_create):
    """Process a single row from the metrics file and create IterationMetric objects."""

    # Get rid of 'iteration' and 'objFunVal' columns
    metrics_row = {k: v for k, v in metrics_row.items() if k not in ['iteration', 'objFunVal']}

    # Prefetch metrics for quick lockup
    metrics_lookup = {m.name.lower(): m for m in Metric.objects.all()}

    for metric_name, value in metrics_row.items():
        # Do a case-insensitive match
        metric = metrics_lookup.get(metric_name.lower())
        if not metric:
            raise CerfException(f"Could not find metric '{metric_name}'")

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

    # Initialize global_best_params_dict only if necessary
    best_params_dict: Dict[str, float] = {}
    if run.optimization != OptimizationEnum.from_enum(OptimizationEnum.DDS):
        global_best_params_file = get_global_best_params_file(run)
        if not Path(global_best_params_file).is_file():
            raise CerfException(f"{global_best_params_file} does not exist")

        # Use pandas to read the CSV file into a DataFrame
        df = pd.read_csv(global_best_params_file, names=['value', 'name', 'model'], skiprows=1)

        # Convert the 'name' and 'value' columns into a dictionary
        best_params_dict = pd.Series(df['value'].astype(float).values, index=df['name']).to_dict()
        print('best_params_dict:', best_params_dict)

    # Check if this params_row matches the global best parameters
    is_best_match = (
            len(params_row) == len(best_params_dict) and
            all(param_name in best_params_dict and float(value) == best_params_dict[param_name]
                for param_name, value in params_row.items())
    )
    if is_best_match:
        print('found best match:', params_row)

    # Prefetch params for quick lookup
    params_lookup = {p.name.lower(): p for p in CalibrationParameter.objects.all()}

    for param_name, value in params_row.items():
        # Do a case-insensitive match
        parameter = params_lookup.get(param_name.lower())
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

        # Append the created object to the list for bulk creation
        params_to_create.append(param_obj)


def update_output_variables(metrics_iteration_file, run, worker_name):
    # Prefetch all relevant Iteration objects and create a dictionary keyed by iteration_num
    iterations_dict = {
        iteration.iteration_num: iteration
        for iteration in Iteration.objects.filter(calibration_run=run, worker_name=worker_name)
    }

    # Read the metrics file using pandas for better handling
    metrics_df = pd.read_csv(metrics_iteration_file)

    iterations_to_update = []

    # Iterate over rows in the DataFrame
    for _, row in metrics_df.iterrows():
        iteration_num = int(row['iteration'])
        obj_fun_val = row['objFunVal']

        # Retrieve the iteration object from the dictionary
        iteration = iterations_dict.get(iteration_num)
        if not iteration:
            raise CerfException(
                f"Cannot find Iteration object for calibration run {run.id}, worker {worker_name}, iteration {iteration_num}.  Ngen-cal did not report this iteration")

        print(f'Updating iteration {iteration_num} for worker {worker_name} with output variable value {obj_fun_val}')
        iteration.calibration_output_variable_value = obj_fun_val

        # Add the modified object to the list
        iterations_to_update.append(iteration)

    # Perform a bulk update for all iterations in chunks if there are any updates to apply
    if iterations_to_update:
        with transaction.atomic():  # Ensure atomicity of bulk update
            for i in range(0, len(iterations_to_update), BULK_CREATE_BATCH_SIZE):
                Iteration.objects.bulk_update(iterations_to_update[i:i + BULK_CREATE_BATCH_SIZE], ['calibration_output_variable_value'])


# # Read backwards from the end of the file until we find linefeed.  Then read the line
# def read_last_line(filename):
#     with open(filename, 'rb') as file:
#         # Move the cursor to the end of the file
#         file.seek(-2, 2)
#         while file.read(1) != b'\n':
#             file.seek(-2, 1)
#         last_line = file.readline().decode()
#         return last_line


def read_last_line(filename):
    with open(filename, 'rb') as file:
        return deque(file, maxlen=1).pop().decode().strip()


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
    for item in Path(output_calibration_run_dir).iterdir():
        item_path = Path(output_calibration_run_dir) / item
        # Check if the item is a directory and matches the pattern
        if item_path.is_dir() and worker_directory_pattern.match(str(item)):
            worker_dir = Path(output_calibration_run_dir) / item
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

        if not Path(metrics_iteration_file).is_file():
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
        return sum(1 for _ in file) - 1


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
