import re

from datetimerange import DateTimeRange
from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail
from rest_framework.fields import empty
from rest_framework.settings import api_settings

from calibration.enums import DataTypeEnum, UnitsEnum, LocationEnum, ForcingSourceEnum, ObservationalSourceEnum, DomainEnum, StatusEnum


# The validators/serializers have 2 purposes.
# The ones called 'validator' are used for validating inputs
# The ones called 'serializer' are used for serializing the responses from endpoints
# Both of them are used to document the inputs and outputs for use by drf_spectacular


class BaseSerializer(serializers.Serializer):
    def run_validation(self, data=None):
        if data is not None and data != empty:
            unknown = set(data) - set(self.fields)
            if unknown:
                errors = ["Unknown field: {}".format(f) for f in unknown]
                raise serializers.ValidationError({
                    api_settings.NON_FIELD_ERRORS_KEY: errors,
                })

        return super().run_validation(data)


def forcingSourceValidator(value):
    if value not in ForcingSourceEnum.values():
        raise serializers.ValidationError(f"This field must be one of {ForcingSourceEnum.values()}")


def domainNameValidator(value):
    if value not in DomainEnum.values():
        raise serializers.ValidationError(f'This field must be one of {DomainEnum.values()}')


def observationSourceValidator(value):
    if value not in ObservationalSourceEnum.values():
        raise serializers.ValidationError(f"This field must be one of {ObservationalSourceEnum.values()}")


def dataTypeValidator(value):
    if value not in DataTypeEnum.values():
        raise serializers.ValidationError(f"This field must be one of {DataTypeEnum.values()}")


def unitsValidator(value):
    if value not in UnitsEnum.values():
        raise serializers.ValidationError(f"This field must be one of {UnitsEnum.values()}")


def locationValidator(value):
    if value not in LocationEnum.values():
        raise serializers.ValidationError(f"This field must be one of {LocationEnum.values()}")


def statusValidator(value):
    if value not in StatusEnum.values():
        raise serializers.ValidationError(f"This field must be one of {StatusEnum.values()}")


def s3FileValidator(value):
    pattern = re.compile('^s3://([^/]+)/(.*?([^/]+))$')
    if not pattern.match(value):
        raise serializers.ValidationError('This field must be a valid S3 uri to a file')


def s3DirectoryValidator(value):
    pattern = re.compile('^s3://([^/]+)/(.*?([^/]+)/)$')
    if not pattern.match(value):
        raise serializers.ValidationError('This field must be a valid S3 uri to a directory')


class CalibrationRunSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)


class CalibrationPlotNameSerializer(BaseSerializer):
    cal_plot_name = serializers.CharField(required=True)


##################################
# Landing page
##################################
class JobsResponseSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    gage_id = serializers.CharField(required=True, allow_null=True)
    status = serializers.CharField(required=True, validators=[statusValidator])
    calibration_start_period = serializers.DateTimeField(required=False, allow_null=True)
    calibration_end_period = serializers.DateTimeField(required=False, allow_null=True)
    formulation_name = serializers.CharField(required=False, allow_null=True)
    run_date = serializers.DateTimeField(required=True, allow_null=True)
    owner = serializers.CharField(required=True, allow_null=True)


class GetJobsResponseSerializer(BaseSerializer):
    jobs = serializers.ListSerializer(child=JobsResponseSerializer(), required=True, allow_empty=True)


class FooterResponseSerializer(BaseSerializer):
    version = serializers.CharField(required=True)
    contact_email = serializers.CharField(required=True)


##################################
# Gage Tab
##################################

class DomainSerializer(BaseSerializer):
    domain = serializers.CharField(required=True, validators=[domainNameValidator])


class GageIdSerializer(BaseSerializer):
    gage_id = serializers.CharField(required=True, allow_blank=False)


class UploadForcingSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    forcing_user_dir = serializers.CharField(required=True, allow_blank=False)


class SaveGageRequestSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    gage_id = serializers.CharField(required=False, allow_blank=False)
    forcing_source = serializers.CharField(required=False, validators=[forcingSourceValidator])
    observational_source = serializers.CharField(required=False, validators=[observationSourceValidator])


class GageSerializer(BaseSerializer):
    gage_id = serializers.CharField(required=True, allow_blank=False)
    agency = serializers.CharField(required=True, allow_blank=False)
    station_name = serializers.CharField(required=True, allow_blank=False)
    latitude = serializers.FloatField(required=True)
    longitude = serializers.FloatField(required=True)
    altitude = serializers.FloatField(required=True)


