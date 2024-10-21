import csv
import logging
import os
import re
from collections import deque
from datetime import timedelta
from itertools import groupby
from operator import attrgetter
from pathlib import Path
from typing import Dict

import pandas as pd
from django.core.cache import cache
from django.db import transaction

from calibration.enums import OptimizationEnum, ValidationMetricPeriod, ValidationType
from calibration.models import Iteration, CalibrationRun, IterationMetric, IterationParameter, CalibrationParameter, Metric, ValidationRun, \
    PerformanceMetrics, ValidationMetrics, NWMRetrospectiveMetrics, IterationResult

from calibration.util.ngen_locations import get_realization_file_path, get_metrics_iteration_file_from_worker_dir, get_metrics_iteration_file, \
    get_params_iteration_file, get_objective_log_best_file, get_worker_path, get_global_best_params_file, get_output_calibration_run_dir, \
    get_validation_metrics_valid_control_file, get_validation_metrics_valid_best_file, get_validation_metrics_valid_iteration_file, \
    get_validation_performance_file, get_calibration_performance_file, get_validation_metrics_nwm_retrospective_file, get_output_iteration_csv
from calibration.views.common import CerfException, get_job_description

logger = logging.getLogger(__name__)

BULK_CREATE_BATCH_SIZE = 1000  # Define a reasonable batch size

# Regular expression pattern to match directories like "ngen_xxxxxxx_worker"
worker_directory_pattern = re.compile(r'ngen_\w+_worker')


def read_validation_output(validation_run: ValidationRun):
    job_description = get_job_description(validation_run)

    logger.info(f"Processing output for {job_description} ")

    with transaction.atomic():
        metrics = parse_performance_metrics(get_validation_performance_file(validation_run.calibration_run, validation_run.worker_name, validation_run.iteration_num))
        validation_run.performance_metrics = metrics
        validation_run.save(update_fields=['performance_metrics'])

        process_validation_for_validation_run(validation_run)

    logger.info(f"End of processing output for {job_description}")


# Function to read the output of a calibration run
def read_calibration_output(calibration_run: CalibrationRun):
    """
    Process the output of a CalibrationRun. This function handles reading and
    processing the worker directories and their iteration files.

    :param calibration_run: The CalibrationRun instance whose output is to be processed.
    """
    job_description = get_job_description(calibration_run)

    logger.info(f"Processing output for {job_description }")

    with transaction.atomic():
        metrics = parse_performance_metrics(get_calibration_performance_file(calibration_run))
        calibration_run.performance_metrics = metrics

        if IterationMetric.objects.filter(iteration__calibration_run=calibration_run).exists():
            raise CerfException(f"End of job processing has already been completed for {job_description }")

        # Set the realization file path for the run
        calibration_run.realization_file_path = get_realization_file_path(calibration_run)

        # Save the run and process iterations within a transaction
        calibration_run.save()
        process_iterations_for_all_workers(calibration_run)

        calibration_run.save()

    logger.info(f"End of processing output for {job_description}")


