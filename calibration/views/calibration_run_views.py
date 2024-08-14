import csv
import json
import logging
import os
import re
from json.decoder import JSONDecodeError
from typing import Dict

from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema, PolymorphicProxySerializer
from git import Repo
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from calibration.createInput import create_input
from calibration.enums import StatusEnum
from calibration.models import CalibrationRun, Gage, Optimization, Metric, Iteration, IterationMetric
from calibration.util.calibration_validators import CalibrationRunValidator, IsReadyResponseSerializer, GenericResponseSerializer, \
    ErrorResponseSerializer, ExceptionResponseSerializer, ValidationErrorSerializer, ValidationExceptionSerializer
from calibration.views import ngen_cal_input
from calibration.views.common import get_run, ResponseError
from cerfServer.settings import NGEN_REPO_ROOT, NGEN_CAL_REPO_ROOT, NGEN_CAL_RUN_DIR

logger = logging.getLogger(__name__)


@extend_schema(
    request=CalibrationRunValidator,
    responses={
        200: IsReadyResponseSerializer,
        400: PolymorphicProxySerializer(
            component_name='MultipleErrorResponse',
            serializers=[
                ValidationExceptionSerializer,
                ValidationErrorSerializer,
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
def is_ready(request):
    try:
        print('user', request.user)

        body = json.loads(request.body or '{}')
        logger.debug(f'is_ready() request from {request.user} - {body}')

        validator = CalibrationRunValidator(data=body)
        validator.is_valid(raise_exception=True)

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

        serializer = IsReadyResponseSerializer(response)
        logger.debug(f'Returning to {request.user} from is_ready() - {serializer.data}')
        return Response(serializer.data)
    except JSONDecodeError as e:
        response = {'validation_error': 'JSON parsing error - ' + str(e)}
        serializer = ValidationErrorSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)
    except ValidationError as e:
        response = {'validation_error': str(e)}
        serializer = ValidationExceptionSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        response = {'exception': str(e)}
        serializer = ExceptionResponseSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    request=None,
    responses={
        200: GenericResponseSerializer,
        400: PolymorphicProxySerializer(
            component_name='MultipleErrorResponse',
            serializers=[
                ValidationExceptionSerializer,
                ValidationErrorSerializer,
                ErrorResponseSerializer,
            ],
            resource_type_field_name=None
        ),
        500: ExceptionResponseSerializer
    },
    description="Run a calibration"
)
@api_view(['POST'])
def run_calibration(request):
    try:
        print('user', request.user)

        body = json.loads(request.body or '{}')
        logger.debug(f'run_calibration() request from {request.user} - {body}')

        validator = CalibrationRunValidator(data=body)
        validator.is_valid(raise_exception=True)

        calibration_run_id = validator.data.get('calibration_run_id')

        run, errorReturn = get_run(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn

        messages, config_file = ngen_cal_input.ready_to_run(run, build=True)
        print('config file', config_file)

        # TODO Normally, we return if not ready, but for testing, we'll skip this test
        # if messages:
        #     return JsonError(f'Calibration Run {calibration_run_id} is not ready')

        # Save the latest git hash or ngen and ngen-cal
        run.ngen_commit_hash = Repo(NGEN_REPO_ROOT).head.object.hexsha
        run.ngen_cal_commit_hash = Repo(NGEN_CAL_REPO_ROOT).head.object.hexsha
        run.save()

        message = create_input.create_input(config_file)
        if message:
            return ResponseError(f'Error from create_input - {message}')

        response = {'message': f'Calibration Run {run.id} has been submitted', 'calibration_run_id': calibration_run_id,
                    'status': run.status.name}
        serializer = GenericResponseSerializer(response)
        logger.debug(f'Returning to {request.user} from run_calibration() - {serializer.data}')
        return Response(serializer.data)
    except JSONDecodeError as e:
        response = {'validation_error': 'JSON parsing error - ' + str(e)}
        serializer = ValidationErrorSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)
    except ValidationError as e:
        response = {'validation_error': str(e)}
        serializer = ValidationExceptionSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        response = {'exception': str(e)}
        serializer = ExceptionResponseSerializer(response)
        logger.exception(e)
        return Response(serializer.data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# This is just a test endpoint to trigger read_output()
@api_view(['GET', 'POST'])
def test_read_output(request):
    data = json.loads(request.body or '{}')
    calibration_run_id = data.get('calibration_run_id')
    optimization_name = data.get('optimization')
    username = data.get('user')

    run, errorReturn = get_run(calibration_run_id, request.user, status=[StatusEnum.DONE])
    # if errorReturn:
    #     return errorReturn
    if not run:
        # create some dummies
        gage = Gage(gage_id='01123000')
        optimization = Optimization(name=optimization_name)
        owner = get_user_model()(username=username)
        objective_function = Metric(name='kge')
        run = CalibrationRun(optimization=optimization, ngen_formulation_name='cfe_noah', gage=gage,
                             objective_function=objective_function, owner=owner)

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
        print(f'Directory {gage_dir} does not exist or is not a directory')

    metrics_iteration_filename = f'{run.gage.gage_id}_metrics_iteration.csv'
    objective_log_best_filename = f'{run.gage.gage_id}_objective_log.txt'
    realization_filename = f'{run.gage.gage_id}_realization_config_bmi_calib.json'
    run.realization_filename = realization_filename
    run.save()  # TODO Need to save this in a transaction with all the other objects

    find_worker_directories(run, os.path.join(gage_dir, 'Output/Calibration_Run'), metrics_iteration_filename, objective_log_best_filename)


def find_worker_directories(run, gage_dir, metrics_iteration_filename, objective_log_best_filename):
    pattern = re.compile(r'^ngen_\w*_worker$')

    for worker_name in os.listdir(gage_dir):
        worker_path = os.path.join(gage_dir, worker_name)
        # Check if it's a directory and matches the pattern
        if os.path.isdir(worker_path) and pattern.match(worker_name):
            process_metrics_iteration(run, worker_path, metrics_iteration_filename, objective_log_best_filename)


def process_metrics_iteration(run, worker_path, metrics_iteration_file, objective_log_best_filename):
    metrics_iteration_file = os.path.join(worker_path, metrics_iteration_file)
    objective_log_best_file = os.path.join(worker_path, objective_log_best_filename)
    if not os.path.exists(metrics_iteration_file):
        raise Exception(f'{metrics_iteration_file} does not exist')
    if not os.path.exists(objective_log_best_file):
        raise Exception(f'{objective_log_best_file} does not exist')

    # Get the best iteration number
    last_line = read_last_line(objective_log_best_file)
    best_iteration = int(last_line.split(',')[2])

    worker_name = os.path.basename(worker_path)

    with open(metrics_iteration_file) as file:
        reader = csv.DictReader(file)
        # iteration,objFunVal,Corr,MAE,RMSE,RSR,PBIAS,NSE,NSELog,NSEWt,KGE,POD,FAR,CSI,FBIAS,HSEG_FDC,MSEG_FDC,LSEG_FDC
        row_dict: Dict[str, str]
        for row_dict in reader:
            # print(row_dict)
            # Iteration table has objective value function -- need realization filename
            iteration = int(row_dict['iteration'])
            best = iteration == best_iteration
            iteration = Iteration.objects.create(calibration_run=run,iteration_num=iteration, worker=worker_name, calibration_output_variable_value=row_dict['objFunVal'], best=best)
            for metric_name in row_dict:
                if metric_name == 'iteration' or metric_name == 'objFunVal':
                    continue
                metric = Metric.objects.filter(name=metric_name).first()
                if not metric:
                    print("Could not find metric", metric_name)
                    continue
                # print('metric_name:', metric_name)
                value = float(row_dict[metric_name])
                IterationMetric.objects.create(iteration=iteration, metric=metric, metric_value=value)


# Read backwards from the end of the file until we find linefeed.  Then read the line
def read_last_line(filename):
    with open(filename, 'rb') as file:
        # Move the cursor to the end of the file
        file.seek(-2, 2)
        while file.read(1) != b'\n':
            file.seek(-2, 1)
        last_line = file.readline().decode()
        return last_line
