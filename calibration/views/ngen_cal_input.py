import os
import re

import toml
from django.conf import settings
from django.db.models import F

from calibration.enums import CalibrationRunType, StatusEnum, ForcingSourceEnum, ObservationalSourceEnum
from calibration.models import CalibrationOptimizationInput, Status, CalibrationStopCriteria, CalibrationSlothParam, \
    CalibrationTuneParameter, OptimizationInput
from calibration.util.ngen_locations import CFE_LIB, TOPMD_LIB, SFT_LIB, SLOTH_LIB, SMP_LIB, LASAM_LIB, NOAH_LIB, NGEN_EXE, NOAH_PARAMETER_DIR, \
    parquet_dir

config_template = {

    "General": {
        "calibration_run_id": 0,
        "user": "",
        "basin": "",
        "model": "",
        "run_type": "",
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
        # Output variable to calibration is not supported yet by ngen-cal
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
        "hydrofab_dir": "",
        "cfe_dir": "",
        "topmd_dir": "",
        # Need another dir for every model
        "noah_parameter_dir": NOAH_PARAMETER_DIR,
        "attributes_file": "",
        "calib_parameter_file": "",
        # Sloth parameter file is not supported by ngen-cal yet
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
        "lasam_lib": LASAM_LIB
    }
}

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def ready_to_run(run, build=None):
    config = dict(config_template)
    general = config['General']
    calibration = config['Calibration']
    datafile = config['DataFile']

    messages = []

    if not run:
        raise Exception('Must pass a run instance to validate')

    general['calibration_run_id'] = run.id
    general['user'] = run.owner

    if not run.gage:
        messages.append('gage_id must be specified')
    else:
        general['basin'] = run.gage.gage_id
        calibration['station_name'] = run.gage.station_name

        if not run.forcing_source:
            messages.append('forcing source must be specified')
        else:
            if run.forcing_source == ForcingSourceEnum.UPLOAD.value and (not run.forcing_dir_path or not run.forcing_user_dir):
                messages.append('forcing data must be uploaded')
            elif run.forcing_source != ForcingSourceEnum.UPLOAD.value and not run.forcing_dir_path:
                messages.append('Error getting forcing path from Hydrofabric')
            else:
                datafile['forcing_dir'] = run.forcing_dir_path

        if not run.observational_source:
            messages.append('observational source must be specified')
        else:
            if run.observational_source == ObservationalSourceEnum.UPLOAD.value and (
                    not run.observational_file_path or not run.observational_user_filename):
                messages.append('observational data must be uploaded')
            elif run.observational_source != ObservationalSourceEnum.UPLOAD.value and not run.observational_file_path:
                messages.append('Error getting observational path from Hydrofabric')
            else:
                datafile['obs_dir'] = os.path.dirname(run.observational_file_path)

        if not run.hydrofabric_gpkg_path:
            messages.append('Error getting geopackage from Hydrofabric')
        else:
            datafile['hydrofab_dir'] = os.path.dirname(run.hydrofabric_gpkg_path)

        # Need to set parquet file based on domain
        datafile['attributes_file'] = os.path.join(parquet_dir, f'{run.gage.domain.name.lower()}_model_attributes.parquet')

    if not run.user_formulation_name:
        messages.append('formulation name must be specified')
    else:
        if not run.ngen_formulation_name:
            messages.append('Coding error - ngen_formulation_name is not filled in')
        else:
            general['model'] = run.ngen_formulation_name

    if not run.run_type:
        messages.append(f'run_type must be specified - {CalibrationRunType.CALIB} or {CalibrationRunType.VALID_BEST}')
    else:
        general['run_type'] = run.run_type

    main_dir = get_main_dir(run)
    general['main_dir'] = main_dir

    if build:
        os.makedirs(main_dir, exist_ok=True)

    # TODO output variable to calibrate
    # TODO set run_date when we actually run it

    if not run.calibration_start_period or not run.calibration_end_period or not run.calibration_eval_start_period or not run.calibration_eval_end_period:
        messages.append(
            'calibration_start_period, calibration_end_period, calibration_eval_start_period and calibration_eval_end_period must be specified')
    else:
        calibration['calib_start_period'] = run.calibration_start_period.strftime(DATE_FORMAT)
        calibration['calib_end_period'] = run.calibration_end_period.strftime(DATE_FORMAT)
        calibration['calib_eval_start_period'] = run.calibration_eval_start_period.strftime(DATE_FORMAT)
        calibration['calib_eval_end_period'] = run.calibration_eval_end_period.strftime(DATE_FORMAT)

    if run.run_type == CalibrationRunType.VALID_BEST.value and (
            not run.validation_start_period or not run.validation_end_period or not run.validation_eval_start_period or not run.validation_eval_end_period):
        messages.append(
            'validation_start_period, validation_end_period, validation_eval_start_period and validation_eval_end_period must be specified')
    elif run.run_type == CalibrationRunType.VALID_BEST.value:
        calibration['valid_start_period'] = min(run.calibration_start_period, run.validation_start_period).strftime(DATE_FORMAT)
        calibration['valid_end_period'] = max(run.calibration_end_period, run.validation_end_period).strftime(DATE_FORMAT)
        calibration['valid_eval_start_period'] = run.validation_eval_start_period.strftime(DATE_FORMAT)
        calibration['valid_eval_end_period'] = run.validation_eval_end_period.strftime(DATE_FORMAT)

        calibration['full_eval_start_period'] = min(run.calibration_eval_start_period, run.validation_eval_start_period).strftime(DATE_FORMAT)
        calibration['full_eval_end_period'] = max(run.calibration_eval_end_period, run.validation_eval_end_period).strftime(DATE_FORMAT)

    if not run.objective_function:
        messages.append('objective function must be specified')
    else:
        calibration['objective_function'] = run.objective_function.name

    if not run.optimization:
        messages.append('optimization must be specified')
    else:
        calibration['optimization_algorithm'] = run.optimization.name

        all_input_names = set(
            OptimizationInput.objects.filter(optimization__name=run.optimization.name).select_related('optimization').only('names').values_list(
                'name', flat=True))
        # See if we have values for all the inputs
        CalibrationOptimizationInput.objects.filter()
        inputs = CalibrationOptimizationInput.objects.filter(calibration_run=run).only('optimization_input__name', 'value').values('value', name=F(
            'optimization_input__name'))
        for opt_input in inputs:
            calibration[opt_input['name']] = opt_input['value']
            all_input_names.remove(opt_input['name'])
        # See if there are any names leftover
        if all_input_names:
            messages.append(f'Missing required optimization inputs for {run.optimization.name} - {list(all_input_names)}')

    if not run.plot_frequency:
        messages.append('plot frequency must be specified')
    else:
        calibration['save_plot_iter_freq'] = run.plot_frequency
    calibration['save_plot-iter'] = 0  # TODO ???
    calibration['restart'] = 0  # TODO ???

    stop_criteria = CalibrationStopCriteria.objects.filter(calibration_run=run).first()
    if not stop_criteria:
        messages.append('stop criteria (number of iterations) must be specified')
    else:
        # We're assuming there is only 1 stop criteria record for now
        calibration['number_iterations'] = stop_criteria.value

    calibration['start_iterations'] = 0  # TODO ????'

    if run.streamflow_threshold:
        calibration['streamflow_threshold'] = run.streamflow_threshold

    if run.peak_flow_threshold:
        calibration['peak_flow_threshold'] = run.peak_flow_threshold
    if run.use_sloth:
        sloth_params = (CalibrationSlothParam.objects.filter(calibration_run=run)
                        .only('param_name', 'param_count', 'param_units', 'param_location', 'param_value', 'maps_to_module', 'maps_to_variable_name')
                        .values('param_name', 'param_count', 'param_units', 'param_location', 'param_value',
                                'maps_to_variable_name', module=F('maps_to_module__name'), ))

        sloth_error = False
        for s in sloth_params:
            # Make sure everything is specified
            if not s['param_name'] or s['param_count'] is None or not s['param_units'] or not s['param_location'] or s['param_value'] is None or not \
                    s['module'] or not s['maps_to_variable_name']:
                sloth_error = True
                messages.append(
                    f"name, count, units, location, value, module and maps_to_variable_name must be specified for sloth parameter '{s['param_name']}'")

        if not sloth_error and build:
            sloth_parameter_file = os.path.join(main_dir, 'sloth_parameters.txt')
            with open(sloth_parameter_file, 'w') as file:
                file.write(
                    '{:30s} {:>10s} {:8s} {:8s} {:>10s} {:15s} {:30s}\n'.format('name', 'count', 'units', 'location', 'value ', 'maps_to_module',
                                                                                'maps_to_variable_name'))
                for s in sloth_params:
                    file.write('{:30s} {:10d} {:8s} {:8s} {:10.5g} {:15s} {:30s}\n'
                               .format(s['param_name'], s['param_count'], s['param_units'], s['param_location'], s['param_value'],
                                       s['module'], s['maps_to_variable_name']))
            datafile['sloth_parameter_file'] = sloth_parameter_file

    params = list(CalibrationTuneParameter.objects.filter(calibration_formulation__calibration_run=run).select_related('calibration_formulation')
                  .only('name', 'initial_value', 'minimum', 'maximum', 'calibration_formulation')
                  .values('name', 'initial_value', 'minimum', 'maximum', model=F('calibration_formulation__name')))
    param_error = False
    for p in params:
        # Make sure everything is specified
        if not p['name'] or p['initial_value'] is None or p['minimum'] is None or p['maximum'] is None:
            param_error = True
            messages.append(f"value, min and max must be specified for parameter '{p['name']}' (module {p['model']})")

    if not param_error and build:
        parameter_file = os.path.join(main_dir, 'parameters.txt')
        with open(parameter_file, 'w') as file:
            file.write('{:16s} {:10s} {:10s} {:10s} {}\n'.format('param', 'min ', 'max', 'init', 'model'))
            for p in params:
                file.write('{:16} {:<10.8g} {:<10.8g} {:<10.8g} {:10}\n'
                           .format(p['name'], p['minimum'], p['maximum'], p['initial_value'], p['model']))

        datafile['calib_parameter_file'] = parameter_file

    print('validation messages', messages)

    run.status = Status.objects.filter(name=(StatusEnum.SAVED if messages else StatusEnum.READY)).first()
    run.save()

    if messages:
        print('There are validation errors. Normally, we would stop here and not try to build the config')
    # TODO Only build if no messages
    # config_file = build_config(config, main_dir) if build and not messages else None
    config_file = build_config(config, main_dir) if build else None

    return messages, config_file


def build_config(config, directory):
    config_file = os.path.join(directory, 'input.config')

    print('saving config to', config_file)
    toml_string = toml.dumps(config)

    # The stupid create_input.py program in ngen_cal wants the strings to be unquotes, which is not standard.  Ugh.
    modified_toml_string = re.sub(r'\"(.*?)\"', r'\1', toml_string)

    with open(config_file, 'w') as file:
        file.write(modified_toml_string)

    return config_file


def get_main_dir(run):
    return os.path.join(settings.NGEN_CAL_RUN_DIR, f'{run.id}_{run.owner}')
