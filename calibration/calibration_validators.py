from datetimerange import DateTimeRange
from rest_framework import serializers
from rest_framework.fields import empty
from rest_framework.settings import api_settings

from calibration.enums import DataTypeEnum, UnitsEnum, LocationEnum, ForcingSourceEnum, ObservationalSourceEnum


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


class UploadForcingValidator(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    forcing_user_dir = serializers.CharField(required=True, allow_blank=False)


def forcingSourceValidator(value):
    if value not in ForcingSourceEnum.values():
        raise serializers.ValidationError(f"This field must be one of {ForcingSourceEnum.values()}")


def observationSourceValidator(value):
    if value not in ObservationalSourceEnum.values():
        raise serializers.ValidationError(f"This field must be one of {ObservationalSourceEnum.values()}")


class SaveGageValidator(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    gage_id = serializers.CharField(min_length=2, required=False, allow_blank=False)
    forcing_source = serializers.CharField(required=False, validators=[forcingSourceValidator])
    observational_source = serializers.CharField(required=False, validators=[observationSourceValidator])


def dataTypeValidator(value):
    if value not in DataTypeEnum.values():
        raise serializers.ValidationError(f"This field must be one of {DataTypeEnum.values()}")


def unitsValidator(value):
    if value not in UnitsEnum.values():
        raise serializers.ValidationError(f"This field must be one of {UnitsEnum.values()}")


def locationValidator(value):
    if value not in LocationEnum.values():
        raise serializers.ValidationError(f"This field must be one of {LocationEnum.values()}")


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


# Geopackage from Hydrofabric
class GeopackageValidator(BaseSerializer):
    uri = serializers.CharField(required=True, allow_blank=False)
    creation_date = serializers.DateTimeField(required=True)


# Output variables from Hydrofabric
class ModuleOutputVariablesValidator(BaseSerializer):
    name = serializers.CharField(min_length=2, required=True, allow_blank=False)
    description = serializers.CharField(required=True, allow_blank=False)


# This class extends the original serializers.Serializer, since we want to ignore extra fields
# Parameters from Hydrofabric
class ModuleParametersValidator(serializers.Serializer):
    name = serializers.CharField(min_length=2, required=True, allow_blank=False)
    data_type = serializers.CharField(required=True, validators=[dataTypeValidator])
    description = serializers.CharField(required=True, allow_blank=False)


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

    def validate(self, data):
        if data['minimum'] > data['maximum']:
            raise serializers.ValidationError(
                f"Minimum ({data['minimum']}) must be less than maximum ({data['maximum']}) for parameter {data['name']}")
        if data['initial_value'] < data['minimum'] or data['initial_value'] > data['maximum']:
            raise serializers.ValidationError(
                f"Value {data['initial_value']} must be between minimum ({data['minimum']:.10f}) and maximum ({data['maximum']:.10f}) for parameter {data['name']}")
        return data


class CalibrationTimeControls(BaseSerializer):
    calibration_start_time = serializers.DateTimeField(required=True)
    calibration_end_time = serializers.DateTimeField(required=True)
    simulation_start_time = serializers.DateTimeField(required=True)
    simulation_end_time = serializers.DateTimeField(required=True)

    def validate(self, data):
        calibration_range = DateTimeRange(data['calibration_start_time'], data['calibration_end_time'])
        if not calibration_range.is_valid_timerange():
            raise serializers.ValidationError(f'{calibration_range} is not a valid time range')

        simulation_range = DateTimeRange(data['simulation_start_time'], data['simulation_end_time'])
        if not simulation_range.is_valid_timerange():
            raise serializers.ValidationError(f'{simulation_range} is not a valid time range')

        if (simulation_range.start_datetime not in calibration_range) or (simulation_range.end_datetime not in calibration_range):
            raise serializers.ValidationError(f'Simulation range {simulation_range} must be contained within calibration range {calibration_range}')

        return data


class ValidationTimeControls(BaseSerializer):
    validation_start_time = serializers.DateTimeField(required=True)
    validation_end_time = serializers.DateTimeField(required=True)
    simulation_start_time = serializers.DateTimeField(required=True)
    simulation_end_time = serializers.DateTimeField(required=True)

    def validate(self, data):
        validation_range = DateTimeRange(data['validation_start_time'], data['validation_end_time'])
        if not validation_range.is_valid_timerange():
            raise serializers.ValidationError(
                f'{validation_range} is not a valid time range')

        simulation_range = DateTimeRange(data['simulation_start_time'], data['simulation_end_time'])
        if not simulation_range.is_valid_timerange():
            raise serializers.ValidationError(
                f'{simulation_range} is not a valid time range')

        if simulation_range.get_start_time_str() not in validation_range or simulation_range.get_end_time_str() not in validation_range:
            raise serializers.ValidationError(f'Simulation range {simulation_range} must be contained within validation range {validation_range}')

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

    def validate(self, data):
        if 'calibration_times' in data and 'validation_times' in data:
            # Make sure there is no overlap between calibration times and validation times
            calibration_range = DateTimeRange(data['calibration_times']['calibration_start_time'], data['calibration_times']['calibration_end_time'])
            validation_range = DateTimeRange(data['validation_times']['validation_start_time'], data['validation_times']['validation_end_time'])
            if calibration_range.is_intersection(validation_range):
                raise serializers.ValidationError(f"Calibration range {calibration_range} cannot intersect validation range {validation_range}")
        return data


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