class SaveGageResponseSerializer(BaseSerializer):
    message = serializers.CharField(required=True)
    calibration_run_id = serializers.IntegerField(required=True)
    status = serializers.CharField(validators=[statusValidator], required=True)
    geopackage_image = serializers.CharField(required=False)


class DomainResponseSerializer(BaseSerializer):
    name = serializers.CharField(validators=[domainNameValidator], required=True)
    description = serializers.CharField(required=True, allow_blank=False)
    is_active = serializers.BooleanField(required=True)


class GagesSerializer(BaseSerializer):
    gage_id = serializers.CharField(required=True, allow_blank=False)
    nws_id = serializers.CharField(required=False, allow_null=True, allow_blank=False)
    domain = serializers.CharField(required=True, validators=[domainNameValidator])
    nwm_v3_calibrated = serializers.BooleanField(required=True)


class ForcingSourceSerializer(BaseSerializer):
    name = serializers.CharField(validators=[forcingSourceValidator], required=True)
    description = serializers.CharField(required=True)
    is_active = serializers.BooleanField(required=True)


class ObservationalSourceSerializer(BaseSerializer):
    name = serializers.CharField(validators=[observationSourceValidator], required=True)
    description = serializers.CharField(required=True)
    is_active = serializers.BooleanField(required=True)


class LoadGageResponseSerializer(BaseSerializer):
    status = serializers.CharField(validators=[statusValidator], required=True)
    calibration_run_id = serializers.IntegerField(required=True)
    forcing_source = serializers.CharField(required=False, validators=[forcingSourceValidator])
    observational_source = serializers.CharField(required=False, validators=[ObservationalSourceSerializer])
    forcing_user_dir = serializers.CharField(required=False)
    forcing_source_values = ForcingSourceSerializer(many=True)
    observational_source_values = ObservationalSourceSerializer(many=True)
    observational_user_filename = serializers.CharField(required=False)
    gages = GagesSerializer(required=True, many=True)
    gage = GageSerializer(required=False)
    domain_values = DomainResponseSerializer(many=True)


class GenericResponseSerializer(BaseSerializer):
    message = serializers.CharField(required=True)
    calibration_run_id = serializers.IntegerField(required=True)
    status = serializers.CharField(validators=[statusValidator], required=True)


class CreateCalibrationRunSerializer(BaseSerializer):
    message = serializers.CharField(required=True)
    calibration_run_id = serializers.IntegerField(required=True)


class GenericMessageResponseSerializer(BaseSerializer):
    message = serializers.CharField(required=True)


# Geopackage from Hydrofabric
class GeopackageSerializer(BaseSerializer):
    uri = serializers.CharField(required=True, allow_blank=False)
    creation_date = serializers.DateTimeField(required=True)


##################################
# Plot Definitions Tab
##################################

class PlotListStaticSerializer(BaseSerializer):
    name = serializers.CharField(required=True, allow_blank=False)
    description = serializers.CharField(required=True, allow_blank=False)
    filename = serializers.CharField(required=True, allow_blank=False)


class LoadPlotDefinitionsResponseSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    plot_list = PlotListStaticSerializer(many=True)


class LoadPlotResponseSerializer(BaseSerializer):
    name = serializers.CharField(required=True, allow_blank=False)
    description = serializers.CharField(required=True, allow_blank=False)
    filename = serializers.CharField(required=True, allow_blank=False)


##################################
# Formulation Tab
##################################

class SlothParameters(BaseSerializer):
    param_name = serializers.CharField(required=True, allow_blank=False)
    param_count = serializers.IntegerField(required=True)
    param_type = serializers.CharField(required=True, validators=[dataTypeValidator])
    param_units = serializers.CharField(required=True, validators=[unitsValidator])
    param_location = serializers.CharField(required=True, validators=[locationValidator])
    param_value = serializers.FloatField(required=True)
    maps_to_module = serializers.CharField(required=True, allow_blank=False)
    maps_to_variable_name = serializers.CharField(required=True, allow_blank=False)


class SaveFormulationRequestSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    formulation_name = serializers.CharField(required=False, allow_blank=False)
    modules = serializers.ListField(child=serializers.CharField(required=True), min_length=2)
    use_sloth = serializers.BooleanField(required=True)
    sloth_parameters = SlothParameters(required=False, many=True, min_length=1)


class ModuleStaticSerializer(BaseSerializer):
    name = serializers.CharField(required=True, allow_blank=False)
    groups = serializers.ListField(child=serializers.CharField(required=True))
    used_by_calibration_run = serializers.BooleanField(required=True)


class LoadFormulationResponseSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    formulation_name = serializers.CharField(required=False, allow_blank=False)
    modules = ModuleStaticSerializer(many=True)
    use_sloth = serializers.BooleanField(required=True)
    sloth_parameters = SlothParameters(required=False, many=True, )
    status = serializers.CharField(validators=[statusValidator], required=True)


##################################
# Tuning Tab
##################################

# Output variables from Hydrofabric
class ModuleOutputVariablesSerializer(BaseSerializer):
    name = serializers.CharField(required=True, allow_blank=False)
    description = serializers.CharField(required=True, allow_blank=False)


# This class extends the original serializers.Serializer, since we want to ignore extra fields
# Parameters from Hydrofabric
class ModuleParametersSerializer(serializers.Serializer):
    name = serializers.CharField(required=True, allow_blank=False)
    data_type = serializers.CharField(required=True, validators=[dataTypeValidator])
    description = serializers.CharField(required=True, allow_blank=False)
    minimum = serializers.FloatField(required=False)
    maximum = serializers.FloatField(required=False)
    # TODO I think this should be required and not null
    initial_value = serializers.FloatField(required=False, allow_null=True)


# Module object from Hydrofabric containing module parameters and output variables
class ModuleMetadataHydrofabricSerializer(BaseSerializer):
    module_name = serializers.CharField(required=True, allow_blank=False)
    module_parameters = ModuleParametersSerializer(many=True)
    module_output_variables = ModuleOutputVariablesSerializer(many=True)


# List of module objects from Hydrofabric containing module parameters and output variables
class ModuleDataHydrofabricListSerializer(BaseSerializer):
    modules = ModuleMetadataHydrofabricSerializer(many=True, min_length=1, required=True)


# This class extends the original serializers.Serializer, since we want to ignore extra fields
class ModuleHydrofabricVersionSerializer(serializers.Serializer):
    commit_hash = serializers.CharField(required=True, allow_blank=False)


# Module objects from Hydrofabric contain group names and version
class ModuleHydrofabricSerializer(BaseSerializer):
    module_name = serializers.CharField(required=True, allow_blank=False)
    description = serializers.CharField(required=True, allow_blank=False)
    groups = serializers.ListSerializer(min_length=1, child=serializers.CharField(required=True, allow_blank=False))
    module_version = ModuleHydrofabricVersionSerializer(required=True)


# List of module objects from Hydrofabric containing group names and version
class ModuleHydrofabricListSerializer(BaseSerializer):
    modules = ModuleHydrofabricSerializer(many=True, min_length=1, required=True)


# Used by SaveTuningRequestValidator
class TuningParametersSerializer(BaseSerializer):
    name = serializers.CharField(required=True, allow_blank=False)
    minimum = serializers.FloatField(required=True)
    maximum = serializers.FloatField(required=True)
    initial_value = serializers.FloatField(required=True, allow_null=True)
    module = serializers.CharField(required=True, allow_blank=False)

    def validate(self, data):
        if data['minimum'] > data['maximum']:
            raise serializers.ValidationError(
                f"Minimum ({data['minimum']}) must be less than maximum ({data['maximum']}) for parameter {data['name']}")
        if data['initial_value'] is not None and not (data['minimum'] <= data['initial_value'] <= data['maximum']):
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


# Used for the output from Hydrofabric
class OutputVariableMetadataSerializer(BaseSerializer):
    name = serializers.CharField(required=True, allow_blank=False)
    description = serializers.CharField(required=True, allow_blank=False)


# Used by SaveTuningRequestValidator
class OutputVariableSerializer(BaseSerializer):
    name = serializers.CharField(required=True, allow_blank=False)
    module = serializers.CharField(required=True, allow_blank=False)


class SaveTuningRequestSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    parameters = TuningParametersSerializer(many=True, required=False)
    calibration_times = CalibrationTimeControls(required=False)
    validation_times = ValidationTimeControls(required=False)
    automatic_validation = serializers.BooleanField(required=True)
    output_variable_to_calibrate = OutputVariableSerializer(required=False)

    def validate(self, data):
        if 'calibration_times' in data and 'validation_times' in data:
            # Make sure there is no overlap between calibration times and validation times
            calibration_range = DateTimeRange(data['calibration_times']['calibration_start_time'], data['calibration_times']['calibration_end_time'])
            validation_range = DateTimeRange(data['validation_times']['validation_start_time'], data['validation_times']['validation_end_time'])
            if calibration_range.is_intersection(validation_range):
                raise serializers.ValidationError(f"Calibration range {calibration_range} cannot intersect validation range {validation_range}")
        return data


