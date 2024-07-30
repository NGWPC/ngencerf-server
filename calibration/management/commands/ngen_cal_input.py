import toml
from django.core.management import BaseCommand
from django.db.models import F
from rest_framework import serializers

from django.conf import settings

from calibration.enums import CalibrationRunType, StatusEnum, ForcingSourceEnum, ObservationalSourceEnum
from calibration.models import CalibrationOptimizationInput, CalibrationRun, Status, CalibrationStopCriteria, CalibrationSlothParam, \
    CalibrationTuneParameter, Optimization
from cerfServer.settings import NGEN_CAL_RUN_DIR
from views.ngen_locations import cfe_lib, topmd_lib, sft_lib, sloth_lib, smp_lib, lasam_lib, noah_lib, ngen_exe, noah_parameter_dir

# TODO This is defined as a management command for dev purposes only.  Will be moved to the regular code


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
        "lasam_soil_parameter_file": "",
        "lasam_soil_class_file": "",
        "ngen_exe_file": "",
        "cfe_lib": "",
        "sloth_lib": "",
        "topmd_lib": "",
        "noah_lib": "",
        "sft_lib": "",
        "smp_lib": "",
        "lasam_lib": ""
    }
}


class Command(BaseCommand):
    help = "Check if ready"

    def handle(self, *args, **options):
        run_id = options['run_id']
        run = options['run']
        ready_to_run(run_id, run)

    def add_arguments(self, parser):
        parser.add_argument('run_id', type=int)
        parser.add_argument('run', type=CalibrationRun)


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


def ready_to_run(run_id=None, run=None):
    config = dict(config_template)
    general = config.get('General')
    calibration = config.get('Calibration')
    datafile = config.get('DataFile)')

    messages = []

    if run_id:
        run = CalibrationRun.objects.filter(id=run_id).first()
    if not run:
        raise Exception(f'CalibrationRun {run_id} does not exist')

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

        if not run.hydrofab_dir:
            messages.append('Error getting geopackage from Hydrofabric')
        else:
            datafile['hydrofab_dir'] = run.hydrofab_path

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

    calibration['streamflow_threshold'] = run.streamflow_threshold

    if run.use_sloth:
        sloth = (CalibrationSlothParam.objects.filter(calibration_run=run)
                 .only('param_name', 'param_count', 'param_units', 'param_location', 'param_value', 'maps_to_module', 'maps_to_variable_name')
                 .values('param_name', 'param_count', 'param_units', 'param_location', 'param_value', 'maps_to_module', 'maps_to_variable_name'))
        print('sloth', sloth)

    params = list(CalibrationTuneParameter.objects.filter(calibration_formulation__calibration_run=run).select_related('calibration_formulation')
                  .only('name', 'initial_value', 'minimum', 'maximum', 'calibration_formulation')
                  .values('name', 'initial_value', 'minimum', 'maximum', model=F('calibration_formulation__name')))
    param_error = False
    for p in params:
        # Make sure everything is specified
        if not p.get('name') or not p.get('initial_value') or not p.get('minimum') or not p.get('maximum'):
            param_error = True
            messages.append(f"value, min and max must be specified for parameter '{p.get('name')}' (module {p.get('model')})")

    if not param_error:
        # Only do this when we're ready to run
        parameter_file = f'{run.id}_parameters.txt'
        print('parameter file', parameter_file)
        with open(parameter_file, 'w') as file:
            file.write('param            min        max        init       model\n')
            for p in params:
                file.write('{:16} {:<10.8g} {:<10.8g} {:<10.8g} {:10}\n'
                           .format(p['name'], p['minimum'], p['maximum'], p['initial_value'], p['model']))

    # TODO Only do this when we're ready to run
    general['main_dir'] = NGEN_CAL_RUN_DIR
    datafile['ngen_exe_file'] = ngen_exe
    datafile['cfe_lib'] = cfe_lib
    datafile['sloth_lib'] = sloth_lib
    datafile['topmd_lib'] = topmd_lib
    datafile['noah_lib'] = noah_lib
    datafile['sft_lib'] = sft_lib
    datafile['smp_lib'] = smp_lib
    datafile['lasam_lib'] = lasam_lib
    datafile['noah_parameter_dir'] = noah_parameter_dir

    print('messages', messages)

    # print('config', config)
    validator = NgenConfigValidator(data=config)
    # if not validator.is_valid():
    #     print(f"Not ready")
    #     run.status = Status.objects.filter(name=StatusEnum.SAVED).first()
    #
    #     return False
    # else:
    #     run.status = Status.objects.filter(name=StatusEnum.READY).first()
    #     return True

    run.status = Status.objects.filter(name=(StatusEnum.READY if validator.is_valid() else StatusEnum.SAVED)).first()
    run.save()
    return messages


def build_config():
    # Need to write to a file
    toml_config = toml.dumps(config_template)
