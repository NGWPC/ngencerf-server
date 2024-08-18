import logging
import os

from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.enums import StatusEnum, ForcingSourceEnum, ObservationalSourceEnum
from calibration.models import CalibrationFormulation, Status, CalibrationRun, CalibrationStopCriteria
from calibration.util.calibration_validators import CalibrationRunSerializer, ImportSerializer, \
    ExportResponseSerializer, IsReadyResponseSerializer
from calibration.util.file_util import copy_directory, copy_file_to_directory
from calibration.views import ngen_cal_input
from calibration.views.calibration_formulation_views import get_my_modules, get_sloth_parameters, get_modules_from_hydrofabric, validate_modules, \
    validate_formulation, SLOTH, add_sloth_parameters
from calibration.views.calibration_gage_views import save_gage
from calibration.views.calibration_optimization_views import get_user_optimization, validate_optimizations, validate_objective_function, \
    write_optimization_inputs
from calibration.views.calibration_run_views import submit_job
from calibration.views.calibration_tuning_views import get_times, get_parameters_for_export, save_times, validate_parameters, save_output_variable, \
    save_parameters, get_module_data_from_hydrofabric, get_time_range
from calibration.views.common import get_run, ResponseError, handle_exceptions, validate_request, validate_response
from calibration.views.ngen_cal_input import get_main_dir

logger = logging.getLogger(__name__)


@api_view(['POST'])
# @permission_classes([AllowAny])
@handle_exceptions
def import_job(request):
    data = request.data
    logger.debug(f'export() request from {request.user} - {data}')

    validator, error_return = validate_request(ImportSerializer, data)
    if error_return:
        return error_return

    with transaction.atomic():
        run = CalibrationRun.objects.create(is_active=True, owner=request.user, status=Status.objects.get(name=StatusEnum.SAVED.value))

        run_after_import = validator.data.get('run_after_import', False)

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
        run.forcing_dir_path = validator.data.get('forcing_dir_path')
        run.observational_source = validator.data.get('observational_source')
        run.observational_user_filename = validator.data.get('observational_user_filename')
        run.observational_file_path = validator.data.get('observational_file_path')
        run.hydrofabric_gpkg_path = validator.data.get('geopackage')

        main_dir = get_main_dir(run)
        if run.forcing_source == ForcingSourceEnum.UPLOAD.value:
            # Need to copy user-loaded files to our instance directory
            new_forcing_dir = os.path.join(main_dir, 'forcing')
            copy_directory(run.forcing_dir_path, new_forcing_dir)

        if run.observational_source == ObservationalSourceEnum.UPLOAD.value:
            # Need to copy user-loaded files to our instance directory
            new_observational_dir = os.path.join(main_dir, 'observation')
            copy_file_to_directory(run.observational_file_path, new_observational_dir)

        #############################
        # Formulations
        #############################
        get_modules_from_hydrofabric(run)
        # List of module names
        modules = set(validator.data.get('modules'))

        message = validate_modules(run, modules)
        if message:
            return ResponseError(message)

        if modules:
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

        if modules:
            get_module_data_from_hydrofabric(run, modules)

        calibration_times = validator.data.get('calibration_times')
        validation_times = validator.data.get('validation_times')

        run.automatic_validation = validator.data.get('automatic_validation')
        save_times(run, calibration_times, validation_times)

        output_variable_to_calibrate = validator.data.get('output_variable_to_calibrate')
        parameters = validator.data.get('parameters')

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

        if optimization_name and optimization_inputs:
            optimization, message = validate_optimizations(run, optimization_name, optimization_inputs)
            if message:
                return ResponseError(message)
            write_optimization_inputs(run, optimization, optimization_inputs)

        message = validate_objective_function(run, objective_function_name, streamflow_threshold, peak_flow_threshold)
        if message:
            return ResponseError(message)

        run.plot_frequency = validator.data.get('plot_frequency')
        run.streamflow_threshold = streamflow_threshold
        run.peak_flow_threshold = peak_flow_threshold

        if stop_criteria:
            # I'm assuming for now that there is just one CalibrationStopCriteria for this run, but that might change in the future
            CalibrationStopCriteria.objects.update_or_create(calibration_run=run, defaults={"value": stop_criteria})

        run.save()

        imported_and_submitted = 'imported'

        errors, config_file = ngen_cal_input.ready_to_run(run)

        if run_after_import:
            if not errors:
                submit_job(run, config_file=config_file)
                imported_and_submitted = 'imported and submitted'

        response = {'message': f'Calibration Run {run.id} {imported_and_submitted}'}
        if errors:
            response['errors'] = errors

        response_validator, error_response = validate_response(IsReadyResponseSerializer, response)
        if error_response:
            return error_response

        logger.debug(f'Returning to {request.user} from import_job() - {response_validator.data}')
        return Response(response_validator.data)


@api_view(['POST'])
# @permission_classes([AllowAny])
@handle_exceptions
def export_job(request):
    data = request.data

    logger.debug(f'export() request from {request.user} - {data}')

    validator, error_return = validate_request(CalibrationRunSerializer, data)
    if error_return:
        return error_return

    calibration_run_id = validator.data.get('calibration_run_id')

    export_file = {}

    # TODO We should only allow DONE
    run, errorReturn = get_run(calibration_run_id, request.user)
    if errorReturn:
        return errorReturn

    metadata = {'source_calibration_run_id': run.id, 'run_date': run.run_date, 'status': run.status.name}
    export_file['metadata'] = metadata
    export_file['gage_id'] = run.gage.gage_id if run.gage else None
    export_file['forcing_source'] = run.forcing_source if run.forcing_source else None
    export_file['forcing_user_dir'] = run.forcing_user_dir
    export_file['forcing_dir_path'] = run.forcing_dir_path
    export_file['observational_source'] = run.observational_source
    export_file['observational_file_path'] = run.observational_file_path
    export_file['geopackage'] = run.hydrofabric_gpkg_path
    # export_file['realization_filename'] = run.realization_filename
    export_file['formulation_name'] = run.user_formulation_name
    export_file['modules'] = get_my_modules(run)
    export_file['use_sloth'] = run.use_sloth
    if run.use_sloth:
        export_file['sloth_parameters'] = get_sloth_parameters(run)
    export_file['automatic_validation'] = run.automatic_validation
    calibration_times, validation_times = get_times(run)
    export_file['calibration_times'] = calibration_times
    export_file['validation_times'] = validation_times
    output_variable_to_calibrate = {
        'module': run.module_output_variable.calibration_formulation.name,
        'name': run.module_output_variable.name
    } if run.module_output_variable else {}
    time_range = get_time_range(run)
    export_file['time_range'] = time_range if time_range else {}

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

    messages, _ = ngen_cal_input.ready_to_run(run)
    metadata['messages'] = messages

    print('export', export_file)

    response_validator, error_response = validate_response(ExportResponseSerializer, export_file)
    if error_response:
        return error_response

    logger.debug(f'Returning to {request.user} from export() - {response_validator.data}')
    return Response(response_validator.data)