class TimeRangeSerializer(BaseSerializer):
    start_time = serializers.DateTimeField(required=True)
    end_time = serializers.DateTimeField(required=True)


class ModuleMetadataStaticSerializer(BaseSerializer):
    name = serializers.CharField(required=True, allow_blank=False)
    parameters = ModuleParametersSerializer(required=True, many=True)
    output_variables = OutputVariableMetadataSerializer(required=True, many=True)


class LoadTuningResponseSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    calibration_times = CalibrationTimeControls(required=False)
    validation_times = ValidationTimeControls(required=False)
    automatic_validation = serializers.BooleanField(required=True)
    output_variable_to_calibrate = OutputVariableSerializer(required=False)
    time_range = TimeRangeSerializer(required=False)
    modules = ModuleMetadataStaticSerializer(many=True, required=False)
    status = serializers.CharField(validators=[statusValidator], required=True)


##################################
# Optimization Tab
##################################


class OptimizationInputsSerializer(BaseSerializer):
    name = serializers.CharField(required=True, allow_blank=False)
    value = serializers.FloatField(required=True)


class SaveOptimizationRequestSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    optimization_inputs = OptimizationInputsSerializer(many=True, required=False)
    optimization = serializers.CharField(allow_blank=False, required=False)
    objective_function = serializers.CharField(allow_blank=False, required=False)
    streamflow_threshold = serializers.FloatField(required=False)
    peak_flow_threshold = serializers.FloatField(required=False)
    stop_criteria = serializers.IntegerField(required=False)
    plot_frequency = serializers.IntegerField(required=False)


class SaveOptimizationResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    calibration_run_id = serializers.IntegerField()
    status = serializers.CharField(validators=[statusValidator], required=True)


class OptimizationInputStaticSerializer(serializers.Serializer):
    name = serializers.CharField(required=True)
    description = serializers.CharField(required=True)
    data_type = serializers.CharField(required=True, validators=[dataTypeValidator])
    is_active = serializers.BooleanField(required=True)


class OptimizationInputsUserSerializer(serializers.Serializer):
    name = serializers.CharField(required=True)
    value = serializers.FloatField(required=True)


class MetricSerializer(serializers.Serializer):
    name = serializers.CharField()
    description = serializers.CharField()
    is_active = serializers.BooleanField()
    categorical = serializers.BooleanField()
    event_based = serializers.BooleanField()


class OptimizationStaticSerializer(serializers.Serializer):
    name = serializers.CharField()
    description = serializers.CharField()
    is_active = serializers.BooleanField()
    inputs = OptimizationInputStaticSerializer(many=True)


class LoadOptimizationResponseSerializer(serializers.Serializer):
    calibration_run_id = serializers.IntegerField(required=True)
    status = serializers.CharField(validators=[statusValidator], required=True)
    streamflow_threshold = serializers.FloatField(required=False)
    peak_flow_threshold = serializers.FloatField(required=False)
    metrics = MetricSerializer(many=True)
    optimization = serializers.CharField(required=False)
    optimization_inputs = OptimizationInputsUserSerializer(many=True, required=False)
    objective_function = serializers.CharField(required=False)
    optimizations = OptimizationStaticSerializer(many=True)
    plot_frequency = serializers.IntegerField(required=False)
    stop_criteria = serializers.CharField(required=False)


class ObservationalHydrofabricSerializer(BaseSerializer):
    uri = serializers.CharField(required=True, validators=[s3FileValidator])


class ForcingHydrofabricSerializer(BaseSerializer):
    uri = serializers.CharField(required=True, validators=[s3DirectoryValidator])


##################################
# Run Tab
##################################

class IsReadyResponseSerializer(BaseSerializer):
    message = serializers.CharField(required=True)
    errors = serializers.ListField(required=False, child=serializers.CharField(required=True))


