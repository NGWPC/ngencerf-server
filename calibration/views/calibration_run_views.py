import csv
import logging
import os
from datetime import datetime, timezone
from itertools import groupby
from operator import attrgetter
from typing import Dict

from createInput import create_input
from django.db import transaction
from django.db.models import Max
from drf_spectacular.utils import extend_schema, PolymorphicProxySerializer
from git import Repo
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.enums import StatusEnum
from calibration.models import Metric, IterationMetric, Iteration, IterationTuneParameter, \
    CalibrationTuneParameter
from calibration.util.calibration_validators import CalibrationRunSerializer, IsReadyResponseSerializer, GenericResponseSerializer, \
    ErrorResponseSerializer, ExceptionResponseSerializer, ValidationExceptionSerializer, ReportIterationSerializer
from calibration.views import ngen_cal_input
from calibration.views.common import ResponseError, get_run, handle_exceptions, validate_request, validate_response, CerfException
from cerfServer.settings import NGEN_REPO_ROOT, NGEN_CAL_REPO_ROOT, NGEN_CAL_RUN_DIR

logger = logging.getLogger(__name__)


@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: IsReadyResponseSerializer,
        400: PolymorphicProxySerializer(
            component_name='MultipleErrorResponse',
            serializers=[
                ValidationExceptionSerializer,
                ErrorResponseSerializer,
            ],
            resource_type_field_name=None
        ),
        500: ExceptionResponseSerializer
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
        400: PolymorphicProxySerializer(
            component_name='MultipleErrorResponse',
            serializers=[
                ValidationExceptionSerializer,
                ErrorResponseSerializer,
            ],
            resource_type_field_name=None
        ),
        500: ExceptionResponseSerializer
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

    message = submit_job(run)
    if message:
        return ResponseError(message)

    response = {'message': f'Calibration Run {run.id} has been submitted', 'calibration_run_id': calibration_run_id,
                'status': run.status.name}

    response_validator, error_response = validate_response(GenericResponseSerializer, response)
    logger.debug(f'Returning to {request.user} from run_calibration() - {response_validator.data}')

    return Response(response_validator.data)


def submit_job(run, config_file=None):
    # If config is passed, then don't need to validate
    if not config_file:
        messages, config_file = ngen_cal_input.ready_to_run(run, build=True)
        print('config file', config_file)

        # TODO Normally, we return if not ready, but for testing, we'll skip this test
        # if messages:
        #     return f'Calibration Run {calibration_run_id} is not ready'

    # Save the latest git hash or ngen and ngen-cal
    run.ngen_commit_hash = Repo(NGEN_REPO_ROOT).head.object.hexsha
    run.ngen_cal_commit_hash = Repo(NGEN_CAL_REPO_ROOT).head.object.hexsha
    run.run_date = datetime.now(timezone.utc)
    run.save()

    message = create_input(config_file)
    if message:
        return message

    # TODO Do something here to kick it off

    return None


# This is just a test endpoint to trigger read_output()
@api_view(['GET', 'POST'])
@handle_exceptions
def test_read_output(request):
    data = request.data if request.method == 'POST' else request.query_params
    calibration_run_id = data.get('calibration_run_id')
    optimization_name = data.get('optimization')
    username = data.get('user')

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

    formulation_name = run.ngen_formulation_name
    gage_id = run.gage.gage_id
    gage_dir = os.path.join(NGEN_CAL_RUN_DIR, f'{calibration_run_id}_{run.owner.username}',
                            f'{run.objective_function.name.lower()}_{run.optimization.name.lower()}', formulation_name, gage_id)
    print("gage_dir", gage_dir)

    read_output(gage_dir, run)

    return Response(data={'calibration_run_id': calibration_run_id, 'user': username})


# This is not an endpoint, but will be automatically called
# when we get a notification (somehow) that a run has completed
def read_output(gage_dir, run):
    print('Reading output from', gage_dir)

    if not os.path.isdir(gage_dir):
        raise Exception(f'Directory {gage_dir} does not exist or is not a directory')

    output_calibration_run_dir = os.path.join(gage_dir, 'Output/Calibration_Run')

    cost_hist_file = os.path.join(output_calibration_run_dir, f'{run.gage.gage_id}_cost_hist.csv')
    # Get the best iteration number across all works
    # TODO This is not right
    # last_line = read_last_line(cost_hist_file)
    # best_iteration_for_all = int(last_line.split(',')[2])

    realization_filename = f'{run.gage.gage_id}_realization_config_bmi_calib.json'
    run.realization_filename = realization_filename

    with transaction.atomic():
        run.save()
        process_workers(run, output_calibration_run_dir)


def process_workers(run, output_calibration_run_dir):
    # Query all Iteration objects for the given calibration_run
    iterations = Iteration.objects.filter(calibration_run=run).order_by('worker_name', 'iteration_num')

    # Group the iterations by worker_name using groupby
    grouped_iterations = groupby(iterations, key=attrgetter('worker_name'))

    # Process each group of iterations
    for worker_name, group in grouped_iterations:
        # TODO This shouldn't be be necessary
        iterations_group = list(group)
        process_iteration(run, output_calibration_run_dir, worker_name, iterations_group)


