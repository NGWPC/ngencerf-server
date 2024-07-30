import toml
from django.conf import settings
from django.db.models import F
from rest_framework import serializers

from calibration.enums import CalibrationRunType, StatusEnum, ForcingSourceEnum, ObservationalSourceEnum
from calibration.models import CalibrationOptimizationInput, Status, CalibrationStopCriteria, CalibrationSlothParam, \
    CalibrationTuneParameter
from views.ngen_locations import cfe_lib, topmd_lib, sft_lib, sloth_lib, smp_lib, lasam_lib, noah_lib, ngen_exe, noah_parameter_dir

config_template = {

    "General": {
        "basin": "01010101",
        "model": "cfe",
        "run_type": "calib",
        "main_dir": ""
    },

    "Calibration": {
        "optimization_algorithm": "DDS",
        "swarm_size": 20,
        "c1": 2,
        "c2": 2,
        "w": 0.7,
        "objective_function": "kge",
        "start_iteration": 0,
        "number_iteration": 10,
        "restart": 0,
        # Output variable to calibration is not supported yet by ngen-cal
        "output_variable_to_calibration_module": "Noah-OWP-Modular",
        "output_variable_to_calibration_name": "parameter1",
        "calib_start_period": "2019-10-01 00:00:00",
        "calib_end_period": "2019-10-01 00:00:00",
        "calib_eval_start_period": "2020-10-01 00:00:00",
        "calib_eval_end_period": "2020-10-01 00:00:00",
        "valid_start_period": "2016-10-01 00:00:00",
        "valid_end_period": "2019-10-01 00:00:00",
        "valid_eval_start_period": "2017-10-01 00:00:00",
        "valid_eval_end_period": "2019-10-01 00:00:00",
        "full_eval_start_period": "2017-10-01 00:00:00",
        "full_eval_end_period": "2019-10-01 00:00:00",
        "save_output_iter": 0,
        "save_plot_iter": 0,
        "save_plot_iter_freq": 50,
        "streamflow_threshold": "",
        "station_name": "",
        "user_email": "",
    },

    "DataFile": {
        "forcing_dir": "",
        "obs_dir": "",
        "hydrofab_dir": "",
        "cfe_dir": "",
        "topmd_dir": "",
        "noah_parameter_dir": "",
        "attributes_file": "",
        "calib_parameter_file": "",
        # Sloth parameter file is not supported by ngen-cal yet
        "sloth_parameter_file": "",
        "lasam_soil_parameter_file": "",
        "lasam_soil_class_file": "",
        "ngen_exe_file": ngen_exe,
        "cfe_lib": cfe_lib,
        "sloth_lib": sloth_lib,
        "topmd_lib": topmd_lib,
        "noah_lib": noah_lib,
        "sft_lib": sft_lib,
        "smp_lib": smp_lib,
        "lasam_lib": lasam_lib
    }
}


class NgenConfigGeneralValidator(serializers.Serializer):
    basin = serializers.CharField(required=True)
    model = serializers.CharField(min_length=2, required=True)
    # enum
    run_type = serializers.CharField(required=True)
    main_dir = serializers.CharField(min_length=2, required=True)


class NgenConfigCalibrationValidator(serializers.Serializer):
    optimization_algorithm = serializers.CharField(required=True)
    swarm_size = serializers.CharField(min_length=2, required=True)
    c1 = serializers.IntegerField(required=False)
    c2 = serializers.IntegerField(required=False)
    w = serializers.FloatField(required=False)
    objective_function = serializers.CharField(required=True)
    start_iteration = serializers.IntegerField(required=True)
    number_iteration = serializers.IntegerField(required=True)
    restart = serializers.IntegerField(required=True)
    calib_start_period = serializers.DateTimeField(required=True)
    calib_end_period = serializers.DateTimeField(required=True)
    calib_eval_start_period = serializers.DateTimeField(required=True)
    calib_eval_end_period = serializers.DateTimeField(required=True)
    valid_start_period = serializers.DateTimeField(required=True)
    valid_end_period = serializers.DateTimeField(required=True)
    valid_eval_start_period = serializers.DateTimeField(required=True)
    valid_eval_end_period = serializers.DateTimeField(required=True)
    full_eval_start_period = serializers.DateTimeField(required=True)
    full_eval_end_period = serializers.DateTimeField(required=True)
    save_output_iter = serializers.IntegerField(required=True)
    save_plot_iter = serializers.IntegerField(required=True)
    save_plot_iter_freq = serializers.IntegerField(required=True)
    streamflow_threshold = serializers.CharField(required=True, allow_blank=True)
    station_name = serializers.CharField(required=True, allow_blank=True)
    user_email = serializers.CharField(required=True, allow_blank=True)


class NgenConfigDatafileValidator(serializers.Serializer):
    forcing_dir = serializers.CharField(required=True)
    obs_dir = serializers.CharField(required=True)
    hydrofab_dir = serializers.CharField(required=True)
    cfe_dir = serializers.CharField(required=True, allow_blank=True)
    topmd_dir = serializers.CharField(required=True, allow_blank=True)
    noah_parameter_dir = serializers.CharField(required=True, allow_blank=True)
    attributes_file = serializers.CharField(required=True, allow_blank=True)
    calib_parameter_file = serializers.CharField(required=True, allow_blank=True)
    lasam_soil_parameter_file = serializers.CharField(required=True, allow_blank=True)
    lasam_soil_class_file = serializers.CharField(required=True, allow_blank=True)
    ngen_exe_file = serializers.CharField(required=True)
    cfe_lib = serializers.CharField(required=True, allow_blank=True)
    sloth_lib = serializers.CharField(required=True, allow_blank=True)
    topmd_lib = serializers.CharField(required=True, allow_blank=True)
    noah_lib = serializers.CharField(required=True, allow_blank=True)
    sft_lib = serializers.CharField(required=True, allow_blank=True)
    smp_lib = serializers.CharField(required=True, allow_blank=True)
    lasam_lib = serializers.CharField(required=True, allow_blank=True)