def process_validation_metrics(run: ValidationRun | CalibrationRun, metrics_file: str, expected_run_type: str) -> None:
    """
    Generic function to process validation or calibration metrics from a CSV file and create corresponding Metric objects.

    :param run: The ValidationRun or CalibrationRun instance.
    :param metrics_file: The file path of the metrics CSV file.
    :param expected_run_type: The expected run type to validate.
    :return: None
    """

    job_description = get_job_description(run)
    logger.info(f"Processing '{metrics_file} for {job_description}")

    # Check if the file exists
    if not Path(metrics_file).is_file():
        raise CerfException(f'{metrics_file} does not exist')

    # Read the metrics file using pandas
    metrics_df = pd.read_csv(metrics_file)

    # Prefetch metrics for quick lookup
    metrics_lookup = get_cached_metrics()

    metrics_to_create = []  # List to accumulate metrics to be created

    # Determine the type of metric to create
    MetricModel = ValidationMetrics if isinstance(run, ValidationRun) else NWMRetrospectiveMetrics

    # Loop over each row in the metrics file
    for _, row in metrics_df.iterrows():
        # Extract the run type and period fields
        run_type = row['run']
        if run_type != expected_run_type:
            logger.info(f'Unexpected run_type in {metrics_file} - {run_type}')
        period = row['period']
        if period not in ValidationMetricPeriod.get_names():
            logger.info(f'Unexpected period in {metrics_file} - {period}')

        # Extract the metrics starting from the third column onwards
        metrics_row = row[2:]

        # For each metric in the row, create or update the relevant Metric model
        for metric_name, value in metrics_row.items():
            # Perform case-insensitive lookup for the metric
            metric = metrics_lookup.get(metric_name.lower())
            if not metric:
                raise CerfException(f"Could not find metric '{metric_name}' from {metrics_file} in the database for run {run.id}")

            metric_value = float(value) if value else float('nan')

            # Create the Metric object (ValidationMetrics or NWMRetrospectiveMetrics)
            metric_obj = MetricModel(
                metric=metric,
                run_type=run_type,
                period=period,
                metric_value=metric_value,
                **({'validation_run': run} if isinstance(run, ValidationRun) else {'calibration_run': run})
            )
            logger.debug(
                f'{job_description}, type: {expected_run_type}: Creating {MetricModel.__name__} metric for Period: {period}, {metric_name} with value {metric_value}'
            )

            metrics_to_create.append(metric_obj)

    # Bulk create the metrics in the database
    if metrics_to_create:
        MetricModel.objects.bulk_create(metrics_to_create, batch_size=BULK_CREATE_BATCH_SIZE)


def process_validation_for_validation_run(validation_run: ValidationRun) -> None:
    """
    Read the file that is created by the Validation run for the specific iteration.
    Processes the metrics and updates the corresponding ValidationMetric entries.

    :param validation_run: The ValidationRun instance.
    :return: None
    """
    job_description = get_job_description(validation_run)

    metrics_file = None
    expected_run_type = None
    worker_name = validation_run.worker_name
    iteration_num = validation_run.iteration_num

    if validation_run.validation_type == ValidationType.VALID_ITERATION.value:
        metrics_file = get_validation_metrics_valid_iteration_file(validation_run.calibration_run, worker_name, iteration_num)
        expected_run_type = f'valid_{worker_name}_iter{iteration_num}'
    elif validation_run.validation_type == ValidationType.VALID_CONTROL.value:
        metrics_file = get_validation_metrics_valid_control_file(validation_run.calibration_run)
        expected_run_type = ValidationType.VALID_CONTROL.value
    elif validation_run.validation_type == ValidationType.VALID_BEST.value:
        metrics_file = get_validation_metrics_valid_best_file(validation_run.calibration_run)
        expected_run_type = ValidationType.VALID_BEST.value

    if ValidationMetrics.objects.filter(validation_run=validation_run, run_type=expected_run_type).exists():
        raise CerfException(f"End of job processing has already been completed for {job_description}")

    process_validation_metrics(
        run=validation_run,
        metrics_file=metrics_file,
        expected_run_type=expected_run_type
    )

    if validation_run.validation_type == ValidationType.VALID_CONTROL.value:
        logger.info("Processing nwm retrospective data")

        # NWM Retrospective data is processed as part of Validation Control, but we save it in the Calibration Run
        metrics_file = get_validation_metrics_nwm_retrospective_file(validation_run.calibration_run)
        expected_run_type = 'nwm_retro'

        process_validation_metrics(
            run=validation_run.calibration_run,
            metrics_file=metrics_file,
            expected_run_type=expected_run_type
        )


# Function to process iterations for all workers in a run
def process_iterations_for_all_workers(calibration_run: CalibrationRun):
    """
    Process all Iteration objects for the workers of a given CalibrationRun.
    It uses prefetching to optimize database queries and processes the iterations
    for each worker based on their metrics and parameters.

    :param calibration_run: The CalibrationRun instance.
    """
    # Query all Iteration objects for the calibration run and prefetch related metrics and parameters
    iterations = Iteration.objects.filter(calibration_run=calibration_run).order_by('worker_name', 'iteration_num').prefetch_related(
        'iterationmetric_set',
        'iterationparameter_set')

    # Group the iterations by worker and process them
    for worker_name, worker_iterations in groupby(iterations, key=attrgetter('worker_name')):
        process_iterations_for_a_worker(calibration_run, worker_name, list(worker_iterations))


