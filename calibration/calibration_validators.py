from datetime import timezone

from django.core.exceptions import ValidationError
from rest_framework import serializers
from rest_framework.fields import empty
from rest_framework.settings import api_settings

from calibration.enums import DataTypeEnum, UnitsEnum, LocationEnum, ForcingSourceEnum, ObservationalSourceEnum

INPUT_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

OUTPUT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S %z"


class BaseSerializer(serializers.Serializer):
    def run_validation(self, data=None):
        if data != empty:
            unknown = set(data) - set(self.fields)
            if unknown:
                errors = ["Unknown field: {}".format(f) for f in unknown]
                raise serializers.ValidationError({
                    api_settings.NON_FIELD_ERRORS_KEY: errors,
                })

        return super().run_validation(data)


class CalibrationRunValidator(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)


class GageIdValidator(BaseSerializer):
    gage_id = serializers.CharField(required=True, allow_blank=False)


def forcingSourceValidator(value):
    if value not in ForcingSourceEnum.values():
        raise ValidationError(f"This field must be one of {ForcingSourceEnum.values()}")


def observationSourceValidator(value):
    if value not in ObservationalSourceEnum.values():
        raise ValidationError(f"This field must be one of {ObservationalSourceEnum.values()}")


class SaveGageValidator(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    gage_id = serializers.CharField(min_length=2, required=False, allow_blank=False)
    forcing_source = serializers.CharField(required=False, validators=[forcingSourceValidator])
    forcing_user_filename = serializers.CharField(min_length=2, required=False, allow_blank=False)
    observational_source = serializers.CharField(required=False, validators=[observationSourceValidator])
    observational_user_filename = serializers.CharField(min_length=2, required=False, allow_blank=False)


def dataTypeValidator(value):
    if value not in DataTypeEnum.values():
        raise ValidationError(f"This field must be one of {DataTypeEnum.values()}")


def unitsValidator(value):
    if value not in UnitsEnum.values():
        raise ValidationError(f"This field must be one of {UnitsEnum.values()}")


def locationValidator(value):
    if value not in LocationEnum.values():
        raise ValidationError(f"This field must be one of {LocationEnum.values()}")


class SlothParameters(BaseSerializer):
    param_name = serializers.CharField(min_length=2, required=True, allow_blank=False)
    param_count = serializers.IntegerField(required=True)
    param_type = serializers.CharField(required=True, validators=[dataTypeValidator])
    param_units = serializers.CharField(required=True, validators=[unitsValidator])
    param_location = serializers.CharField(required=True, validators=[locationValidator])
    param_value = serializers.FloatField(required=True)
    maps_to_module = serializers.CharField(required=True, allow_blank=False)
    maps_to_variable_name = serializers.CharField(required=True, allow_blank=False)


class SaveFormulationValidator(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    formulation_name = serializers.CharField(min_length=2, required=False, allow_blank=False)
    modules = serializers.ListField(child=serializers.CharField(min_length=2, required=True), min_length=2)
    use_sloth = serializers.BooleanField(required=True)
    sloth_parameters = SlothParameters(required=False, many=True, min_length=1)


# Output variables from Hydrofabric
class ModuleOutputVariablesValidator(BaseSerializer):
    name = serializers.CharField(min_length=2, required=True, allow_blank=False)
    description = serializers.CharField(min_length=2, required=True, allow_blank=False)
    # type = serializers.CharField(required=True, validators=[dataTypeValidator])


# class ParameterValidator(BaseSerializer):
#     name = serializers.CharField(min_length=2, required=True, allow_blank=False)
#     initial_value = serializers.FloatField(required=True)
#     type = serializers.CharField(required=True, validators=[dataTypeValidator])


# Parameters from Hydrofabric
class ModuleParametersValidator(BaseSerializer):
    name = serializers.CharField(min_length=2, required=True, allow_blank=False)
    data_type = serializers.CharField(required=True, validators=[dataTypeValidator])
    units = serializers.CharField(required=True)
    min = serializers.FloatField(required=True)
    max = serializers.FloatField(required=True)
    initial_value = serializers.FloatField(required=True)
    # parameters = ParameterValidator(many=True, min_length=1, required=True)


# Module object from Hydrofabric containing module parameters and output variables
class ModuleMetadataHydrofabricValidator(BaseSerializer):
    name = serializers.CharField(min_length=2, required=True, allow_blank=False)
    module_parameters = ModuleParametersValidator(many=True)
    module_output_variables = ModuleOutputVariablesValidator(many=True)


# List of module objects from Hydrofabric containing module parameters and output variables
class ModuleDataHydrofabricListValidator(BaseSerializer):
    modules_data = ModuleMetadataHydrofabricValidator(many=True, min_length=1, required=True)


# This class extends the original serializers.Serializer, since we want to ignore extra fields
class ModuleHydrofabricVersionValidator(serializers.Serializer):
    version = serializers.CharField(required=True, allow_blank=False)


# Module objects from Hydrofabric contain group names and version
class ModuleHydrofabricValidator(BaseSerializer):
    name = serializers.CharField(min_length=2, required=True, allow_blank=False)
    description = serializers.CharField(min_length=2, required=True, allow_blank=False)
    groups = serializers.ListSerializer(min_length=1, child=serializers.CharField(min_length=2, required=True, allow_blank=False))
    version = ModuleHydrofabricVersionValidator(required=True)


# List of module objects from Hydrofabric containing group names and version
class ModuleHydrofabricListValidator(BaseSerializer):
    modules_data = ModuleHydrofabricValidator(many=True, min_length=1, required=True)


class ReportIterationValidator(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    iteration = serializers.IntegerField(required=True, min_value=1)


class TuningParametersValidator(BaseSerializer):
    name = serializers.CharField(required=True, allow_blank=False)
    module = serializers.CharField(required=True, allow_blank=False)
    minimum = serializers.FloatField(required=True)
    maximum = serializers.FloatField(required=True)
    initial_value = serializers.FloatField(required=True)


class CalibrationTimeControls(BaseSerializer):
    calibration_start_time = serializers.DateTimeField(required=True, format=OUTPUT_DATE_FORMAT, input_formats=[INPUT_DATE_FORMAT],
                                                       default_timezone=timezone.utc)
    calibration_end_time = serializers.DateTimeField(required=True, format=OUTPUT_DATE_FORMAT, input_formats=[INPUT_DATE_FORMAT],
                                                     default_timezone=timezone.utc)
    simulation_start_time = serializers.DateTimeField(required=True, format=OUTPUT_DATE_FORMAT, input_formats=[INPUT_DATE_FORMAT],
                                                      default_timezone=timezone.utc)
    simulation_end_time = serializers.DateTimeField(required=True, format=OUTPUT_DATE_FORMAT, input_formats=[INPUT_DATE_FORMAT],
                                                    default_timezone=timezone.utc)

    def validate(self, data):
        if data['calibration_start_time'] > data['calibration_end_time']:
            raise serializers.ValidationError({'calibration_start_time': 'calibration_end_time must occur after calibration_start_time'})
        if data['simulation_start_time'] > data['simulation_end_time']:
            raise serializers.ValidationError({'simulation_start_time': 'simulation_end_time must occur after simulation_start_time'})
        if data['simulation_start_time'] > data['calibration_start_time']:
            raise serializers.ValidationError({'simulation_start_time': 'calibration_start_time must occur after simulation_start_time'})
        if data['calibration_end_time'] > data['simulation_end_time']:
            raise serializers.ValidationError({'simulation_start_time': 'simulation_end_time must occur after calibration_end_time'})
        return data


class ValidationTimeControls(BaseSerializer):
    validation_start_time = serializers.DateTimeField(required=True, format=OUTPUT_DATE_FORMAT, input_formats=[INPUT_DATE_FORMAT])
    validation_end_time = serializers.DateTimeField(required=True, format=OUTPUT_DATE_FORMAT, input_formats=[INPUT_DATE_FORMAT])
    simulation_start_time = serializers.DateTimeField(required=True, format=OUTPUT_DATE_FORMAT, input_formats=[INPUT_DATE_FORMAT])
    simulation_end_time = serializers.DateTimeField(required=True, format=OUTPUT_DATE_FORMAT, input_formats=[INPUT_DATE_FORMAT])

    def validate(self, data):
        if data['validation_start_time'] > data['validation_end_time']:
            raise serializers.ValidationError({'validation_start_time': 'validation_end_time must occur after validation_start_time'})
        if data['simulation_start_time'] > data['simulation_end_time']:
            raise serializers.ValidationError({'simulation_start_time': 'simulation_end_time must occur after simulation_start_time'})
        if data['simulation_start_time'] > data['validation_start_time']:
            raise serializers.ValidationError({'simulation_start_time': 'validation_start_time must occur after simulation_start_time'})
        if data['validation_end_time'] > data['simulation_end_time']:
            raise serializers.ValidationError({'simulation_start_time': 'simulation_end_time must occur after validation_end_time'})
        return data


class OutputVariableValidator(BaseSerializer):
    module = serializers.CharField(required=True, allow_blank=False)
    name = serializers.CharField(required=True, allow_blank=False)


class SaveTuningValidator(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    parameters = TuningParametersValidator(many=True, required=False)
    calibration_times = CalibrationTimeControls(required=False)
    validation_times = ValidationTimeControls(required=False)
    automatic_validation = serializers.BooleanField(required=True)
    output_variable_to_calibrate = OutputVariableValidator(required=False)


class MetricNameValidator(BaseSerializer):
    metric = serializers.CharField(min_length=3, allow_blank=False)


class AlgorithmInputsValidator(BaseSerializer):
    name = serializers.CharField(required=True, allow_blank=False)
    value = serializers.FloatField(required=True)


class SaveOptimizationValidator(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    optimization_inputs = AlgorithmInputsValidator(many=True, required=False)
    optimization = serializers.CharField(allow_blank=False, required=False)
    objective_function = serializers.CharField(allow_blank=False, required=False)
    streamflow_threshold = serializers.FloatField(required=False)
    stop_criteria = serializers.IntegerField(required=False)
    plot_generation_frequency = serializers.IntegerField(required=False)