##################################
# Import/Export
##################################
class ExportResponseSerializer(BaseSerializer):
    metadata = serializers.DictField(required=False)
    gage_id = serializers.CharField(required=True, allow_null=True)
    forcing_source = serializers.CharField(required=False, validators=[forcingSourceValidator])
    forcing_user_dir = serializers.CharField(required=False, allow_blank=False, allow_null=True)
    forcing_dir_path = serializers.CharField(required=False, allow_blank=False, allow_null=True)
    observational_source = serializers.CharField(required=False, validators=[observationSourceValidator])
    observational_user_filename = serializers.CharField(required=False, allow_blank=False, allow_null=True)
    observational_file_path = serializers.CharField(required=False, allow_blank=False)
    geopackage = serializers.CharField(required=True, allow_null=True)
    modules = serializers.ListField(child=serializers.CharField(required=True), required=True)
    formulation_name = serializers.CharField(required=True, allow_null=True)
    use_sloth = serializers.BooleanField(required=True, allow_null=False)
    sloth_parameters = SlothParameters(required=False, many=True, allow_empty=False)
    automatic_validation = serializers.BooleanField(required=True, allow_null=False)
    output_variable_to_calibrate = OutputVariableSerializer(required=True, allow_null=False)
    calibration_times = CalibrationTimeControls(required=True)
    validation_times = ValidationTimeControls(required=True)
    time_range = TimeRangeSerializer(required=False)
    streamflow_threshold = serializers.FloatField(required=True)
    peak_flow_threshold = serializers.FloatField(required=True)
    parameters = TuningParametersSerializer(many=True, required=False)
    objective_function = serializers.CharField(required=True, allow_null=True)
    optimization_inputs = OptimizationInputsSerializer(many=True, required=False)
    optimization = serializers.CharField(required=True, allow_null=True)
    plot_frequency = serializers.IntegerField(required=True, allow_null=False)
    stop_criteria = serializers.IntegerField(required=True, allow_null=False)


class ImportSerializer(serializers.Serializer):
    run_after_import = serializers.BooleanField(required=False, default=False)
    metadata = serializers.DictField(required=False)
    gage_id = serializers.CharField(required=True, allow_null=False)
    forcing_source = serializers.CharField(required=True, validators=[forcingSourceValidator])
    forcing_user_dir = serializers.CharField(required=False, allow_blank=False, allow_null=True)
    forcing_dir_path = serializers.CharField(required=True, allow_blank=False, allow_null=True)
    observational_source = serializers.CharField(required=True, validators=[observationSourceValidator])
    observational_user_filename = serializers.CharField(required=False, allow_blank=False, allow_null=True)
    observational_file_path = serializers.CharField(required=True, allow_blank=False)
    geopackage = serializers.CharField(required=True, allow_null=True)
    modules = serializers.ListField(child=serializers.CharField(required=True), required=True, allow_empty=False)
    sloth_parameters = SlothParameters(required=False, many=True, allow_empty=False)
    formulation_name = serializers.CharField(required=True, allow_null=True)
    use_sloth = serializers.BooleanField(required=True, allow_null=False)
    automatic_validation = serializers.BooleanField(required=True, allow_null=False)
    output_variable_to_calibrate = OutputVariableSerializer(required=True, allow_null=False)
    calibration_times = CalibrationTimeControls(required=True)
    validation_times = ValidationTimeControls(required=True)
    streamflow_threshold = serializers.FloatField(required=True)
    peak_flow_threshold = serializers.FloatField(required=True)
    parameters = TuningParametersSerializer(many=True, required=False)
    objective_function = serializers.CharField(required=True, allow_null=True)
    optimization_inputs = OptimizationInputsSerializer(many=True, required=False)
    optimization = serializers.CharField(required=True, allow_null=True)
    plot_frequency = serializers.IntegerField(required=True, allow_null=False)
    stop_criteria = serializers.IntegerField(required=True, allow_null=False)


##################################
# Misc
##################################
class ReportIterationSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    iteration = serializers.IntegerField(required=True, min_value=1)


class ErrorResponseSerializer(BaseSerializer):
    error = serializers.CharField(required=True)


class ErrorDetailListField(serializers.ListField):
    child = serializers.CharField()

    def to_representation(self, value):
        # Ensure that the value is a list of ErrorDetail objects
        if not all(isinstance(item, ErrorDetail) for item in value):
            raise serializers.ValidationError("All items must be instances of ErrorDetail.")
        return [str(item) for item in value]

    def to_internal_value(self, data):
        if not isinstance(data, list):
            raise serializers.ValidationError("Expected a list of strings.")
        return [ErrorDetail(item) for item in data]


class ValidationExceptionSerializer(BaseSerializer):
    # validation_error = serializers.DictField(child=ErrorDetailListField(), required=True)
    validation_error = serializers.JSONField(required=True)


class ValidationErrorSerializer(BaseSerializer):
    validation_error = serializers.CharField(required=True)


class ExceptionResponseSerializer(BaseSerializer):
    exception = serializers.CharField(required=True)
