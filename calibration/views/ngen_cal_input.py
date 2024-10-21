import logging
import re
from datetime import datetime
from pathlib import Path

import toml
from datetimerange import DateTimeRange
from django.db.models import F

from calibration.enums import StatusEnum, ForcingSourceEnum, ObservationalSourceEnum, DataTypeEnum, GeopackageSourceEnum
from calibration.models import CalibrationOptimizationInput, CalibrationStopCriteria, CalibrationSlothParam, \
    CalibrationParameter, OptimizationInput, CalibrationFormulation, CalibrationRun
from calibration.util.file_util import get_single_file
from calibration.util.ngen_locations import CFE_LIB, TOPMD_LIB, SFT_LIB, SLOTH_LIB, SMP_LIB, LASAM_LIB, NOAH_LIB, NGEN_EXE, NOAH_PARAMETER_DIR, \
    PARQUET_DIR, get_forcing_dir_for_job, get_observational_dir_for_job, \
    get_observational_file_for_job, get_geopackage_dir_for_job, \
    get_geopackage_file_for_job, PET_LIB, SNOW17_LIB, SAC_LIB, NWM_RETROSPECTIVE_DIR
from calibration.views.calibration_run_views import subset_by_time_range, subset_directory_by_time_range
from calibration.views.common import CerfException, token_ngen, generate_custom_token, SLOTH

logger = logging.getLogger(__name__)

config_template = {

    "General": {
        "calibration_run_id": 0,
        "ngen_cerf": True,  # Indicate that we came from the ngenCerf server - Always true
        "auth_token": "",
        "basin": "",
        "models": "",

        "formulation": "",
        "run_type": "calib",
        "main_dir": ""
    },

    "Calibration": {
        "optimization_algorithm": "",
        "swarm_size": 0,
        "c1": 0,
        "c2": 0,
        "w": 0,
        "r": 0,
        "objective_function": "",
        "start_iteration": 0,
        "number_iteration": 0,
        # Whether restart calibration from the stopped iteration
        # 0: Not
        # 1: Yes
        # It should be 0 if start_interation entry is 0.
        "restart": 0,
        # TODO Output variable to calibrate is not supported yet by ngen-cal
        "output_variable_to_calibration_module": "",
        "output_variable_to_calibration_name": "",
        "calib_start_period": "",
        "calib_end_period": "",
        "calib_eval_start_period": "",
        "calib_eval_end_period": "",
        # If we're not doing automatic validation, create_input still expects a valid date/time here
        "valid_start_period": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "valid_end_period": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "valid_eval_start_period": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "valid_eval_end_period": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "full_eval_start_period": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "full_eval_end_period": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        # Save streamflow output and plot at the specified iteration
        # These entries are optional and specified with the default values.
        # 1: Filename is distinguished by the iteration number.
        # 0: Filename is same at different iteration, i.e., overwritten by file from last iteration.
        "save_output_iter": 0,
        "save_plot_iter": 0,

        # Iteration interval to save plots
        # This entry is optional and specified with the default value.
        "save_plot_iter_freq": 0,
        "streamflow_threshold": 0,
        "peak_flow_threshold": 0,
        "station_name": "",
        "user_email": "",
    },

    "DataFile": {
        "forcing_dir": "",
        "obs_dir": "",
        "nwmretro_file": "",
        "hydrofab_dir": "",

        # TODO cfe_dir and topmd_dir should be obsolete
        "cfe_dir": "",
        "topmd_dir": "",
        "noah-owp-modular_bmi_dir": "",
        "cfe-s_bmi_dir": "",
        "cfe-x_bmi_dir": "",
        "t-route_bmi_dir": "",
        "topoflow_bmi_dir": "",
        "snow-17_bmi_dir": "",
        "ueb_bmi_dir": "",
        "pet_bmi_dir": "",
        "topmodel_bmi_dir": "",
        "sac-sma_bmi_dir": "",
        "lasam_bmi_dir": "",
        "smp_bmi_dir": "",
        "sft_bmi_dir": "",

        # Not sure what these 2 are for
        "ueb_lib": "",
        "ueb_parameter_dir": "",

        # Static file
        "noah_parameter_dir": NOAH_PARAMETER_DIR,
        # Parquet file - base on domain
        "attributes_file": "",
        # Parameter file, dynamically built based on user input
        "calib_parameter_file": "",
        # TODO Sloth parameter file is not supported by ngen-cal yet
        "sloth_parameter_file": "",
        "lasam_soil_parameter_file": "",
        "lasam_soil_class_file": "",
        "ngen_exe_file": NGEN_EXE,
        "cfe_lib": CFE_LIB,
        "sloth_lib": SLOTH_LIB,
        "topmd_lib": TOPMD_LIB,
        "noah-owp-modular_lib": NOAH_LIB,
        "sft_lib": SFT_LIB,
        "smp_lib": SMP_LIB,
        "lasam_lib": LASAM_LIB,
        "pet_lib": PET_LIB,
        "snow-17_lib": SNOW17_LIB,
        "sac-sma_lib": SAC_LIB
    }
}

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def validate_times(run):
    if run.time_range_start and run.time_range_end:
        time_range = DateTimeRange(run.time_range_start, run.time_range_end)
        if run.calibration_start_period and (run.calibration_start_period not in time_range or run.calibration_end_period not in time_range):
            return f"Calibration simulation times must be contained within the intersection of forcing data and observational data - {time_range}"
        if run.automatic_validation and run.validation_start_period and (
                run.validation_start_period not in time_range or run.validation_end_period not in time_range):
            return f"Validation simulation times must be contained within the intersection of forcing data and observational data - {time_range}"

    return None


