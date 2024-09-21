import logging
import re
from collections import deque
from itertools import groupby
from operator import attrgetter
from pathlib import Path
from typing import Dict

import pandas as pd
from django.db import transaction

from calibration.enums import OptimizationEnum
from calibration.models import Iteration, CalibrationRun, IterationMetric, IterationParameter, CalibrationParameter, Metric
from calibration.util.ngen_locations import get_realization_file_path, get_metrics_iteration_file_from_worker_dir, get_metrics_iteration_file, \
    get_params_iteration_file, get_objective_log_best_file, get_worker_path, get_global_best_params_file, get_output_calibration_run_dir
from calibration.views.common import CerfException

logger = logging.getLogger(__name__)

BULK_CREATE_BATCH_SIZE = 1000  # Define a reasonable batch size

# Regular expression pattern to match directories like "ngen_xxxxxxx_worker"
worker_directory_pattern = re.compile(r'ngen_\w+_worker')


# Automatically called when a job ends
def read_output(run):
    """
    Normally, ngen_cal sends us the iteration using the report_iteration endpoint.  We get the iteration # and worker name, and we create entries in the database.
    Until we get that interface working, we'll create all the Iteration objects here
    We'll look for all the worker directories and create an iteration object for each record in the metrics_iteration.csv file
    """
    logger.info(f"Processing output for Calibration Run {run.id}")

    create_iteration_objects_for_all_workers(run)

    run.realization_file_path = get_realization_file_path(run)

    with transaction.atomic():
        run.save()
        process_iterations_for_all_workers(run)


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
            logger.error(f'Metrics iteration file not found in {worker_dir}')
            return

        # Use pandas to read the CSV file into a DataFrame
        metrics_df = pd.read_csv(metrics_iteration_file, dtype={'iteration': int})

        for _, row in metrics_df.iterrows():
            iteration_number = row['iteration']

            logger.debug(f'{run.id}_{run.owner.username} Creating iteration {iteration_number} for worker {Path(worker_dir).name}, worker number {worker_number}')
            all_iteration_objects.append(Iteration(
                iteration_num=iteration_number,
                calibration_run=run,
                worker_name=Path(worker_dir).name,
                worker_number=worker_number
            ))

    # Loop through all worker directories and apply create_iteration_objects_for_a_worker
    process_worker_dirs(run, create_iteration_objects_for_a_worker)

    if all_iteration_objects:
        with transaction.atomic():
            for i in range(0, len(all_iteration_objects), BULK_CREATE_BATCH_SIZE):
                Iteration.objects.bulk_create(all_iteration_objects[i:i + BULK_CREATE_BATCH_SIZE], batch_size=BULK_CREATE_BATCH_SIZE)


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

        process_metrics_row(run, iteration, metrics_row[1], metrics_to_create)
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


def process_metrics_row(run, iteration, metrics_row, metrics_to_create):
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
        logger.debug(f'{run.id}_{run.owner.username} Creating Iteration metric for {metric_obj}')
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
        # print('best_params_dict:', best_params_dict)

    # Check if this params_row matches the global best parameters
    is_best_match = (
            len(params_row) == len(best_params_dict) and
            all(param_name in best_params_dict and float(value) == best_params_dict[param_name]
                for param_name, value in params_row.items())
    )
    if is_best_match:
        logger.debug(f'{run.id}_{run.owner.username} Found best match:{params_row}')

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
        logger.debug(f'{run.id}_{run.owner.username} Creating Iteration parameter for {param_obj}')

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

        logger.debug(f'{run.id}_{run.owner.username} Updating iteration {iteration_num} for worker {worker_name} with output variable value {obj_fun_val}')
        iteration.calibration_output_variable_value = obj_fun_val

        # Add the modified object to the list
        iterations_to_update.append(iteration)

    # Perform a bulk update for all iterations in chunks if there are any updates to apply
    if iterations_to_update:
        with transaction.atomic():  # Ensure atomicity of bulk update
            for i in range(0, len(iterations_to_update), BULK_CREATE_BATCH_SIZE):
                Iteration.objects.bulk_update(iterations_to_update[i:i + BULK_CREATE_BATCH_SIZE], ['calibration_output_variable_value'])


def read_last_line(filename):
    with open(filename, 'rb') as file:
        return deque(file, maxlen=1).pop().decode().strip()


def process_worker_dirs(run: CalibrationRun, worker_lambda):
    """
    Loops through directories matching the pattern "ngen_xxxxx_worker" and applies the worker_lambda function.

    :param run: The run object to process
    :param worker_lambda: A lambda function that processes each worker directory
    """
    output_calibration_run_dir = get_output_calibration_run_dir(run)
    for item in Path(output_calibration_run_dir).iterdir():
        # Check if the item is a directory and matches the pattern
        if item.is_dir() and worker_directory_pattern.match(item.name):
            worker_dir = Path(output_calibration_run_dir) / item
            logger.debug(f'{run.id}_{run.owner.username} Processing worker directory:{worker_dir}')
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
    def count_iterations_for_worker(worker_dir, run: CalibrationRun):  # noqa : F811
        nonlocal total_iterations
        metrics_iteration_file = get_metrics_iteration_file_from_worker_dir(run, worker_dir)

        if not Path(metrics_iteration_file).is_file():
            logger.error(f'File {metrics_iteration_file} not found in {worker_dir}')
        else:
            # Count rows in the CSV file and add to total iterations
            rows = count_rows_in_csv(metrics_iteration_file)
            total_iterations += rows

    # Call process_worker_dirs with the defined lambda function
    process_worker_dirs(run, count_iterations_for_worker)

    return total_iterations  # Return the accumulated total iterations


def count_rows_in_csv(file_path):
    with open(file_path, 'r') as file:
        # Count the lines and subtract 1 for the header
        return sum(1 for _ in file) - 1