class NgenConfigValidator(serializers.Serializer):
    General = NgenConfigGeneralValidator(required=True)
    Calibration = NgenConfigCalibrationValidator(required=True)
    DataFile = NgenConfigDatafileValidator(required=True)


def ready_to_run(run, build=None):
    config = dict(config_template)
    general = config.get('General')
    calibration = config.get('Calibration')
    datafile = config.get('DataFile')

    messages = []

    if not run:
        raise Exception('Must pass a run instance to validate')

    if not run.gage:
        messages.append('gage_id must be specified')
    else:
        general['basin'] = run.gage.gage_id
        calibration['station_name'] = run.gage.station_name

        if not run.forcing_source:
            messages.append('forcing source must be specified')

        if run.forcing_source == ForcingSourceEnum.UPLOAD.value and not run.forcing_path or not run.forcing_user_filename:
            messages.append('forcing data must be uploaded')

        if run.forcing_source != ForcingSourceEnum.UPLOAD.name and not run.forcing_path:
            messages.append('Error getting forcing path from Hydrofabric')
        else:
            datafile['forcing_dir'] = run.forcing_path

        if not run.observational_source:
            messages.append('observational source must be specified')

        if run.observational_source == ObservationalSourceEnum.UPLOAD.value and not run.observational_path or not run.observational_user_filename:
            messages.append('observational data must be uploaded')

        if run.observational_source != ObservationalSourceEnum.UPLOAD.name and not run.observational_path:
            messages.append('Error getting observational path from Hydrofabric')
        else:
            datafile['obs_dir'] = run.observational_path

        if not run.hydrofabric_gpkg_path:
            messages.append('Error getting geopackage from Hydrofabric')
        else:
            datafile['hydrofab_dir'] = run.hydrofabric_gpkg_path

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

    general['main_dir'] = settings.NGEN_CAL_RUN_DIR

    # TODO output variable to calibrate
    # TODO Sloth parameters
    # TODO set run_date when we actually run it

    if not run.calibration_start_period or not run.calibration_end_period or not run.calibration_eval_start_period or not run.calibration_eval_end_period:
        messages.append(
            'calibration_start_period, calibration_end_period, calibration_eval_start_period and calibration_eval_end_period must be specified')
    else:
        calibration['calib_start_period'] = run.calibration_start_period
        calibration['calib_end_period'] = run.calibration_end_period
        calibration['calib_eval_start_period'] = run.calibration_eval_start_period
        calibration['calib_eval_start_period'] = run.calibration_eval_start_period

    if run.run_type == CalibrationRunType.VALID_BEST and (
            not run.validation_start_period or not run.validation_end_period or not run.validation_eval_start_period or not run.validation_eval_end_period):
        messages.append(
            'validation_start_period, validation_end_period, validation_eval_start_period and validation_eval_end_period must be specified')
    else:
        calibration['valid_start_period'] = run.validation_start_period
        calibration['valid_end_period'] = run.validation_end_period
        calibration['valid_eval_start_period'] = run.validation_eval_start_period
        calibration['valid_eval_start_period'] = run.validation_eval_start_period

    if not run.objective_function:
        messages.append('objective function must be specified')
    calibration['objective_function'] = run.objective_function

    if not run.optimization:
        messages.append('optimization must be specified')
    else:
        datafile['optimization_algorithm'] = run.optimization.name

        # Are any of te parameters required?
        inputs = CalibrationOptimizationInput.objects.filter(calibration_run=run)
        if swarm := inputs.filter(optimization_input__name='swarm_size').first():
            calibration['swarm_size'] = swarm.value
        if c1 := inputs.filter(optimization_input__name='c1').first():
            calibration['c1'] = c1.value
        if c2 := inputs.filter(optimization_input__name='c2').first():
            calibration['c2'] = c2.value
        if w := inputs.filter(optimization_input__name='w').first():
            calibration['w'] = w.value

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
        calibration['number_iterations'] = stop_criteria.value()
    calibration['start_iterations'] = 0  # TODO ????'

    if run.streamflow_threshold:
        calibration['streamflow_threshold'] = run.streamflow_threshold

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
            sloth_parameter_file = f'{run.id}_sloth_parameters.txt'
            print('sloth_parameter file', sloth_parameter_file)
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
        parameter_file = f'{run.id}_parameters.txt'
        print('parameter file', parameter_file)
        with open(parameter_file, 'w') as file:
            file.write('{:16s} {:10s} {:10s} {:10s} {}\n'.format('param', 'min ', 'max', 'init', 'model'))
            for p in params:
                file.write('{:16} {:<10.8g} {:<10.8g} {:<10.8g} {:10}\n'
                   .format(p['name'], p['minimum'], p['maximum'], p['initial_value'], p['model']))

        datafile['calib_parameter_file'] = parameter_file

    datafile['noah_parameter_dir'] = noah_parameter_dir

    print('messages', messages)

    # TODO This validation isn't really doing anything
    validator = NgenConfigValidator(data=config)

    run.status = Status.objects.filter(name=(StatusEnum.READY if validator.is_valid() else StatusEnum.SAVED)).first()
    run.save()

    # TODO Only build if no messages
    if build:
        build_config(config)


    return messages


def build_config(config):
    # Need to write to a file
    toml_config = toml.dumps(config)
    with open('input.config', 'w') as file:
        file.write(toml_config)