# Function to process iterations for a specific worker
def process_iterations_for_a_worker(calibration_run: CalibrationRun, worker_name: str, iterations):
    """
    Process all iterations for a specific worker in a CalibrationRun.
    It reads the metrics and parameters files for the worker and processes each
    iteration for metrics and parameters creation.

    :param calibration_run: The CalibrationRun instance.
    :param worker_name: The name of the worker. This is the middle part of the worker name.
                        Need to prefix with ngen_ and suffix with _worker.
    :param iterations: A list of Iteration objects for the worker.
    """
    logger.info(f"Processing iterations for {worker_name} for Calibration Run {calibration_run.id}")

    # Get the cached metrics once for this batch of processing
    metrics_lookup = get_cached_metrics()

    # Get the worker's path
    worker_path = get_worker_path(calibration_run, worker_name)
    if not Path(worker_path).is_dir():
        raise CerfException(f"{worker_path} does not exist or is not a directory for CalibrationRun {calibration_run.id}")

    # Get the necessary files for metrics, parameters, and best objective function log
    metrics_iteration_file = get_metrics_iteration_file(calibration_run, worker_name)
    params_iteration_file = get_params_iteration_file(calibration_run, worker_name)
    # Contains the best for DDS
    objective_log_best_file = get_objective_log_best_file(calibration_run, worker_name)

    # Check if the files exist
    if not Path(metrics_iteration_file).is_file():
        raise CerfException(f'{metrics_iteration_file} does not exist for CalibrationRun {calibration_run.id}')
    if not Path(params_iteration_file).is_file():
        raise CerfException(f'{params_iteration_file} does not exist for CalibrationRun {calibration_run.id}')

    # Check for the best iteration based on optimization type (DDS, GWO, PSO)
    best_iteration_for_worker = -1
    if calibration_run.optimization.name == 'DDS':
        if not Path(objective_log_best_file).is_file():
            raise CerfException(f'{objective_log_best_file} does not exist for CalibrationRun {calibration_run.id}')
        # Read the best iteration from the log
        last_line = read_last_line(objective_log_best_file)
        best_iteration_for_worker = int(last_line.split(',')[2])
    else:
        # for GWO and PSO, we can't get the best iteration number.
        # We need to read the actual best parameters and then try to match them up when we read the parameter file later
        pass

    # Prefetch Iteration objects for efficiency
    iteration_dict = {it.iteration_num: it for it in iterations}

    # Read metrics and parameters files using pandas
    metrics_df = pd.read_csv(metrics_iteration_file)
    params_df = pd.read_csv(params_iteration_file)

    # Ensure the metrics and parameters CSV files have the same number of rows
    if len(metrics_df) != len(params_df):
        raise CerfException(f'Mismatch in the number of rows between {metrics_iteration_file} and {params_iteration_file} for CalibrationRun {calibration_run.id}')

    metrics_to_create = []  # List to accumulate metrics to be created
    params_to_create = []  # List to accumulate parameters to be created

    # Update the output variables for the worker's iterations
    update_output_variables(metrics_iteration_file, calibration_run, worker_name)

    # Loop over both metrics and parameters DataFrames row by row
    for _, (metrics_row, params_row) in enumerate(zip(metrics_df.iterrows(), params_df.iterrows())):
        iteration_num = metrics_row[1]['iteration']
        iteration = iteration_dict.get(iteration_num)
        if not iteration:
            raise CerfException(f"Iteration {iteration_num} not found for worker {worker_name} for CalibrationRun {calibration_run.id}")

        # Process metrics and parameters for this iteration
        process_metrics_row_for_calibration(calibration_run, iteration, metrics_row[1], metrics_to_create, metrics_lookup)
        process_params_row(calibration_run, iteration, params_row[1], params_to_create, best_iteration_for_worker)

    # Bulk create IterationMetric and IterationParameter objects in chunks
    if metrics_to_create:
        for i in range(0, len(metrics_to_create), BULK_CREATE_BATCH_SIZE):
            IterationMetric.objects.bulk_create(metrics_to_create[i:i + BULK_CREATE_BATCH_SIZE])

    if params_to_create:
        for i in range(0, len(params_to_create), BULK_CREATE_BATCH_SIZE):
            IterationParameter.objects.bulk_create(params_to_create[i:i + BULK_CREATE_BATCH_SIZE])

    # Check if this worker has a non-empty Output_Iteration directory
    output_iter = os.path.join(worker_path, 'Output_Iteration')
    if os.path.isdir(output_iter) and any(os.listdir(output_iter)):
        # Iterate over files and check if a file matches the current iteration number
        for filename in os.listdir(output_iter):
            # Check if the file matches the iteration number format
            for iteration_num in iteration_dict:
                expected_filename = get_output_iteration_csv(calibration_run, iteration_num)
                if filename == expected_filename:
                    # Save the filename to the IterationResult for this iteration
                    iteration = iteration_dict.get(iteration_num)
                    if iteration:
                        iteration_result = IterationResult.objects.create(
                            iteration=iteration,
                            filename=filename
                        )
                        logger.info(f"Saved output_iteration filename to {iteration_result} for CalibrationRun {calibration_run.id}")
                    break


