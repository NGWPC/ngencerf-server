import json
import logging
from json import JSONDecodeError

from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from calibration.enums import CalibrationRunType, StatusEnum
from calibration.models import CalibrationFormulation, Status, CalibrationRun, CalibrationStopCriteria
from calibration.util.calibration_validators import ValidationErrorSerializer, ValidationExceptionSerializer, ExceptionResponseSerializer, \
    CalibrationRunValidator, ExportResponseValidator, ImportValidator, GenericMessageResponseSerializer
from calibration.views.calibration_formulation_views import get_my_modules, get_sloth_parameters, get_modules_from_hydrofabric, validate_modules, \
    validate_formulation, SLOTH, add_sloth_parameters
from calibration.views.calibration_gage_views import save_gage
from calibration.views.calibration_optimization_views import get_user_optimization, validate_optimizations, validate_objective_function, \
    write_optimization_inputs
from calibration.views.calibration_tuning_views import get_times, get_parameters_for_export, save_times, validate_parameters, save_output_variable, \
    save_parameters, get_module_data_from_hydrofabric, get_time_range
from calibration.views.common import get_run, ResponseError

logger = logging.getLogger(__name__)


@api_view(['POST'])
# @permission_classes([AllowAny])
def import_job(request):
    try:
        print('user', request.user)
        body = json.loads(request.body or '{}')
        logger.debug(f'export() request from {request.user} - {body}')

        validator = ImportValidator(data=body)
        print('body', body)
        validator.is_valid(raise_exception=True)

        with transaction.atomic():
            run = CalibrationRun.objects.create(is_active=True, owner=request.user, status=Status.objects.get(name=StatusEnum.SAVED.value))

            #############################
            # Gage
            #############################
            gage_id = validator.data.get('gage_id')
            if gage_id:
                gage = save_gage(run, gage_id)
                if not gage:
                    return ResponseError("Gage '{}' does not exist".format(gage_id), status.HTTP_404_NOT_FOUND)

            run.forcing_source = validator.data.get('forcing_source')
            run.forcing_user_dir = validator.data.get('forcing_user_dir')
            run.observational_source = validator.data.get('observational_source')
            run.observational_user_filename = validator.data.get('observational_user_filename')
            # TODO User needs to upload or we get from Hydro

            # TODO Need to get Geopackage

            #############################
            # Formulations
            #############################
            get_modules_from_hydrofabric(run)
            # List of module names
            modules = set(validator.data.get('modules'))

            message = validate_modules(run, modules)
            if message:
                return ResponseError(message)

            if not validate_formulation(run, modules):
                return ResponseError(f'Invalid formulation -  {modules}')

            run.user_formulation_name = validator.data.get('formulation_name')

            run.use_sloth = validator.data.get('use_sloth')
            sloth_parameters = validator.data.get('sloth_parameters')
            if run.use_sloth:
                modules.add(SLOTH)
                if not sloth_parameters:
                    return ResponseError(f"If 'use_sloth' is True, you must enter {SLOTH} parameters")
            else:
                if sloth_parameters:
                    return ResponseError(f"You must indicate 'use_sloth' is True to allow {SLOTH} parameters to be specified")

            # Create any new formulations
            for name in modules:
                CalibrationFormulation.objects.update_or_create(calibration_run=run, name=name, defaults={'used_by_calibration_run': True})

            message = add_sloth_parameters(run, sloth_parameters)
            if message:
                return ResponseError(message)

            #############################
            # Tuning
            #############################
            # Get the list of modules for this Run
            modules = CalibrationFormulation.objects.filter(calibration_run=run, used_by_calibration_run=True)

            get_module_data_from_hydrofabric(run, modules)

            automatic_validation = validator.data.get('automatic_validation')
            calibration_times = validator.data.get('calibration_times')
            validation_times = validator.data.get('validation_times')
            output_variable_to_calibrate = validator.data.get('output_variable_to_calibrate')
            parameters = validator.data.get('parameters')

            save_times(run, automatic_validation, calibration_times, validation_times)

            # TODO Change logic for run_type - I don't think we need this field at all
            run.run_type = 'calib'

            message = validate_parameters(run, parameters)
            if message is not None:
                return ResponseError(message)

            message = save_output_variable(run, output_variable_to_calibrate)
            if message is not None:
                return ResponseError(message)

            save_parameters(run, parameters)

            #############################
            # Optimization
            #############################

            optimization_name = validator.data.get('optimization')
            objective_function_name = validator.data.get('objective_function')
            streamflow_threshold = validator.data.get('streamflow_threshold')
            peak_flow_threshold = validator.data.get('peak_flow_threshold')
            optimization_inputs = validator.data.get('optimization_inputs')
            stop_criteria = validator.data.get('stop_criteria')

            if optimization_inputs and not optimization_name:
                return ResponseError('Optimization inputs cannot be specified without an optimization name')

            optimization, message = validate_optimizations(run, optimization_name, optimization_inputs)
            if message:
                return ResponseError(message)

            message = validate_objective_function(run, objective_function_name, streamflow_threshold, peak_flow_threshold)
            if message:
                return ResponseError(message)

            run.plot_frequency = validator.data.get('plot_frequency')
            run.streamflow_threshold = streamflow_threshold
            run.peak_flow_threshold = peak_flow_threshold

            # I'm assuming for now that there is just one CalibrationStopCriteria for this run, but that might change in the future
            CalibrationStopCriteria.objects.update_or_create(calibration_run=run, defaults={"value": stop_criteria})

            write_optimization_inputs(run, optimization, optimization_inputs)

            run.save()

            # TODO Need another flag to determine if we submit right away.
            # When we submit is when we'll set the run_date and commit hashes

            response = {'message': f'Calibration Run {run.id} submitted'}
            serializer = GenericMessageResponseSerializer(data=response)
            if not serializer.is_valid():
                return ResponseError(f'Data format error returning from import_job() - {serializer.errors}',
                                     httpStatus=status.HTTP_500_INTERNAL_SERVER_ERROR)

            logger.debug(f'Returning to {request.user} from import_job() - {serializer.data}')
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


