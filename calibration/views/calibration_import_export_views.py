import base64
import logging
import os

from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from calibration.enums import StatusEnum, ForcingSourceEnum, ObservationalSourceEnum
from calibration.models import CalibrationFormulation, Status, CalibrationRun, CalibrationStopCriteria, ForcingSource, ObservationalSource
from calibration.util import ngen_locations
from calibration.util.calibration_validators import CalibrationRunSerializer, ImportResponseSerializer, ImportSerializer, \
    ExportResponseSerializer, IsReadyResponseSerializer, ErrorResponseSerializer
from calibration.util.file_util import copy_directory, copy_file_to_directory
from calibration.util.geopkg import gpkg_to_png_selected_layers
from calibration.util.ngen_locations import get_forcing_dir_for_job, get_observational_dir_for_job, \
    get_geopackage_dir_for_job, get_geopackage_file_for_job
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

logger = logging.getLogger(__name__)


@extend_schema(
    request=ImportSerializer,
    responses={
        200: IsReadyResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: ErrorResponseSerializer
    },
    description="Import a job"
)
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

        warnings = []

        #############################
        # Gage
        #############################
        gage_id = validator.data.get('gage_id')
        if gage_id:
            gage = save_gage(run, gage_id)
            if not gage:
                return ResponseError("Gage '{}' does not exist".format(gage_id), status.HTTP_404_NOT_FOUND)

        forcing_source_name = validator.data.get('forcing_source')
        run.forcing_source = ForcingSource.objects.get(name=forcing_source_name) if forcing_source_name else None
        run.forcing_hydrofabric_dir_path = validator.data.get('forcing_hydrofabric_dir_path')

        observational_source_name = validator.data.get('observational_source')
        run.observational_source = ObservationalSource.objects.get(name=observational_source_name) if observational_source_name else None
        run.observational_hydrofabric_file_path = validator.data.get('observational_hydrofabric_file_path')

        run.geopackage_hydrofabric_path = validator.data.get('geopackage_path_from_hydrofabric')
        geopackage_user_uploaded_file_path = validator.data.get('geopackage_user_uploaded_file_path')
        if os.path.exists(geopackage_user_uploaded_file_path):
            # Copy from original location to our job-specific path
            copy_file_to_directory(geopackage_user_uploaded_file_path, get_geopackage_dir_for_job(run))

        if run.forcing_source and run.forcing_source.name == ForcingSourceEnum.UPLOAD.value:
            forcing_user_uploaded_dir_path = validator.data.get('forcing_user_uploaded_dir_path')
            if forcing_user_uploaded_dir_path and os.path.exists(forcing_user_uploaded_dir_path):
                # Copy from original location to our job-specific path
                copy_directory(forcing_user_uploaded_dir_path, get_forcing_dir_for_job(run))
            else:
                warnings.append(f"Unable to access user uploaded forcing data from '{run.forcing_hydrofabric_dir_path}'")

        if run.observational_source and run.observational_source.name == ObservationalSourceEnum.UPLOAD.value:
            observational_user_uploaded_file_path = validator.data.get('observational_user_uploaded_file_path')
            if observational_user_uploaded_file_path and os.path.exists(observational_user_uploaded_file_path):
                # Copy from original location to our job-specific path
                copy_file_to_directory(observational_user_uploaded_file_path, get_observational_dir_for_job(run))
            else:
                warnings.append(f"Unable to access user uploaded observational data from '{run.observational_hydrofabric_file_path}'")

    #############################
    # Formulations
    #############################
    get_modules_from_hydrofabric(run)
    # List of module names
    modules_list = validator.data.get('modules')
    module_names = set(modules_list) if modules_list else set()

    message = validate_modules(run, module_names)
    if message:
        return ResponseError(message)

    if module_names:
        if not validate_formulation(run, module_names):
            return ResponseError(f'Invalid formulation -  {module_names}')

    run.user_formulation_name = validator.data.get('formulation_name')

    run.use_sloth = validator.data.get('use_sloth')
    sloth_parameters = validator.data.get('sloth_parameters')
    if run.use_sloth:
        if module_names:
            module_names.add(SLOTH)
    else:
        if sloth_parameters:
            return ResponseError(f"You must indicate 'use_sloth' is True to allow {SLOTH} parameters to be specified")

    # Create any new formulations
    for name in module_names:
        CalibrationFormulation.objects.update_or_create(calibration_run=run, name=name, defaults={'used_by_calibration_run': True})

    if sloth_parameters:
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

    run.automatic_validation = validator.data.get('automatic_validation')

    calibration_times = validator.data.get('calibration_times')
    validation_times = validator.data.get('validation_times')
    if not run.automatic_validation and validation_times:
        return ResponseError('validation_times cannot be specified unless automatic_validation is True')

    save_times(run, calibration_times, validation_times)

    output_variable_to_calibrate = validator.data.get('output_variable_to_calibrate')
    parameters = validator.data.get('parameters')
    if parameters and not modules:
        return ResponseError('Parameters cannot be specified without modules')

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

    if not optimization_name:
        if optimization_inputs:
            return ResponseError('Optimization inputs cannot be specified without an optimization name')
    else:
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
    errors.extend(warnings)

    if run_after_import:
        errors, config_file = ngen_cal_input.ready_to_run(run)
        if not errors:
            submit_job(run, config_file=config_file)
            imported_and_submitted = 'imported and submitted'

    response = {'message': f'Calibration Run {run.id} {imported_and_submitted}', 'calibration_run_id': run.id}
    if errors:
        response['errors'] = errors

    response_validator, error_response = validate_response(ImportResponseSerializer, response)
    if error_response:
        return error_response

    logger.debug(f'Returning to {request.user} from import_job() - {response_validator.data}')
    return Response(response_validator.data)


