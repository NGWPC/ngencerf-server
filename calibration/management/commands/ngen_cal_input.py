import toml
from django.core.management import BaseCommand
from rest_framework import serializers

from django.conf import settings

from calibration.enums import CalibrationRunType, StatusEnum
from calibration.models import CalibrationOptimizationInput, CalibrationRun, Status

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

    if not run.ngen_formulation_name:
        messages.append('formulation name must be specified')
    else:
        # Not sure what we list for model
        general['model'] = '?'

    if not run.run_type:
        messages.append(f'run_type must be specified - {CalibrationRunType.CALIB} or {CalibrationRunType.VALID_BEST}')
    else:
        general['run_type'] = run.run_type

    general['main_dir'] = settings.NGEN_CAL_MAIN_DIR

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

    calibration['save_plot_iter_freq'] = run.plot_frequency
    # What is save_plot_iter?

    # Where does stop criteria go?
    # calibration[CalibrationStopCriteria.objects.filter(calibration_run=run).first().value()

    calibration['streamflow_threshold'] = run.streamflow_threshold

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