def process_iteration(run, output_calibration_run_dir, worker_name: str, iterations):
    worker_path = os.path.join(output_calibration_run_dir, worker_name)
    if not os.path.exists(worker_path):
        # TODO Need to make sure we're handling exceptions
        raise CerfException(f"{worker_path} does not exist")

    metrics_iteration_file = os.path.join(worker_path, f'{run.gage.gage_id}_metrics_iteration.csv')
    params_iteration_file = os.path.join(worker_path, f'{run.gage.gage_id}_params_iteration.csv')

    if not os.path.exists(metrics_iteration_file):
        raise CerfException(f'{metrics_iteration_file} does not exist')
    if not os.path.exists(params_iteration_file):
        raise CerfException(f'{params_iteration_file} does not exist')

    # Get the best iteration number

    #########
    # TODO For dev only, we will delete entries first
    #########
    IterationMetric.objects.filter(iteration__calibration_run=run).delete()
    IterationTuneParameter.objects.filter(iteration__calibration_run=run).delete()
    Iteration.objects.filter(calibration_run=run).delete()
    #####

    metrics_to_create = []
    params_to_create = []

    update_output_variable(metrics_iteration_file)

    # Read the metrics and parameter files and update values
    with open(metrics_iteration_file) as metrics_file, open(params_iteration_file) as params_file:
        metrics_reader = csv.DictReader(metrics_file)
        params_reader = csv.DictReader(params_file)

        for iteration, metrics_row, params_row in zip(iterations, metrics_reader, params_reader):
            print(f'iteration number: {iteration.iteration_num}')
            process_metrics_row(iteration, metrics_row, metrics_to_create)
            process_params_row(iteration, params_row, params_to_create)

    # Bulk create IterationMetric and IterationTuneParameter objects
    IterationMetric.objects.bulk_create(metrics_to_create)
    IterationTuneParameter.objects.bulk_create(params_to_create)


def process_metrics_row(iteration, metrics_row, metrics_to_create):
    """Process a single row from the metrics file and create IterationMetric objects."""
    for metric_name, value in metrics_row.items():
        if metric_name in ['iteration', 'objFunVal']:
            continue

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


def process_params_row(iteration, params_row, params_to_create):
    """Process a single row from the params file and create IterationTuneParameter objects."""
    for param_name, value in params_row.items():
        if param_name == 'iteration':
            continue

        # Do a case-insensitive match
        parameter = CalibrationTuneParameter.objects.filter(name__iexact=param_name).first()
        if not parameter:
            raise CerfException(f"Could not find parameter '{param_name}' referenced in params_iteration_file")

        param_value = float(value) if value else None
        param_obj = IterationTuneParameter(
            iteration=iteration,
            parameter=parameter,
            param_value=param_value
        )
        params_to_create.append(param_obj)


def update_output_variable(metrics_iteration_file):
    iterations_to_update = []

    # We read the metrics_iteration_file to get the output variable value for the Iteration object
    with open(metrics_iteration_file) as file:
        reader = csv.DictReader(file)
        # iteration,objFunVal,Corr,MAE,RMSE,RSR,PBIAS,NSE,NSELog,NSEWt,KGE,POD,FAR,CSI,FBIAS,HSEG_FDC,MSEG_FDC,LSEG_FDC
        row_dict: Dict[str, str]
        for row_dict in reader:
            iteration_num = int(row_dict['iteration'])
            obj_fun_val = row_dict['objFunVal']

            # Find the corresponding Iteration object
            iteration = Iteration.objects.get(iteration_num=iteration_num)
            iteration.calibration_output_variable_value = obj_fun_val

            # Add the modified object to the list
            iterations_to_update.append(iteration)

    # Perform a bulk update for all iterations in the list
    Iteration.objects.bulk_update(iterations_to_update, ['calibration_output_variable_value'])


# # Read backwards from the end of the file until we find linefeed.  Then read the line
# def read_last_line(filename):
#     with open(filename, 'rb') as file:
#         # Move the cursor to the end of the file
#         file.seek(-2, 2)
#         while file.read(1) != b'\n':
#             file.seek(-2, 1)
#         last_line = file.readline().decode()
#         return last_line


@extend_schema(
    request=ReportIterationSerializer,
    responses={
        200: GenericResponseSerializer,
        400: PolymorphicProxySerializer(
            component_name='MultipleErrorResponse',
            serializers=[
                ValidationExceptionSerializer,
                ErrorResponseSerializer,
            ],
            resource_type_field_name=None
        ),
        500: ExceptionResponseSerializer
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
    iteration_number = validator.data.get('iteration')
    worker_name = validator.data.get('worker_name')

    run, errorReturn = get_run(calibration_run_id, request.user, run_status=[StatusEnum.SAVED, StatusEnum.READY])
    # run, errorReturn = get_run(calibration_run_id, request.user, run_status=[StatusEnum.RUNNING])
    if errorReturn:
        return errorReturn

    with transaction.atomic():
        if iteration_number == 0:
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
                return ResponseError(f"No existing worker_name found for '{worker_name}' in this calibration run.")

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
        400: PolymorphicProxySerializer(
            component_name='MultipleErrorResponse',
            serializers=[
                ValidationExceptionSerializer,
                ErrorResponseSerializer,
            ],
            resource_type_field_name=None
        ),
        500: ExceptionResponseSerializer
    },
    description="Report iteration of a running calibration"
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
