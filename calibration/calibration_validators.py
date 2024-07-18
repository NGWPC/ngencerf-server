from django.core.exceptions import ValidationError
from rest_framework import serializers

from calibration.enums import DataTypeEnum, UnitsEnum, LocationEnum


class CalibrationRunValidator(serializers.Serializer):
    calibration_run_id = serializers.IntegerField(required=True)


class GageIdValidator(serializers.Serializer):
    gage_id = serializers.CharField(required=True)


class SaveGageValidator(serializers.Serializer):
    calibration_run_id = serializers.IntegerField(required=True)
    gage_id = serializers.CharField(min_length=2, required=True)
    forcing_source = serializers.CharField(min_length=2, required=True)
    forcing_path = serializers.CharField(min_length=2, required=True)


def dataTypeValidator(value):
    if value not in DataTypeEnum.values():
        raise ValidationError(f"This field must be one of {DataTypeEnum.values()}")


def unitsValidator(value):
    if value not in UnitsEnum.values():
        raise ValidationError(f"This field must be one of {UnitsEnum.values()}")


def locationValidator(value):
    if value not in LocationEnum.values():
        raise ValidationError(f"This field must be one of {LocationEnum.values()}")


class SlothParameters(serializers.Serializer):
    name = serializers.CharField(min_length=2, required=True)
    count = serializers.IntegerField(required=True)
    type = serializers.CharField(required=True, validators=[dataTypeValidator])
    units = serializers.CharField(required=True, validators=[unitsValidator])
    location = serializers.CharField(required=True, validators=[locationValidator])
    value = serializers.FloatField(required=True)
    module = serializers.CharField(required=True)
    module_param = serializers.CharField(required=True)


class SaveFormulationValidator(serializers.Serializer):
    calibration_run_id = serializers.IntegerField(required=True)
    formulation_name = serializers.CharField(min_length=2, required=True)
    modules = serializers.ListField(child=serializers.CharField(min_length=2, required=True), min_length=2)
    sloth_parameters = SlothParameters(required=True, many=True, min_length=1)


class ModuleOutputVariablesValidator(serializers.Serializer):
    name = serializers.CharField(min_length=2, required=True)
    description = serializers.CharField(min_length=2, required=True)
    type = serializers.CharField(required=True, validators=[dataTypeValidator])


class ParameterValidator(serializers.Serializer):
    name = serializers.CharField(min_length=2, required=True)
    initial_value = serializers.FloatField(required=True)
    calibratable = serializers.BooleanField(required=True)


class ModuleValidator(serializers.Serializer):
    name = serializers.CharField(min_length=2, required=True)
    description = serializers.CharField(min_length=2, required=True)
    groups = serializers.ListSerializer(min_length=1, child=serializers.CharField(min_length=2, required=True))


class ModuleCollectionValidator(serializers.Serializer):
    modules_data = ModuleValidator(many=True, min_length=1, required=True)


class ModuleDataValidator(serializers.Serializer):
    name = serializers.CharField(min_length=2, required=True)
    output_variables = ModuleOutputVariablesValidator(many=True, min_length=1, required=True)
    parameters = ParameterValidator(many=True, min_length=1, required=True)


class ModuleDataCollectionValidator(serializers.Serializer):
    modules_data = ModuleDataValidator(many=True, min_length=1, required=True)


class ReportIterationValidator(serializers.Serializer):
    calibration_run_id = serializers.IntegerField(required=True)
    iteration = serializers.IntegerField(required=True, min_value=1)


class TuningParametersValidator(serializers.Serializer):
    name = serializers.CharField(required=True)
    module = serializers.CharField(required=True)
    min = serializers.FloatField(required=True)
    max = serializers.FloatField(required=True)
    initial_value = serializers.FloatField(required=True)


class CalibrationTimeControls(serializers.Serializer):
    calibration_start_time = serializers.DateTimeField(required=True, format="%Y-%m-%d %H:%M:%S", input_formats=['%Y-%m-%d %H:%M:%S'])
    calibration_end_time = serializers.DateTimeField(required=True, format="%Y-%m-%d %H:%M:%S", input_formats=['%Y-%m-%d %H:%M:%S'])
    simulation_start_time = serializers.DateTimeField(required=True, format="%Y-%m-%d %H:%M:%S", input_formats=['%Y-%m-%d %H:%M:%S'])
    simulation_end_time = serializers.DateTimeField(required=True, format="%Y-%m-%d %H:%M:%S", input_formats=['%Y-%m-%d %H:%M:%S'])


class ValidationTimeControls(serializers.Serializer):
    validation_start_time = serializers.DateTimeField(required=True, format="%Y-%m-%d %H:%M:%S", input_formats=['%Y-%m-%d %H:%M:%S'])
    validation_end_time = serializers.DateTimeField(required=True, format="%Y-%m-%d %H:%M:%S", input_formats=['%Y-%m-%d %H:%M:%S'])
    simulation_start_time = serializers.DateTimeField(required=True, format="%Y-%m-%d %H:%M:%S", input_formats=['%Y-%m-%d %H:%M:%S'])
    simulation_end_time = serializers.DateTimeField(required=True, format="%Y-%m-%d %H:%M:%S", input_formats=['%Y-%m-%d %H:%M:%S'])


class SaveTuningValidator(serializers.Serializer):
    calibration_run_id = serializers.IntegerField(required=True)
    parameters = TuningParametersValidator(many=True, required=False)
    calibration_times = CalibrationTimeControls(required=False)
    validation_times = ValidationTimeControls(required=False)
    automatic_validation = serializers.BooleanField(required=True)


class MetricNameValidator(serializers.Serializer):
    metric = serializers.CharField(min_length=3)


class AlgorithmInputsValidator(serializers.Serializer):
    name = serializers.CharField(required=True, allow_blank=False)
    value = serializers.FloatField(required=True)


class SaveOptimizationValidator(serializers.Serializer):
    calibration_run_id = serializers.IntegerField(required=True)
    optimization_inputs = AlgorithmInputsValidator(many=True, required=False)
    optimization = serializers.CharField(allow_blank=False, required=False)
    objective_function = serializers.CharField(allow_blank=False, required=False)
    streamflow_threshold = serializers.FloatField(required=False)
    run_categorical_metrics = serializers.BooleanField(default=False)

