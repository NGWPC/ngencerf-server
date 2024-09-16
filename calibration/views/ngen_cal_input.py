import logging
import re
from pathlib import Path

import toml
from datetimerange import DateTimeRange
from django.db.models import F

from calibration.enums import StatusEnum, ForcingSourceEnum, ObservationalSourceEnum, DataTypeEnum
from calibration.models import CalibrationOptimizationInput, CalibrationStopCriteria, CalibrationSlothParam, \
    CalibrationParameter, OptimizationInput, CalibrationFormulation, CalibrationRun
from calibration.util.ngen_locations import CFE_LIB, TOPMD_LIB, SFT_LIB, SLOTH_LIB, SMP_LIB, LASAM_LIB, NOAH_LIB, NGEN_EXE, NOAH_PARAMETER_DIR, \
    PARQUET_DIR, get_forcing_dir_for_job, get_observational_dir_for_job, \
    get_observational_file_for_job, get_geopackage_dir_for_job, \
    get_geopackage_file_for_job, PET_LIB, SNOW17_LIB, SAC_LIB
from calibration.views.calibration_run_views import subset_by_time_range, subset_directory_by_time_range
from calibration.views.common import CerfException

logger = logging.getLogger(__name__)

config_template = {

    "General": {
        "calibration_run_id": 0,
        "user": "",
        "basin": "",
        # Old
        "model": "",
        # New
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
        "restart": 0,
        # TODO Output variable to calibrate is not supported yet by ngen-cal
        "output_variable_to_calibration_module": "",
        "output_variable_to_calibration_name": "",
        "calib_start_period": "",
        "calib_end_period": "",
        "calib_eval_start_period": "",
        "calib_eval_end_period": "",
        "valid_start_period": "0000-00-00 00:00:00",
        "valid_end_period": "0000-00-00 00:00:00",
        "valid_eval_start_period": "0000-00-00 00:00:00",
        "valid_eval_end_period": "0000-00-00 00:00:00",
        "full_eval_start_period": "0000-00-00 00:00:00",
        "full_eval_end_period": "0000-00-00 00:00:00",
        "save_output_iter": 0,
        "save_plot_iter": 0,
        "save_plot_iter_freq": 0,
        "streamflow_threshold": 0,
        "peak_flow_threshold": 0,
        "station_name": "",
        "user_email": "",
    },

    "DataFile": {
        "forcing_dir": "",
        "obs_dir": "",
        "nwmretro_file": "/home/peter.a.kronenberg/s3/ngwpc-dev/Yuqiong.Liu/data/nwmv3_retro_streamflow/csv/CONUS/01123000_1979_2022.csv",
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

        "noah_parameter_dir": NOAH_PARAMETER_DIR,
        "attributes_file": "",
        "calib_parameter_file": "",
        # TODO Sloth parameter file is not supported by ngen-cal yet
        "sloth_parameter_file": "",
        "lasam_soil_parameter_file": "",
        "lasam_soil_class_file": "",
        "ngen_exe_file": NGEN_EXE,
        "cfe_lib": CFE_LIB,
        "sloth_lib": SLOTH_LIB,
        "topmd_lib": TOPMD_LIB,
        "noah_lib": NOAH_LIB,
        "sft_lib": SFT_LIB,
        "smp_lib": SMP_LIB,
        "lasam_lib": LASAM_LIB,
        "pet_lib": PET_LIB,
        "snow17_lib": SNOW17_LIB,
        "sac_lib": SAC_LIB
    }
}

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def ready_to_run(run: CalibrationRun, build: bool = None):
    config = dict(config_template)
    general = config['General']
    calibration = config['Calibration']
    datafile = config['DataFile']

    errors = []

    if not run:
        raise CerfException('Must pass a run instance to validate')

    general['calibration_run_id'] = run.id
    general['user'] = run.owner.username

    if not is_missing(run.gage, 'gage_id', errors):
        general['basin'] = run.gage.gage_id
        calibration['station_name'] = run.gage.station_name

        if not is_missing(run.forcing_source, 'forcing source', errors):
            is_forcing_upload = run.forcing_source == ForcingSourceEnum.from_enum(ForcingSourceEnum.UPLOAD)
            if is_forcing_upload:
                forcing_dir = get_forcing_dir_for_job(run)
                if not forcing_dir or not Path(forcing_dir).exists():
                    errors.append('forcing data must be uploaded')
            elif build:
                # for non-uploaded data, subset the data by time range
                source_dir = run.forcing_hydrofabric_dir_path
                subset_directory_by_time_range(source_dir, get_forcing_dir_for_job(run),
                                               DateTimeRange(min(run.calibration_start_period, run.validation_start_period), max(run.calibration_end_period, run.validation_end_period)))

        datafile['forcing_dir'] = get_forcing_dir_for_job(run)

        if not is_missing(run.observational_source, 'observational source', errors):
            is_observational_upload = run.observational_source == ObservationalSourceEnum.from_enum(ObservationalSourceEnum.UPLOAD)
            if is_observational_upload:
                observational_file = get_observational_file_for_job(run)
                if not observational_file or not Path(observational_file).exists():
                    errors.append('observational data must be uploaded')
            elif build:
                # For non-uploaded data, subset the data by time range
                source_file = run.observational_hydrofabric_file_path
                subset_by_time_range(source_file, get_observational_file_for_job(run),
                                     DateTimeRange(min(run.calibration_start_period, run.validation_start_period), max(run.calibration_end_period, run.validation_end_period)))

        datafile['obs_dir'] = get_observational_dir_for_job(run)

        # datafile['nwmretro_file'] = ''  # Not sure what this is yet

        if run.geopackage_hydrofabric_path and Path(run.geopackage_hydrofabric_path).exists():
            datafile['hydrofab_dir'] = str(Path(run.geopackage_hydrofabric_path).parent)
        else:
            if Path(get_geopackage_file_for_job(run)).exists():
                datafile['hydrofab_dir'] = get_geopackage_dir_for_job(run)
            else:
                errors.append('geopackage data must be uploaded')

        # Need to set parquet file based on domain
        datafile['attributes_file'] = str(Path(PARQUET_DIR) / f'{run.gage.domain.name.lower()}_model_attributes.parquet')

    modules = CalibrationFormulation.objects.filter(calibration_run=run, used_by_calibration_run=True).values('name', 'bmi_config_path')
    # Create a dictionary with 'name' as the key and 'bmi_config_path' as the value
    module_dict = {module['name']: module['bmi_config_path'] for module in modules}

    if not is_missing(modules, 'modules', errors) and not is_missing(run.user_formulation_name, 'formulation name', errors):
        general['formulation'] = run.user_formulation_name
        general['model'] = run.ngen_formulation_name
        # TODO Not being used yet by ngen-cal
        general['models'] = ', '.join(module_dict.keys())

        # Dynamically add keys and values from the module_dict to our config
        for key, value in module_dict.items():
            new_key = key.lower() + '_bmi_dir'
            datafile[new_key] = value

    job_data_dir = run.job_data_dir
    general['main_dir'] = job_data_dir

    if build:
        Path(job_data_dir).mkdir(parents=True, exist_ok=True)

    if any(field is None for field in
           [run.calibration_start_period, run.calibration_end_period, run.calibration_eval_start_period, run.calibration_eval_end_period]):
        errors.append(
            'calibration_start_period, calibration_end_period, calibration_eval_start_period and calibration_eval_end_period must be specified')
    else:
        calibration['calib_start_period'] = run.calibration_start_period.strftime(DATE_FORMAT)
        calibration['calib_end_period'] = run.calibration_end_period.strftime(DATE_FORMAT)
        calibration['calib_eval_start_period'] = run.calibration_eval_start_period.strftime(DATE_FORMAT)
        calibration['calib_eval_end_period'] = run.calibration_eval_end_period.strftime(DATE_FORMAT)

    if run.automatic_validation:
        if any(field is None for field in
               [run.validation_start_period, run.validation_end_period, run.validation_eval_start_period, run.validation_eval_end_period]):
            errors.append(
                'validation_start_period, validation_end_period, validation_eval_start_period and validation_eval_end_period must be specified')
        else:
            calibration['valid_start_period'] = run.validation_start_period.strftime(DATE_FORMAT)
            calibration['valid_end_period'] = run.validation_end_period.strftime(DATE_FORMAT)
            calibration['valid_eval_start_period'] = run.validation_eval_start_period.strftime(DATE_FORMAT)
            calibration['valid_eval_end_period'] = run.validation_eval_end_period.strftime(DATE_FORMAT)

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

    if not is_missing(run.plot_frequency, 'plot frequency', errors):
        calibration['save_plot_iter_freq'] = run.plot_frequency
    calibration['save_plot-iter'] = 0  # TODO ???
    calibration['restart'] = 0  # TODO ???

    stop_criteria = CalibrationStopCriteria.objects.filter(calibration_run=run).first()
    if not is_missing(stop_criteria, 'stop criteria (number of iterations)', errors):
        # We're assuming there is only 1 stop criteria record for now
        calibration['number_iteration'] = stop_criteria.value

    calibration['start_iteration'] = 0  # TODO ????'

    if not is_missing(run.module_output_variable, 'output variable to calibrate', errors):
        calibration['output_variable_to_calibrate_name'] = run.module_output_variable.name
        calibration['output_variable_to_calibrate_module'] = run.module_output_variable.calibration_formulation.name

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

    params = list(CalibrationParameter.objects
                  .filter(calibration_formulation__calibration_run=run, user_selected_for_tuning=True)
                  .select_related('calibration_formulation')
                  .values('name', 'initial_value', 'minimum', 'maximum', model=F('calibration_formulation__name')))
    param_error = False
    for p in params:
        # Make sure everything is specified
        if not p['name'] or p['initial_value'] is None or p['minimum'] is None or p['maximum'] is None:
            param_error = True
            errors.append(f"value, min and max must be specified for parameter '{p['name']}' (module {p['model']})")

    if not param_error and build:
        parameter_file = Path(job_data_dir) / 'parameters.txt'

        parameter_content = '{:16s} {:10s} {:10s} {:10s} {}\n'.format('param', 'min ', 'max', 'init', 'model') + '\n'.join(
            '{:16} {:<10.8g} {:<10.8g} {:<10.8g} {:10}\n'.format(p['name'], p['minimum'], p['maximum'], p['initial_value'], p['model'])
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