def ready_to_run(run: CalibrationRun, build: bool = None):
    config = dict(config_template)
    general = config['General']
    calibration = config['Calibration']
    datafile = config['DataFile']

    errors = []

    if not run:
        raise CerfException('Must pass a run instance to validate')

    general['calibration_run_id'] = run.id
    # general['user'] = run.owner.username
    general['auth_token'] = generate_custom_token(run.owner, token_ngen)

    if not is_missing(run.gage, 'gage_id', errors):
        general['basin'] = run.gage.gage_id
        calibration['station_name'] = run.gage.station_name

        if not is_missing(run.forcing_source, 'forcing source', errors):
            is_forcing_upload = run.forcing_source == ForcingSourceEnum.from_enum(ForcingSourceEnum.UPLOAD)
            if is_forcing_upload:
                forcing_dir = get_forcing_dir_for_job(run)
                if not forcing_dir or not Path(forcing_dir).exists():
                    errors.append('Forcing data must be uploaded')
            elif build:
                # for non-uploaded data, subset the data by time range
                source_dir = run.forcing_hydrofabric_dir_path
                subset_directory_by_time_range(
                    source_dir,
                    get_forcing_dir_for_job(run),
                    DateTimeRange(min(run.calibration_start_period, run.validation_start_period),
                                  max(run.calibration_end_period, run.validation_end_period))
                )

        datafile['forcing_dir'] = get_forcing_dir_for_job(run)

        if not is_missing(run.observational_source, 'observational source', errors):
            is_observational_upload = run.observational_source == ObservationalSourceEnum.from_enum(ObservationalSourceEnum.UPLOAD)
            if is_observational_upload:
                user_uploaded_observational_file = get_single_file(get_observational_dir_for_job(run))
                if not user_uploaded_observational_file:
                    errors.append('Observational data must be uploaded')
                else:
                    # We need to rename the user-uploaded file.
                    observational_file_for_job_path = Path(get_observational_file_for_job(run))
                    # If the user uploaded it with the proper name, no need to rename
                    if user_uploaded_observational_file != observational_file_for_job_path:
                        logger.info(
                            f"Renaming observational file from {str(user_uploaded_observational_file)} to {get_observational_file_for_job(run)}")
                        user_uploaded_observational_file.rename(Path(get_observational_file_for_job(run)))
            elif build:
                # For non-uploaded data, subset the data by time range
                source_file = run.observational_hydrofabric_file_path
                subset_by_time_range(
                    source_file,
                    get_observational_file_for_job(run),
                    DateTimeRange(min(run.calibration_start_period, run.validation_start_period),
                                  max(run.calibration_end_period, run.validation_end_period))
                )

        datafile['obs_dir'] = get_observational_dir_for_job(run)

        if not is_missing(run.geopackage_source, 'geopackage source', errors):
            is_geopackage_upload = run.geopackage_source == GeopackageSourceEnum.from_enum(GeopackageSourceEnum.UPLOAD)
            if is_geopackage_upload:
                user_uploaded_geopackage_file = get_single_file(get_geopackage_dir_for_job(run))
                if not user_uploaded_geopackage_file:
                    errors.append('Geopackage data must be uploaded')
                else:
                    # We need to rename the user-uploaded file.
                    geopackage_file_for_job_path = Path(get_geopackage_file_for_job(run))
                    # If the user uploaded it with the proper name, no need to rename
                    if user_uploaded_geopackage_file != geopackage_file_for_job_path:
                        logger.info(f"Renaming geopackage file from {str(user_uploaded_geopackage_file)} to {get_geopackage_file_for_job(run)}")
                        user_uploaded_geopackage_file.rename(Path(get_geopackage_file_for_job(run)))

                        # For user uploads, use the job-specific location
                    datafile['hydrofab_dir'] = get_geopackage_dir_for_job(run)
            else:
                # For data from Hydrofabric, we use the location that Hydrofabric gave us
                if run.geopackage_hydrofabric_file_path:
                    datafile['hydrofab_dir'] = str(Path(run.geopackage_hydrofabric_file_path).parent)

        nwm_retro = Path(NWM_RETROSPECTIVE_DIR) / f'{run.gage.gage_id}.csv'
        if nwm_retro.exists():
            datafile['nwmretro_file'] = str(nwm_retro)

        error_message = validate_times(run)
        if error_message:
            errors.append(error_message)

        # Need to set parquet file based on domain
        datafile['attributes_file'] = str(Path(PARQUET_DIR) / f'{run.gage.domain.name.lower()}_model_attributes.parquet')

    formulations = CalibrationFormulation.objects.filter(calibration_run=run)

    # Create a dictionary with 'name' as the key and 'bmi_config_path' as the value
    module_dict = {formulation.module.name: formulation.bmi_config_path for formulation in formulations}

    if not is_missing(formulations, 'modules', errors) and not is_missing(run.user_formulation_name, 'formulation name', errors):
        general['formulation'] = run.user_formulation_name
        general['models'] = ', '.join(module_dict.keys())
        if run.use_sloth:
            general['models'] += f', {SLOTH}'

        # Dynamically add keys and values from the module_dict to our config
        for key, value in module_dict.items():
            new_key = key.lower() + '_bmi_dir'
            datafile[new_key] = value

    job_data_dir = run.job_data_dir
    general['main_dir'] = job_data_dir

    if build:
        Path(job_data_dir).mkdir(parents=True, exist_ok=True)

    if any(field is None for field in [run.calibration_start_period, run.calibration_end_period, run.calibration_eval_start_period, run.calibration_eval_end_period]):
        errors.append('calibration_start_period, calibration_end_period, calibration_eval_start_period and calibration_eval_end_period must be specified')
    else:
        calibration.update({
            'calib_start_period': run.calibration_start_period.strftime(DATE_FORMAT),
            'calib_end_period': run.calibration_end_period.strftime(DATE_FORMAT),
            'calib_eval_start_period': run.calibration_eval_start_period.strftime(DATE_FORMAT),
            'calib_eval_end_period': run.calibration_eval_end_period.strftime(DATE_FORMAT),
        })

    if run.automatic_validation:
        if any(field is None for field in [run.validation_start_period, run.validation_end_period, run.validation_eval_start_period, run.validation_eval_end_period]):
            errors.append('validation_start_period, validation_end_period, validation_eval_start_period and validation_eval_end_period must be specified')
        else:
            calibration.update({
                'valid_start_period': run.validation_start_period.strftime(DATE_FORMAT),
                'valid_end_period': run.validation_end_period.strftime(DATE_FORMAT),
                'valid_eval_start_period': run.validation_eval_start_period.strftime(DATE_FORMAT),
                'valid_eval_end_period': run.validation_eval_end_period.strftime(DATE_FORMAT),
            })

        # Set full evaluation periods if both calibration and validation evaluation periods are present
        if run.calibration_eval_start_period and run.calibration_eval_end_period:
            calibration['full_eval_start_period'] = min(run.calibration_eval_start_period, run.validation_eval_start_period).strftime(DATE_FORMAT)
            calibration['full_eval_end_period'] = max(run.calibration_eval_end_period, run.validation_eval_end_period).strftime(DATE_FORMAT)

    if not is_missing(run.objective_function, 'objective function', errors):
        calibration['objective_function'] = run.objective_function.name.lower()

    if not is_missing(run.optimization, 'optimization', errors):
        calibration['optimization_algorithm'] = run.optimization.name.lower()

        all_input_names = set(
            OptimizationInput.objects.filter(optimization__name=run.optimization.name)
            .select_related('optimization')
            .values_list('name', flat=True)
        )

        # See if we have values for all the inputs
        inputs = CalibrationOptimizationInput.objects.filter(calibration_run=run).values(
            'value', data_type=F('optimization_input__data_type'), name=F('optimization_input__name'))

        for opt_input in inputs:
            converted_value = int(opt_input['value']) if opt_input['data_type'] == DataTypeEnum.INTEGER else opt_input['value']
            calibration[opt_input['name']] = converted_value
            all_input_names.discard(opt_input['name'])
        # See if there are any names leftover
        if all_input_names:
            errors.append(f'Missing required optimization inputs for {run.optimization.name} - {list(all_input_names)}')

    if not is_missing(run.save_plot_iteration_frequency, 'plot iteration frequency', errors):
        calibration['save_plot_iter_freq'] = run.save_plot_iteration_frequency

    # This field is not required from user
    calibration['save_output_iteration'] = int(run.save_output_iteration or 0)

    calibration['restart'] = 0  # TODO ???

    stop_criteria = CalibrationStopCriteria.objects.filter(calibration_run=run).first()
    if not is_missing(stop_criteria, 'stop criteria (number of iterations)', errors):
        # We're assuming there is only 1 stop criteria record for now
        calibration['number_iteration'] = stop_criteria.value

    calibration['start_iteration'] = 0  # TODO ????'

    if not is_missing(run.module_output_variable, 'output variable to calibrate', errors):
        calibration['output_variable_to_calibrate_name'] = run.module_output_variable.name
        calibration['output_variable_to_calibrate_module'] = run.module_output_variable.calibration_formulation.module.name

    if run.streamflow_threshold:
        calibration['streamflow_threshold'] = run.streamflow_threshold

    if run.peak_flow_threshold:
        calibration['peak_flow_threshold'] = run.peak_flow_threshold
    if run.use_sloth:
        sloth_params = (CalibrationSlothParam.objects.filter(calibration_run=run)
                        .values('param_name', 'param_count', 'param_units', 'param_location', 'param_value',
                                'maps_to_variable_name', module=F('maps_to_module__name')))

        # Required fields for sloth parameters
        required_fields = ['param_name', 'param_count', 'param_units', 'param_location', 'param_value', 'module', 'maps_to_variable_name']

        sloth_error = False
        sloth_lines = []
        header_format = '{:30s} {:>10s} {:8s} {:8s} {:>10s} {:15s} {:30s}\n'
        line_format = '{:30s} {:10d} {:8s} {:8s} {:10.5g} {:15s} {:30s}\n'
        for s in sloth_params:
            missing_fields = [field for field in required_fields if s.get(field) is None]
            if missing_fields:
                sloth_error = True
                errors.append(f"Missing fields {', '.join(missing_fields)} for sloth parameter '{s['param_name']}'")
            else:
                sloth_lines.append(
                    line_format.format(s['param_name'], s['param_count'], s['param_units'], s['param_location'], s['param_value'], s['module'],
                                       s['maps_to_variable_name'])
                )

        # If no errors and build is True, write the sloth parameters to a file
        if not sloth_error and build:
            sloth_parameter_file = Path(job_data_dir) / 'sloth_parameters.txt'

            sloth_parameter_content = header_format.format('name', 'count', 'units', 'location', 'value ', 'maps_to_module',
                                                           'maps_to_variable_name') + '\n'.join(
                line_format.format(s['param_name'], s['param_count'], s['param_units'], s['param_location'], s['param_value'], s['module'],
                                   s['maps_to_variable_name'])
                for s in sloth_params
            )
            Path(sloth_parameter_file).write_text(sloth_parameter_content)

            datafile['sloth_parameter_file'] = str(sloth_parameter_file)

    # Get formulations related to the run
    formulations = CalibrationFormulation.objects.filter(calibration_run=run)
    params = list(CalibrationParameter.objects
                  .filter(calibration_formulation__in=formulations, user_selected_for_tuning=True)
                  .select_related('calibration_formulation')
                  .values('name', 'initial_value', 'minimum', 'maximum', model=F('calibration_formulation__module__name')))
    param_error = False
    for p in params:
        # Make sure everything is specified
        if not p['name'] or p['initial_value'] is None or p['minimum'] is None or p['maximum'] is None:
            param_error = True
            errors.append(f"value, min and max must be specified for parameter '{p['name']}' (module {p['model']})")

    if not param_error and build:
        parameter_file = Path(job_data_dir) / 'parameters.txt'

        parameter_content = '{:16s} {:10s} {:10s} {:10s} {}\n'.format('param', 'min ', 'max', 'init', 'model') + '\n'.join(
            '{:16} {:<10.8g} {:<10.8g} {:<10.8g} {:10}'.format(p['name'], p['minimum'], p['maximum'], p['initial_value'], p['model'])
            for p in params
        )
        Path(parameter_file).write_text(parameter_content)

        datafile['calib_parameter_file'] = str(parameter_file)

    # print('validation errors from ngen_cal_input:', errors)

    run.status = StatusEnum.from_enum(StatusEnum.SAVED if errors else StatusEnum.READY)

    run.save()

    # if errors:
    #     print('There are validation errors. Normally, we would stop here and not try to build the config')
    # TODO Only build if no errors
    config_file = build_config(config, job_data_dir) if build and not errors else None
    # config_file = build_config(config, job_data_dir) if build else None

    return errors, config_file


def build_config(config: dict, directory: str):
    config_file = Path(directory) / 'input.config'

    logger.info(f'saving config to {config_file}')
    toml_string = toml.dumps(config)

    # The stupid create_input.py program in ngen_cal wants the strings to be unquotes, which is not standard.  Ugh.
    modified_toml_string = re.sub(r'\"(.*?)\"', r'\1', toml_string)

    Path(config_file).write_text(modified_toml_string)

    return config_file


def is_missing(value, field_name, errors, custom_error=None):
    if value is None:
        if custom_error:
            errors.append(custom_error)
        else:
            errors.append(f'{field_name} must be specified')

        return True
    return False