# Function to process a single metrics row
def process_metrics_row_for_calibration(calibration_run: CalibrationRun, iteration: Iteration, metrics_row, metrics_to_create, metrics_lookup):
    """
    Process a single row from the metrics file and create IterationMetric objects.

    :param calibration_run: The CalibrationRun instance.
    :param iteration: The Iteration object for the current iteration.
    :param metrics_row: The row of metrics data from the file.
    :param metrics_to_create: The list to accumulate created IterationMetric objects.
    :param metrics_lookup: Cache to avoid repeated lookups of Metrics
    """
    job_description = get_job_description(calibration_run)

    # Get rid of 'iteration' and 'objFunVal' columns
    metrics_row = {k: v for k, v in metrics_row.items() if k not in ['iteration', 'objFunVal']}

    for metric_name, value in metrics_row.items():
        # Perform case-insensitive lookup for the metric
        metric = metrics_lookup.get(metric_name.lower())
        if not metric:
            raise CerfException(f"Could not find metric '{metric_name}'")

        metric_value = float(value) if value else None
        metric_obj = IterationMetric(
            iteration=iteration,
            metric=metric,
            metric_value=metric_value
        )
        logger.debug(f'{job_description}: Creating Iteration metric for {metric_obj}')
        metrics_to_create.append(metric_obj)


# Function to process a single parameters row
def process_params_row(calibration_run: CalibrationRun, iteration: Iteration, params_row, params_to_create, best_iteration_for_worker):
    """
    Process a single row from the parameters file and create IterationParameter objects.
    Determine if the iteration represents the best set of parameters and set the `best_params` flag on the Iteration.

    :param calibration_run: The CalibrationRun instance.
    :param iteration: The Iteration object for the current iteration.
    :param params_row: The row of parameter data from the file.
    :param params_to_create: The list to accumulate created IterationParameter objects.
    :param best_iteration_for_worker: The best iteration number for the worker, used to mark the best parameters.
    """
    job_description = get_job_description(calibration_run)

    # Filter out the 'iteration' column
    params_row = {k: v for k, v in params_row.items() if k != 'iteration'}

    # Initialize global_best_params_dict if not using DDS optimization
    best_params_dict: Dict[str, float] = {}
    if calibration_run.optimization != OptimizationEnum.from_enum(OptimizationEnum.DDS):
        global_best_params_file = get_global_best_params_file(calibration_run)
        if not Path(global_best_params_file).is_file():
            raise CerfException(f"{global_best_params_file} does not exist")

        # Read the global best parameters into a DataFrame
        df = pd.read_csv(global_best_params_file, names=['value', 'name', 'model'], skiprows=1)

        # Convert the 'name' and 'value' columns into a dictionary
        best_params_dict = pd.Series(df['value'].astype(float).values, index=df['name']).to_dict()

    # Check if the current params_row matches the global best parameters
    is_best_match = (
            len(params_row) == len(best_params_dict) and
            all(param_name in best_params_dict and float(value) == best_params_dict[param_name]
                for param_name, value in params_row.items())
    )

    # If the iteration is the best (based on matching parameters or best iteration number)
    if is_best_match or iteration.iteration_num == best_iteration_for_worker:
        logger.debug(f'{calibration_run.id}_{calibration_run.owner.username} Found best iteration: {iteration.iteration_num}, for {job_description}')
        iteration.best_params = True
    else:
        iteration.best_params = False

    # Save the iteration after setting the best_params flag
    iteration.save(update_fields=['best_params'])

    # Prefetch CalibrationParameter objects for quick lookup
    params_lookup = {p.name.lower(): p for p in CalibrationParameter.objects.all()}

    for param_name, value in params_row.items():
        # Perform case-insensitive lookup for the parameter
        parameter = params_lookup.get(param_name.lower())
        if not parameter:
            raise CerfException(f"Could not find parameter '{param_name}' referenced in params_iteration_file")

        tuned_value = float(value) if value else None
        param_obj = IterationParameter(
            iteration=iteration,
            calibration_parameter=parameter,
            tuned_value=tuned_value
        )
        logger.debug(f'{job_description}: Creating Iteration parameter for {param_obj}')
        params_to_create.append(param_obj)


