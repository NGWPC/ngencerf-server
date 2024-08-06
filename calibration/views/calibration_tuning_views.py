import csv
import json
import logging
import os
from datetime import MAXYEAR as MAXYEAR
from datetime import MINYEAR as MINYEAR
from datetime import datetime, timezone
from json.decoder import JSONDecodeError

from datetimerange import DateTimeRange
from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.enums import CalibrationRunType
from calibration.models import CalibrationFormulation, ModuleOutputVariable, CalibrationTuneParameter
from calibration.util.calibration_validators import CalibrationRunValidator, SaveTuningRequestValidator, ModuleDataHydrofabricListValidator, \
    LoadTuningResponseSerializer, GenericResponseSerializer, ErrorResponseSerializer
from calibration.views import ngen_cal_input
from calibration.views.common import get_run, ResponseError

logger = logging.getLogger(__name__)

MIN_TIME = datetime(MAXYEAR, 12, 31, 11, 59, 59).replace(tzinfo=timezone.utc)
MAX_TIME = datetime(MINYEAR, 1, 1, 0, 0, 0).replace(tzinfo=timezone.utc)

# For testing
module_sample_data = {"modules_data": [
    {
        "name": "Noah-OWP-Modular",
        "module_output_variables": [
            {
                "name": "QINSUR",
                "description": "description of variable",
            },
            {
                "name": "ETRAN",
                "description": "description of variable",
            },
            {
                "name": "QSEVA",
                "description": "description of variable",
            },
        ],
        "module_parameters": [
            {
                "name": "parameter1",
                "data_type": "double",
                "description": "description of variable",
            },

            {
                "name": "parameter2",
                "data_type": "double",
                "description": "description of variable",
            },
            {
                "name": "parameter3",
                "data_type": "double",
                "description": "description of variable",
                "units": "m/s",
                "initial_value": 0.0,
                "min": 0.0,
                "max": 0.0
            }

        ]
    },
]
}


