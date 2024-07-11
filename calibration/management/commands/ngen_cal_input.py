import toml
from django.core.management import BaseCommand
from rest_framework import serializers

from django.conf import settings


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
        "save_plot_iter_freqself": 50,
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
        ready_to_run()


class Ngen_config_general_validator(serializers.Serializer):
    basin = serializers.CharField(required=True)
    model = serializers.CharField(min_length=2, required=True)
    # enum
    run_type = serializers.CharField(required=True)
    main_dir = serializers.CharField(min_length=2, required=True)


class Ngen_config_calibration_validator(serializers.Serializer):
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


class Ngen_config_datafile_validator(serializers.Serializer):
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


class Ngen_config_validator(serializers.Serializer):
    General = Ngen_config_general_validator(required=True)
    Calibration = Ngen_config_calibration_validator(required=True)
    DataFile = Ngen_config_datafile_validator(required=True)


def ready_to_run():
    config = dict(config_template)
    general = config.get('General')
    calibration = config.get('Calibration')
    datafile = config.get('DataFile)')

    general['basin'] = "gage_id"
    general['model'] = "cfe"
    general['run_type'] = "calib"
    general['main_dir'] = settings.NGEN_CAL_MAIN_DIR

    print('config', config)
    validator = Ngen_config_validator(data=config)
    if not validator.is_valid():
        print(f"Not ready {validator.errors}")
        return False
    else:
        return True


def build_config():
    # Need to write to a file
    toml_config = toml.dumps(config_template)
