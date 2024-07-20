from datetime import timezone

from django.core.exceptions import ValidationError
from rest_framework import serializers

from calibration.enums import DataTypeEnum, UnitsEnum, LocationEnum, ForcingSourceEnum

INPUT_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

OUTPUT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S %z"


class CalibrationRunValidator(serializers.Serializer):
    calibration_run_id = serializers.IntegerField(required=True)


class GageIdValidator(serializers.Serializer):
    gage_id = serializers.CharField(required=True, allow_blank=False)


def forcingSourceValidator(value):
    if value not in ForcingSourceEnum.values():
        raise ValidationError(f"This field must be one of {ForcingSourceEnum.values()}")


class SaveGageValidator(serializers.Serializer):
    calibration_run_id = serializers.IntegerField(required=True)
    gage_id = serializers.CharField(min_length=2, required=False, allow_blank=False)
    forcing_source = serializers.CharField(required=False, validators=[forcingSourceValidator])
    forcing_user_filename = serializers.CharField(min_length=2, required=False, allow_blank=False)


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
    name = serializers.CharField(min_length=2, required=True, allow_blank=False)
    count = serializers.IntegerField(required=True)
    type = serializers.CharField(required=True, validators=[dataTypeValidator])
    units = serializers.CharField(required=True, validators=[unitsValidator])
    location = serializers.CharField(required=True, validators=[locationValidator])
    value = serializers.FloatField(required=True)
    module = serializers.CharField(required=True, allow_blank=False)
    module_param = serializers.CharField(required=True, allow_blank=False)


class SaveFormulationValidator(serializers.Serializer):
    calibration_run_id = serializers.IntegerField(required=True)
    formulation_name = serializers.CharField(min_length=2, required=False, allow_blank=False)
    modules = serializers.ListField(child=serializers.CharField(min_length=2, required=True), min_length=2)
    sloth_parameters = SlothParameters(required=False, many=True, min_length=1)


class ModuleOutputVariablesValidator(serializers.Serializer):
    name = serializers.CharField(min_length=2, required=True, allow_blank=False)
    description = serializers.CharField(min_length=2, required=True, allow_blank=False)
    type = serializers.CharField(required=True, validators=[dataTypeValidator])


class ParameterValidator(serializers.Serializer):
    name = serializers.CharField(min_length=2, required=True, allow_blank=False)
    initial_value = serializers.FloatField(required=True)
    calibratable = serializers.BooleanField(required=True)


class ModuleValidator(serializers.Serializer):
    name = serializers.CharField(min_length=2, required=True, allow_blank=False)
    description = serializers.CharField(min_length=2, required=True, allow_blank=False)
    groups = serializers.ListSerializer(min_length=1, child=serializers.CharField(min_length=2, required=True, allow_blank=False))


class ModuleCollectionValidator(serializers.Serializer):
    modules_data = ModuleValidator(many=True, min_length=1, required=True)


class ModuleDataValidator(serializers.Serializer):
    name = serializers.CharField(min_length=2, required=True, allow_blank=False)
    output_variables = ModuleOutputVariablesValidator(many=True, min_length=1, required=True)
    parameters = ParameterValidator(many=True, min_length=1, required=True)


class ModuleDataCollectionValidator(serializers.Serializer):
    modules_data = ModuleDataValidator(many=True, min_length=1, required=True)


class ReportIterationValidator(serializers.Serializer):
    calibration_run_id = serializers.IntegerField(required=True)
    iteration = serializers.IntegerField(required=True, min_value=1)


class TuningParametersValidator(serializers.Serializer):
    name = serializers.CharField(required=True, allow_blank=False)
    module = serializers.CharField(required=True, allow_blank=False)
    minimum = serializers.FloatField(required=True)
    maximum = serializers.FloatField(required=True)
    initial_value = serializers.FloatField(required=True)


class CalibrationTimeControls(serializers.Serializer):
    calibration_start_time = serializers.DateTimeField(required=True, format=OUTPUT_DATE_FORMAT, input_formats=[INPUT_DATE_FORMAT], default_timezone=timezone.utc)
    calibration_end_time = serializers.DateTimeField(required=True, format=OUTPUT_DATE_FORMAT, input_formats=[INPUT_DATE_FORMAT], default_timezone=timezone.utc)
    simulation_start_time = serializers.DateTimeField(required=True, format=OUTPUT_DATE_FORMAT, input_formats=[INPUT_DATE_FORMAT], default_timezone=timezone.utc)
    simulation_end_time = serializers.DateTimeField(required=True, format=OUTPUT_DATE_FORMAT, input_formats=[INPUT_DATE_FORMAT], default_timezone=timezone.utc)


class ValidationTimeControls(serializers.Serializer):
    validation_start_time = serializers.DateTimeField(required=True, format=OUTPUT_DATE_FORMAT, input_formats=[INPUT_DATE_FORMAT])
    validation_end_time = serializers.DateTimeField(required=True, format=OUTPUT_DATE_FORMAT, input_formats=[INPUT_DATE_FORMAT])
    simulation_start_time = serializers.DateTimeField(required=True, format=OUTPUT_DATE_FORMAT, input_formats=[INPUT_DATE_FORMAT])
    simulation_end_time = serializers.DateTimeField(required=True, format=OUTPUT_DATE_FORMAT, input_formats=[INPUT_DATE_FORMAT])


class OutputVariableValidator(serializers.Serializer):
    module = serializers.CharField(required=True, allow_blank=False)
    name = serializers.CharField(required=True, allow_blank=False)


class SaveTuningValidator(serializers.Serializer):
    calibration_run_id = serializers.IntegerField(required=True)
    parameters = TuningParametersValidator(many=True, required=False)
    calibration_times = CalibrationTimeControls(required=False)
    validation_times = ValidationTimeControls(required=False)
    automatic_validation = serializers.BooleanField(required=True)
    output_variable_to_calibrate = OutputVariableValidator(required=False)


class MetricNameValidator(serializers.Serializer):
    metric = serializers.CharField(min_length=3, allow_blank=False)


class AlgorithmInputsValidator(serializers.Serializer):
    name = serializers.CharField(required=True, allow_blank=False)
    value = serializers.FloatField(required=True)


class SaveOptimizationValidator(serializers.Serializer):
    calibration_run_id = serializers.IntegerField(required=True)
    optimization_inputs = AlgorithmInputsValidator(many=True, required=False)
    optimization = serializers.CharField(allow_blank=False, required=False)
    objective_function = serializers.CharField(allow_blank=False, required=False)
    streamflow_threshold = serializers.FloatField(required=False)
    stop_criteria = serializers.IntegerField(required=False)
    plot_generation_frequency = serializers.IntegerField(required=False)