@extend_schema(
    request=CalibrationRunValidator,
    responses={
        200: LoadTuningResponseSerializer,
        400: ErrorResponseSerializer
    },
    parameters=[
        OpenApiParameter(name='calibration_run_id', description='ID of the calibration run', required=True, type=int)
    ],
    description="Load tuning tab data"
)
@api_view(['GET', 'POST'])
# @login_required
def load_tuning_tab(request):
    try:
        print('user', request.user)
        if request.method == 'POST':
            data = json.loads(request.body or '{}')
        else:
            data = request.GET

        logger.debug(f'load_tuning_tab() request from {request.user} - {data}')

        validator = CalibrationRunValidator(data=data)
        validator.is_valid(raise_exception=True)

        calibration_run_id = validator.data.get('calibration_run_id')

        run, errorReturn = get_run(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn

        automatic_validation = run.run_type == CalibrationRunType.VALID_BEST.value
        validation_times = {}
        calibration_times = {}

        # These are all or nothing.  So if this first one exists, we'll assume they all do
        if run.calibration_start_period:
            calibration_times['simulation_start_time'] = run.calibration_start_period
            calibration_times['simulation_end_time'] = run.calibration_end_period
            calibration_times['calibration_start_time'] = run.calibration_eval_start_period
            calibration_times['calibration_end_time'] = run.calibration_eval_end_period
        if automatic_validation and run.validation_start_period:
            validation_times['simulation_start_time'] = run.validation_start_period
            validation_times['simulation_end_time'] = run.validation_end_period
            validation_times['validation_start_time'] = run.validation_eval_start_period
            validation_times['validation_end_time'] = run.validation_eval_end_period

        output_variable_to_calibrate = {
            'module': run.module_output_variable.calibration_formulation.name,
            'name': run.module_output_variable.name
        } if run.module_output_variable else {}

        # Get the list of modules for this Run
        modules = CalibrationFormulation.objects.filter(calibration_run=run, used_by_calibration_run=True)

        module_list = []
        if modules:
            # Only do this if modules have been saved in the formulation tab

            # print('calling hydrofabric with', modules)
            get_module_data_from_hydrofabric(run, modules)

            # For each module, get the Parameters and Output Variables
            for m in modules:
                parameters = list(CalibrationTuneParameter.objects.filter(calibration_formulation=m)
                                  .only('name', 'minimum', 'maximum', 'initial_value', 'data_type', 'description')
                                  .values('name', 'minimum', 'maximum', 'initial_value', 'data_type', 'description'))

                # parameter_list.extend(parameters)

                module_entry = {'name': m.name,
                                'output_variables': list(m.output_variables.all().only('name', 'description').values('name', 'description')),
                                'parameters': parameters}
                module_list.append(module_entry)

        # Get data range intersection of observational and forcing data if we don't already have it
        if (run.observational_file_path and run.forcing_dir_path
                and (not run.time_range_start or not run.time_range_end)):
            daterange = get_date_range_intersection(run.observational_file_path, run.forcing_dir_path)
            run.time_range_start = daterange.start_datetime
            run.time_range_end = daterange.end_datetime
            run.save()

            ngen_cal_input.ready_to_run(run)

        response = {'calibration_run_id': run.id, 'status': run.status.name,
                    'modules': module_list,
                    'calibration_times': calibration_times,
                    'validation_times': validation_times, 'automatic_validation': automatic_validation,
                    'time_range': {'start_time': run.time_range_start, 'end_time': run.time_range_end},
                    'output_variable_to_calibrate': output_variable_to_calibrate}
        serializer = LoadTuningResponseSerializer(response)
        logger.debug(f'load_tuning_tab() request from {request.user} - {serializer.data}')

        return Response(serializer.data)
    except JSONDecodeError as e:
        logger.exception(e)
        return Response({'validation_error': 'JSON parsing error - ' + str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except serializers.ValidationError as e:
        logger.exception(e)
        return Response({'validation_error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception(e)
        return Response({'exception': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# @login_required()
def get_module_data_from_hydrofabric(run, modules):
    # Get this from hydrofabric
    # modules_request = {"modules":modules}
    # response = requests.post(settings.HYDROFABRIC_URL, json=modules_request)
    # module_data = response.json()

    validator = ModuleDataHydrofabricListValidator(data=module_sample_data)
    if not validator.is_valid():
        logger.error(validator.errors)
        raise Exception('Module metadata from Hydrofabric is not in the expected format')

    module_data = module_sample_data.get("modules_data")

    # Save the output variables and parameters for each module
    # TODO We need to ensure that the data from Hydrofabric contains all the modules we asked for
    with transaction.atomic():
        for m in module_data:
            # Get the modules object from our list
            module = modules.filter(name=m['name']).first()
            # print('module', module)

            # Save output variables
            outputs = m['module_output_variables']
            o: dict
            for o in outputs:
                ModuleOutputVariable.objects.get_or_create(name=o['name'], calibration_formulation=module,
                                                           defaults={'description': o['description']})
            # Save parameters
            # print('getting parameters for', m)
            parameters = m['module_parameters']
            # print('parameters from Hydro', parameters)
            for p in parameters:
                CalibrationTuneParameter.objects.get_or_create(name=p['name'], calibration_formulation=module,
                                                               defaults={'data_type': p['data_type'],
                                                                         'description': p['description']})

        run.got_module_data_from_hydrofabric = True
        run.save()

    return


@extend_schema(
    request=SaveTuningRequestValidator,
    responses={
        200: GenericResponseSerializer,
        400: ErrorResponseSerializer
    },
    description="Save tuning tab data"
)
@api_view(['POST'])
# @login_required
def save_tuning_tab(request):
    try:
        print('user', request.user)
        body = json.loads(request.body or '{}')
        logger.debug(f'save_tuning_tab() request from {request.user} - {body}')

        validator = SaveTuningRequestValidator(data=body)
        validator.is_valid(raise_exception=True)

        calibration_run_id = validator.data.get('calibration_run_id')
        automatic_validation = validator.data.get('automatic_validation')
        calibration_times = validator.data.get('calibration_times')
        validation_times = validator.data.get('validation_times')
        parameters = validator.data.get('parameters')

        output_variable_to_calibrate = validator.data.get('output_variable_to_calibrate')

        run, errorReturn = get_run(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn

        run.calibration_start_period = datetime.fromisoformat(calibration_times['simulation_start_time']) if calibration_times else None
        run.calibration_end_period = datetime.fromisoformat(calibration_times['simulation_end_time']) if calibration_times else None
        run.calibration_eval_start_period = datetime.fromisoformat(calibration_times['calibration_start_time']) if calibration_times else None
        run.calibration_eval_end_period = datetime.fromisoformat(calibration_times['calibration_end_time']) if calibration_times else None

        if automatic_validation:
            run.validation_start_period = datetime.fromisoformat(validation_times['simulation_start_time']) if validation_times else None
            run.validation_end_period = datetime.fromisoformat(validation_times['simulation_end_time']) if validation_times else None
            run.validation_eval_start_period = datetime.fromisoformat(validation_times['validation_start_time']) if validation_times else None
            run.validation_eval_end_period = datetime.fromisoformat(validation_times['validation_end_time']) if validation_times else None

        # Set the type
        run.run_type = CalibrationRunType.VALID_BEST if automatic_validation else CalibrationRunType.CALIB

        if parameters:
            if not CalibrationTuneParameter.objects.filter(calibration_formulation__calibration_run=run).exists():
                return ResponseError('CalibrationTuneParameters have not been loaded from Hydrofabric')
            # Make sure the parameters we are trying to save exist
            for p in parameters:
                if not CalibrationTuneParameter.objects.filter(name=p['name'], calibration_formulation__name=p['module']).exists():
                    return ResponseError("Invalid parameter '{}' specified for module '{}'".format(p['name'], p['module']))

        # Validate the output_variable_to_calibrate
        if output_variable_to_calibrate:
            module_with_output_variable = CalibrationFormulation.objects.filter(name=output_variable_to_calibrate['module'],
                                                                                calibration_run=run).first()
            if not module_with_output_variable:
                return ResponseError("Module '{}' is not part of calibration run {}".format(output_variable_to_calibrate['module'], run.id))
            module_output_variable = module_with_output_variable.output_variables.all().filter(
                name=output_variable_to_calibrate['name']).first()
            if not module_output_variable:
                return ResponseError("Module output variable '{}' not found in module '{}' for this run".format(
                    output_variable_to_calibrate['name'], output_variable_to_calibrate['module']))

            logger.debug(f'module_output_variable {module_output_variable}')
            run.module_output_variable = module_output_variable

        with transaction.atomic():
            run.save()
            if parameters:
                for p in parameters:
                    (CalibrationTuneParameter.objects
                     .filter(name=p['name'], calibration_formulation__name=p['module'], calibration_formulation__calibration_run=run)
                     .update(minimum=p['minimum'], maximum=p['maximum'], initial_value=p['initial_value']))

        ngen_cal_input.ready_to_run(run)

        response = {'message': f'Calibration Run {run.id} updated', 'calibration_run_id': run.id, 'status': run.status.name}
        serializer = GenericResponseSerializer(response)
        logger.debug(f'Returning to {request.user} from save_tuning_tab() - {serializer.data}')
        return Response(serializer.data)
    except JSONDecodeError as e:
        logger.exception(e)
        return Response({'validation_error': 'JSON parsing error - ' + str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except serializers.ValidationError as e:
        logger.exception(e)
        return Response({'validation_error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception(e)
        return Response({'exception': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Reads a CSV file and gets the date field from the first column.  Then computes the min/max to construct a date range
def get_csv_daterange(file):
    max_time = MAX_TIME
    min_time = MIN_TIME
    with open(file, 'r') as f:
        csv_reader = csv.reader(f, delimiter=',')
        # skip the header
        next(csv_reader, None)
        for row in csv_reader:
            timestamp = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
            max_time = max(max_time, timestamp)
            min_time = min(min_time, timestamp)

    return DateTimeRange(min_time, max_time)


def get_forcing_date_range(forcing_dir_path):
    # dir = '/home/peter.a.kronenberg/ngen-cal-work/forcing/Gage_01123000/'
    # Get all files in the dir
    timerange = None
    for file in os.listdir(forcing_dir_path):
        new_range = get_csv_daterange(os.path.join(forcing_dir_path, file))
        if timerange:
            timerange = timerange.encompass(new_range)
        else:
            timerange = new_range

    return timerange


def get_observation_date_range(observational_filepath):
    # obs_file = '/home/peter.a.kronenberg/ngen-cal-work/observation/01123000_hourly_discharge.csv'
    return get_csv_daterange(observational_filepath)


def get_date_range_intersection(observational_file_path, forcing_dir_path):
    # The get latest start data and the earlier end date
    obs_range = get_observation_date_range(observational_file_path)
    logger.debug(f'obs_range: {obs_range}')
    forcing_range = get_forcing_date_range(forcing_dir_path)
    logger.debug(f'forcing_range: {forcing_range}')
    return obs_range.intersection(forcing_range)