@api_view(['POST'])
# @permission_classes([AllowAny])
def export_job(request):
    try:
        print('user', request.user)
        body = json.loads(request.body or '{}')
        logger.debug(f'export() request from {request.user} - {body}')

        validator = CalibrationRunValidator(data=body)
        validator.is_valid(raise_exception=True)

        calibration_run_id = validator.data.get('calibration_run_id')

        export_file = {}

        # TODO We should only allow DONE
        run, errorReturn = get_run(calibration_run_id, request.user)
        if errorReturn:
            return errorReturn

        export_file['gage_id'] = run.gage.gage_id if run.gage else None
        export_file['forcing_source'] = run.forcing_source if run.forcing_source else None
        export_file['forcing_user_dir'] = run.forcing_user_dir
        export_file['observational_source'] = run.observational_source
        export_file['observational_user_filename'] = run.observational_user_filename
        export_file['realization_filename'] = run.realization_filename
        # TODO Figure out how to get forcing and obs
        export_file['formulation_name'] = run.user_formulation_name
        export_file['modules'] = get_my_modules(run)
        export_file['use_sloth'] = run.use_sloth
        if run.use_sloth:
            export_file['sloth_parameters'] = get_sloth_parameters(run)
        automatic_validation = run.run_type == CalibrationRunType.VALID_BEST.value
        export_file['automatic_validation'] = automatic_validation
        calibration_times, validation_times = get_times(run, automatic_validation)
        export_file['calibration_times'] = calibration_times
        export_file['validation_times'] = validation_times
        output_variable_to_calibrate = {
            'module': run.module_output_variable.calibration_formulation.name,
            'name': run.module_output_variable.name
        } if run.module_output_variable else None
        export_file['time_range'] = get_time_range(run)

        export_file['output_variable_to_calibrate'] = output_variable_to_calibrate
        # Get the list of modules for this Run
        modules = CalibrationFormulation.objects.filter(calibration_run=run, used_by_calibration_run=True)
        # For each module, get the Parameters and Output Variables
        parameters = get_parameters_for_export(modules)
        export_file['parameters'] = parameters
        export_file['objective_function'] = run.objective_function.name if run.objective_function else None
        export_file['streamflow_threshold'] = run.streamflow_threshold
        export_file['peak_flow_threshold'] = run.peak_flow_threshold
        optimization, optimization_inputs = get_user_optimization(run)
        export_file['optimization'] = optimization
        export_file['optimization_inputs'] = optimization_inputs
        export_file['plot_frequency'] = run.plot_frequency

        # Get stop criteria
        calibration_stop_criteria = CalibrationStopCriteria.objects.filter(calibration_run=run).first()
        stop_criteria = calibration_stop_criteria.value if calibration_stop_criteria else None
        export_file['stop_criteria'] = stop_criteria

        export_file['run_date'] = run.run_date

        print('export', export_file)
        export_file = {key: value for key, value in export_file.items() if value not in [None, '', [], {}]}

        serializer = ExportResponseValidator(data=export_file)
        if not serializer.is_valid():
            return ResponseError(f'Data format error returning from export() - {serializer.errors}',
                                 httpStatus=status.HTTP_500_INTERNAL_SERVER_ERROR)

        logger.debug(f'Returning to {request.user} from export() - {serializer.data}')
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