# Function to update the output variables for the worker's iterations
def update_output_variables(metrics_iteration_file, calibration_run: CalibrationRun, worker_name):
    """
    Update the output variable values for each iteration in a worker's metrics file.

    :param metrics_iteration_file: The path to the metrics file.
    :param calibration_run: The CalibrationRun instance.
    :param worker_name: The name of the worker.
    """
    # Prefetch all relevant Iteration objects and create a dictionary keyed by iteration_num
    iterations_dict = {
        iteration.iteration_num: iteration
        for iteration in Iteration.objects.filter(calibration_run=calibration_run, worker_name=worker_name)
    }

    # Read the metrics file using pandas
    metrics_df = pd.read_csv(metrics_iteration_file)

    iterations_to_update = []  # List to accumulate iterations to update

    # Iterate over rows in the DataFrame
    for _, row in metrics_df.iterrows():
        iteration_num = int(row['iteration'])
        obj_fun_val = row['objFunVal']

        # Retrieve the iteration object from the dictionary
        iteration = iterations_dict.get(iteration_num)
        if not iteration:
            raise CerfException(
                f"Cannot find Iteration object for calibration run {calibration_run.id}, worker {worker_name}, iteration {iteration_num}. Ngen-cal did not report this iteration")

        logger.debug(
            f'{calibration_run.id}_{calibration_run.owner.username} Updating iteration {iteration_num} for worker {worker_name} with output variable value {obj_fun_val}')
        iteration.calibration_output_variable_value = obj_fun_val

        # Add the modified object to the list
        iterations_to_update.append(iteration)

    # Perform a bulk update for all iterations in chunks if there are any updates
    if iterations_to_update:
        with transaction.atomic():  # Ensure atomicity of the bulk update
            for i in range(0, len(iterations_to_update), BULK_CREATE_BATCH_SIZE):
                Iteration.objects.bulk_update(iterations_to_update[i:i + BULK_CREATE_BATCH_SIZE], ['calibration_output_variable_value'])


# Function to read the last line of a file
def read_last_line(filename):
    """
    Reads and returns the last line of a file.

    :param filename: The path to the file.
    :return: The last line of the file as a string.
    """
    with open(filename, 'rb') as file:
        return deque(file, maxlen=1).pop().decode().strip()


# Function to process worker directories for a CalibrationRun
def process_worker_dirs(calibration_run: CalibrationRun, worker_lambda):
    """
    Loops through directories matching the pattern "ngen_xxxxx_worker" and applies the worker_lambda function.

    :param calibration_run: The CalibrationRun instance to process.
    :param worker_lambda: A lambda function that processes each worker directory.
    """
    output_calibration_run_dir = get_output_calibration_run_dir(calibration_run)
    output_calibration_run_dir_path = Path(output_calibration_run_dir)
    if not output_calibration_run_dir_path.exists():
        raise CerfException(f"Cannot find expected data at {output_calibration_run_dir}")
    for item in output_calibration_run_dir_path.iterdir():
        # Check if the item is a directory and matches the pattern
        if item.is_dir() and worker_directory_pattern.match(item.name):
            worker_dir = output_calibration_run_dir_path / item
            logger.debug(f'{calibration_run.id}_{calibration_run.owner.username} Processing worker directory: {worker_dir}')
            worker_lambda(worker_dir, calibration_run)