@extend_schema(
    request=CalibrationRunSerializer,
    responses={
        200: ExportResponseSerializer,
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation error or parsing error"
        ),
        500: ErrorResponseSerializer
    },
    description="Export a job"
)
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

    run, errorReturn = get_run(calibration_run_id, request.user)
    if errorReturn:
        return errorReturn

    calibration_run_data = load_calibration_run_data(run, export=True)

    errors, _ = ngen_cal_input.ready_to_run(run)
    if errors:
        calibration_run_data['metadata']['errors'] = errors

    response_validator, error_response = validate_response(ExportResponseSerializer, calibration_run_data)
    if error_response:
        return error_response
    logger.debug(f'Returning to {request.user} from export() - {response_validator.data}')

    return Response(response_validator.data)


def load_calibration_run_data(run, export: bool = None):
    if export is None:
        export = False

    calibration_run_data = {}

    time_range = get_time_range(run)
    # Since we're not using a serializer for metadata, we need to serialize the datetime objects manually
    time_range['start_time'] = time_range['start_time'].isoformat()
    time_range['end_time'] = time_range['end_time'].isoformat()
    module_objects = CalibrationFormulation.objects.filter(calibration_run=run, used_by_calibration_run=True)

    if export:
        metadata = {'source_calibration_run_id': run.id, 'time_range': time_range}
        calibration_run_data['metadata'] = metadata

        calibration_run_data['run_after_import'] = False

        calibration_run_data['gage_id'] = run.gage.gage_id if run.gage else None
        calibration_run_data['parameters'] = get_parameters_for_export(module_objects)
        # There fields are exported so we can import them later
        # Note that it makes sense to export the unsubsetted Hydrofabric files
        # We will subset them again with the new job, when it is imported

        # Only one of these geopackage paths should be populated
        calibration_run_data['geopackage_path_from_hydrofabric'] = run.geopackage_hydrofabric_path
        calibration_run_data['geopackage_user_uploaded_file_path'] = get_geopackage_file_for_job(run)

        # Foe export, we need these paths only for user-uploaded data, so we can copy the data to the newly imported job
        user_uploaded_observational_file = ngen_locations.get_observational_file_for_job(run)
        calibration_run_data['observational_user_uploaded_file_path'] = user_uploaded_observational_file if user_uploaded_observational_file and os.path.exists(
            user_uploaded_observational_file) else None
        user_uploaded_forcing_dir = ngen_locations.get_forcing_dir_for_job(run)
        calibration_run_data['forcing_user_uploaded_dir_path'] = user_uploaded_forcing_dir if user_uploaded_forcing_dir and os.path.exists(user_uploaded_forcing_dir) else None

    else:
        calibration_run_data['calibration_run_id'] = run.id
        calibration_run_data['time_range'] = time_range
        calibration_run_data['gage'] = {'gage_id': run.gage.gage_id, 'agency': run.gage.agency, 'station_name': run.gage.station_name,
                                        'latitude': run.gage.latitude,
                                        'longitude': run.gage.longitude, 'altitude': run.gage.altitude} if run.gage else None
        calibration_run_data['status'] = run.status.name

        # For the UI, we don't need the Geopackage file, but rather, the full map
        # TODO This should be the map file, which might need to be regenerated
        geopackage_path = run.geopackage_hydrofabric_path if run.geopackage_hydrofabric_path and os.path.exists(run.geopackage_hydrofabric_path) else get_geopackage_file_for_job(run)
        if geopackage_path and os.path.exists(geopackage_path):
            geopackage_png = gpkg_to_png_selected_layers(geopackage_path)
            base64_str = base64.b64encode(geopackage_png.getvalue()).decode('utf-8')
            geopackage_image_url = f'data:image/png;base64,{base64_str}'
            calibration_run_data['geopackage_image_url'] = geopackage_image_url

    #############################
    # Gage
    #############################

    calibration_run_data['forcing_source'] = run.forcing_source.name if run.forcing_source else None
    calibration_run_data['forcing_hydrofabric_dir_path'] = run.forcing_hydrofabric_dir_path

    calibration_run_data['observational_source'] = run.observational_source.name if run.observational_source else None
    calibration_run_data['observational_hydrofabric_file_path'] = run.observational_hydrofabric_file_path

    #############################
    # Formulation
    #############################
    calibration_run_data['formulation_name'] = run.user_formulation_name
    calibration_run_data['modules'] = get_my_modules(run)
    calibration_run_data['use_sloth'] = run.use_sloth
    if run.use_sloth:
        calibration_run_data['sloth_parameters'] = get_sloth_parameters(run)

    #############################
    # Tuning
    #############################
    calibration_run_data['automatic_validation'] = run.automatic_validation

    calibration_times, validation_times = get_times(run)
    calibration_run_data['calibration_times'] = calibration_times
    calibration_run_data['validation_times'] = validation_times

    output_variable_to_calibrate = {
        'module': run.module_output_variable.calibration_formulation.name,
        'name': run.module_output_variable.name
    } if run.module_output_variable else {}

    #############################
    # Optimization
    #############################
    calibration_run_data['output_variable_to_calibrate'] = output_variable_to_calibrate
    calibration_run_data['objective_function'] = run.objective_function.name if run.objective_function else None
    calibration_run_data['streamflow_threshold'] = run.streamflow_threshold
    calibration_run_data['peak_flow_threshold'] = run.peak_flow_threshold
    optimization, optimization_inputs = get_user_optimization(run)
    calibration_run_data['optimization'] = optimization
    calibration_run_data['optimization_inputs'] = optimization_inputs
    calibration_run_data['plot_frequency'] = run.plot_frequency

    # Get stop criteria
    calibration_stop_criteria = CalibrationStopCriteria.objects.filter(calibration_run=run).first()
    stop_criteria = calibration_stop_criteria.value if calibration_stop_criteria else None
    calibration_run_data['stop_criteria'] = stop_criteria

    # calibration_run_data['run_date'] = run.run_date

    if not export and run.status.name in [StatusEnum.RUNNING.value, StatusEnum.DONE.value]:
        # Other stuff we need for Running/Done jobs
        pass

    print('export', calibration_run_data)

    return calibration_run_data