# Function to accumulate the total number of iterations across worker directories
def accumulate_iterations(calibration_run: CalibrationRun):
    """
    Loops through worker directories, counts the iterations in each worker's metrics file,
    and returns the total iterations across all workers.

    :param calibration_run: The CalibrationRun instance to process.
    :return: Total number of iterations across all worker directories.
    """
    total_iterations = 0  # Initialize the accumulator

    # Define the lambda function to process each worker directory and count iterations
    def count_iterations_for_worker(worker_dir, calibration_run: CalibrationRun):  # noqa : F811
        nonlocal total_iterations
        metrics_iteration_file = get_metrics_iteration_file_from_worker_dir(calibration_run, worker_dir)

        if not Path(metrics_iteration_file).is_file():
            logger.error(f'File {metrics_iteration_file} not found in {worker_dir}')
        else:
            # Count rows in the CSV file and add to total iterations
            rows = count_rows_in_csv(metrics_iteration_file)
            total_iterations += rows

    # Call process_worker_dirs with the defined lambda function
    process_worker_dirs(calibration_run, count_iterations_for_worker)

    return total_iterations  # Return the accumulated total iterations


# Function to count the number of rows in a CSV file
def count_rows_in_csv(file_path):
    """
    Counts the number of rows in a CSV file, excluding the header.

    :param file_path: The path to the CSV file.
    :return: The number of rows in the CSV file (excluding the header).
    """
    with open(file_path, 'r') as file:
        # Count the lines and subtract 1 for the header
        return sum(1 for _ in file) - 1


def get_cached_metrics() -> dict:
    """
    Retrieve the Metric objects from cache or from the database if not cached.
    :return: A dictionary of metric names (lowercased) mapped to Metric objects.
    """
    # Check if the cache already exists
    metrics_lookup = cache.get('metrics_cache')
    if not metrics_lookup:
        # Fetch from the database and cache the results
        metrics_lookup = {m.name.lower(): m for m in Metric.objects.all()}
        cache.set('metrics_cache', metrics_lookup, None)  # Cache indefinitely
    return metrics_lookup


def parse_duration(duration_str):
    """Converts a duration string (HH:MM:SS) into a timedelta object."""
    hours, minutes, seconds = map(int, duration_str.split(':'))
    return timedelta(hours=hours, minutes=minutes, seconds=seconds)


def parse_performance_metrics(file_path):
    """
    Opens the pipe-delimited file, parses the content, and extracts performance metrics to save to database
    Expects the file to have exactly two lines of data.
    """

    if not os.path.exists(file_path):
        logger.error(f'Performance metrics file {file_path} not found')
        return
    else:
        logger.info(f'Reading performance metrics from {file_path}')

    reserved_time = None
    batch_metrics = None

    with open(file_path, 'r') as file:
        reader = csv.DictReader(file, delimiter='|')

        for row in reader:
            job_id = row['JobID']

            if job_id.endswith('.batch'):
                # Collect data from the .batch line
                batch_metrics = {
                    'slurm_job_id': job_id,
                    'elapsed_time': parse_duration(row['Elapsed']),
                    'num_cpus': int(row['NCPUS']),
                    'cpu_time': parse_duration(row['CPUTime']),
                    'max_rss': row['MaxRSS'] or None,
                    'max_disk_read': row['MaxDiskRead'] or None,
                    'max_disk_write': row['MaxDiskWrite'] or None,
                    'reserved_time': reserved_time  # This will be updated later if available
                }
            else:
                # Save the reserved time from the non-.batch line
                reserved_time = parse_duration(row['Reserved']) if row['Reserved'] else None

    if batch_metrics:
        # Now update the reserved_time for the batch metrics
        batch_metrics['reserved_time'] = reserved_time

        # Create or update the PerformanceMetrics record
        metrics = PerformanceMetrics.objects.create(
            job_id=batch_metrics['job_id'],
            elapsed_time=batch_metrics['elapsed_time'],
            num_cpus=batch_metrics['num_cpus'],
            cpu_time=batch_metrics['cpu_time'],
            max_rss=batch_metrics['max_rss'],
            max_disk_read=batch_metrics['max_disk_read'],
            max_disk_write=batch_metrics['max_disk_write'],
            reserved_time=batch_metrics['reserved_time']
        )

        return metrics

    return None
