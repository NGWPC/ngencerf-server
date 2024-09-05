import re

from datetimerange import DateTimeRange
from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail
from rest_framework.fields import empty
from rest_framework.settings import api_settings

from calibration.enums import DataTypeEnum, UnitsEnum, LocationEnum, ForcingSourceEnum, ObservationalSourceEnum, DomainEnum, StatusEnum, \
    OptimizationEnum


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


def optimizationValidator(value):
    if value not in OptimizationEnum.values():
        raise serializers.ValidationError(f"This field must be one of {OptimizationEnum.values()}")


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
# Common serializers that need to be defined before usage
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


class TimeRangeSerializerAllowEmpty(BaseSerializer):
    start_time = serializers.DateTimeField(required=False)
    end_time = serializers.DateTimeField(required=False)


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


class CalibrationTimeControlsAllowEmpty(BaseSerializer):
    calibration_start_time = serializers.DateTimeField(required=False)
    calibration_end_time = serializers.DateTimeField(required=False)
    simulation_start_time = serializers.DateTimeField(required=False)
    simulation_end_time = serializers.DateTimeField(required=False)


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


class ValidationTimeControlsAllowEmpty(BaseSerializer):
    validation_start_time = serializers.DateTimeField(required=False)
    validation_end_time = serializers.DateTimeField(required=False)
    simulation_start_time = serializers.DateTimeField(required=False)
    simulation_end_time = serializers.DateTimeField(required=False)


# TODO See if we can eliminate 1 of these after Hydrofabric implementation
# Used for the output from Hydrofabric
class OutputVariableMetadataSerializer(BaseSerializer):
    name = serializers.CharField(required=True, allow_blank=False)
    description = serializers.CharField(required=True, allow_blank=False)


# Used by SaveTuningRequestValidator
class OutputVariableSerializer(BaseSerializer):
    name = serializers.CharField(required=True, allow_blank=False)
    module = serializers.CharField(required=True, allow_blank=False)


# Used by Export
class OutputVariableSerializerAllowEmpty(BaseSerializer):
    name = serializers.CharField(required=False, allow_blank=False)
    module = serializers.CharField(required=False, allow_blank=False)


class SaveTuningParametersSerializer(BaseSerializer):
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


class LoadTuningParametersSerializer(BaseSerializer):
    name = serializers.CharField(required=True, allow_blank=False)
    minimum = serializers.FloatField(required=True)
    maximum = serializers.FloatField(required=True)
    initial_value = serializers.FloatField(required=True, allow_null=True)
    data_type = serializers.CharField(required=True, validators=[dataTypeValidator])
    description = serializers.CharField(required=True, allow_blank=False)
    user_selected_for_tuning = serializers.BooleanField(required=True)


class OptimizationInputsSerializer(BaseSerializer):
    name = serializers.CharField(required=True, allow_blank=False)
    value = serializers.FloatField(required=True)


class GageSerializer(BaseSerializer):
    gage_id = serializers.CharField(required=True, allow_blank=False)
    agency = serializers.CharField(required=True, allow_blank=False)
    station_name = serializers.CharField(required=True, allow_blank=False)
    latitude = serializers.FloatField(required=True, allow_null=True)
    longitude = serializers.FloatField(required=True, allow_null=True)
    altitude = serializers.FloatField(required=True, allow_null=True)


# This class extends the original serializers.Serializer, since we want to ignore extra fields
# Parameters from Hydrofabric
class ModuleParametersSerializer(serializers.Serializer):
    name = serializers.CharField(required=True, allow_blank=False)
    data_type = serializers.CharField(required=True, validators=[dataTypeValidator])
    description = serializers.CharField(required=True, allow_blank=False)
    minimum = serializers.FloatField(required=False, allow_null=True)
    maximum = serializers.FloatField(required=False, allow_null=True)
    initial_value = serializers.FloatField(required=False, allow_null=True)


# class ModuleTuningParametersSerializer(BaseSerializer):
#     name = serializers.CharField(required=True, allow_blank=False)
#     minimum = serializers.FloatField(required=True, allow_null=True)
#     maximum = serializers.FloatField(required=True, allow_null=True)
#     initial_value = serializers.FloatField(required=True, allow_null=True)
#     user_selected_for_tuning = serializers.BooleanField(required=True)
#

# Used by LoadTuningParameters
class ModuleMetadataStaticSerializer(BaseSerializer):
    name = serializers.CharField(required=True, allow_blank=False)
    parameters = LoadTuningParametersSerializer(required=True, many=True)
    output_variables = OutputVariableMetadataSerializer(required=True, many=True)


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


class LoadCalibrationRunResponseSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    gage = GageSerializer(required=True, allow_null=True)
    forcing_source = serializers.CharField(required=True, allow_null=True, validators=[forcingSourceValidator])
    forcing_hydrofabric_dir_path = serializers.CharField(required=True, allow_blank=False, allow_null=True)
    observational_source = serializers.CharField(required=True, allow_null=True, validators=[observationSourceValidator])
    observational_hydrofabric_file_path = serializers.CharField(required=True, allow_blank=False, allow_null=True)
    geopackage_image_url = serializers.CharField(required=False)
    modules = serializers.ListField(child=serializers.CharField(required=False))
    formulation_name = serializers.CharField(required=True, allow_null=True, allow_blank=False)
    use_sloth = serializers.BooleanField(default=False)
    sloth_parameters = SlothParameters(many=True, default=[])
    automatic_validation = serializers.BooleanField(default=False)
    time_range = TimeRangeSerializerAllowEmpty(required=False)
    calibration_times = CalibrationTimeControlsAllowEmpty(required=False)
    validation_times = ValidationTimeControlsAllowEmpty(required=False)
    output_variable_to_calibrate = OutputVariableSerializerAllowEmpty(required=True, )

    objective_function = serializers.CharField(required=True, allow_null=True)
    streamflow_threshold = serializers.FloatField(required=False, allow_null=True)
    peak_flow_threshold = serializers.FloatField(required=False, allow_null=True)
    optimization = serializers.CharField(allow_blank=False, required=True, allow_null=True, validators=[optimizationValidator])
    optimization_inputs = OptimizationInputsSerializer(many=True, default=[])
    plot_frequency = serializers.IntegerField(required=True, allow_null=True)
    stop_criteria = serializers.IntegerField(required=True, allow_null=True, min_value=2)
    status = serializers.CharField(validators=[statusValidator], required=True)


##################################
# Gage Tab
##################################

class DomainSerializer(BaseSerializer):
    domain = serializers.CharField(required=True, validators=[domainNameValidator])


class GageIdSerializer(BaseSerializer):
    gage_id = serializers.CharField(required=True, allow_blank=False)


class GageIdOptionalSerializer(BaseSerializer):
    gage_id = serializers.CharField(required=False, allow_blank=False)


class UploadForcingSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    forcing_files = serializers.FileField(required=True)

    def validate_forcing_files(self, value):
        request = self.context.get('request')
        files = request.FILES.getlist('forcing_files')
        if len(files) == 0:
            raise serializers.ValidationError("Forcing files must be uploaded")
        return value


class UploadObservationalSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    observational_file = serializers.FileField(required=True)

    def validate_observational_file(self, value):
        request = self.context.get('request')
        files = request.FILES.getlist('observational_file')
        if len(files) != 1:
            raise serializers.ValidationError("Only one observational file should be uploaded.")
        return value


class UploadGeopackageSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    geopackage_file = serializers.FileField(required=True)

    def validate_geopackage_file(self, value):
        request = self.context.get('request')
        files = request.FILES.getlist('geopackage_file')
        if len(files) != 1:
            raise serializers.ValidationError("Only one geopackage file should be uploaded.")
        return value


class SaveGageRequestSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    gage_id = serializers.CharField(required=False, allow_blank=False)
    forcing_source = serializers.CharField(required=False, validators=[forcingSourceValidator])
    observational_source = serializers.CharField(required=False, validators=[observationSourceValidator])


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
    forcing_source_values = ForcingSourceSerializer(many=True)
    observational_source_values = ObservationalSourceSerializer(many=True)
    gages = GagesSerializer(required=True, many=True)
    gage = GageSerializer(required=False)
    geopackage_image_url = serializers.CharField(required=False)
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
    modules = ModuleStaticSerializer(many=True)
    status = serializers.CharField(validators=[statusValidator], required=True)


##################################
# Tuning Tab
##################################
class UploadUserParameterFile(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    user_parameter_file = serializers.FileField(required=True)

    def validate_user_parameter_file(self, value):
        request = self.context.get('request')
        files = request.FILES.getlist('user_parameter_file')
        if len(files) != 1:
            raise serializers.ValidationError("Only one parameter file should be uploaded.")
        return value


class ParameterFileSerializer(BaseSerializer):
    param = serializers.CharField(required=True)
    min = serializers.FloatField(required=True)
    max = serializers.FloatField(required=True)
    init = serializers.FloatField(required=True)
    model = serializers.CharField(required=True)


class UserParameterFileUploadResponse(BaseSerializer):
    message = serializers.CharField(required=True)
    calibration_run_id = serializers.IntegerField(required=True)
    user_parameter_file = serializers.ListField(child=ParameterFileSerializer(), required=True)


# Output variables from Hydrofabric
class ModuleOutputVariablesSerializer(BaseSerializer):
    name = serializers.CharField(required=True, allow_blank=False)
    description = serializers.CharField(required=True, allow_blank=False)


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


class SaveTuningRequestSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    parameters = SaveTuningParametersSerializer(many=True, required=False)
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


class LoadTuningResponseSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    modules = ModuleMetadataStaticSerializer(many=True, required=False)
    time_range = TimeRangeSerializerAllowEmpty(required=True)
    status = serializers.CharField(validators=[statusValidator], required=True)


##################################
# Optimization Tab
##################################


class SaveOptimizationRequestSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    optimization_inputs = OptimizationInputsSerializer(many=True, required=False)
    optimization = serializers.CharField(allow_blank=False, required=False, validators=[optimizationValidator])
    objective_function = serializers.CharField(allow_blank=False, required=False)
    streamflow_threshold = serializers.FloatField(required=False)
    peak_flow_threshold = serializers.FloatField(required=False)
    stop_criteria = serializers.IntegerField(required=False, min_value=2)
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
    metrics = MetricSerializer(many=True)
    optimizations = OptimizationStaticSerializer(many=True)


class ObservationalHydrofabricSerializer(BaseSerializer):
    uri = serializers.CharField(required=True, validators=[s3FileValidator])


class ForcingHydrofabricSerializer(BaseSerializer):
    uri = serializers.CharField(required=True, validators=[s3DirectoryValidator])


class GeopackageHydrofabricSerializer(serializers.Serializer):
    uri = serializers.CharField(required=True, validators=[s3FileValidator])


##################################
# Run Tab
##################################

class IsReadyResponseSerializer(BaseSerializer):
    message = serializers.CharField(required=True)
    errors = serializers.ListField(required=False, child=serializers.CharField(required=True))


class ImportResponseSerializer(BaseSerializer):
    message = serializers.CharField(required=True)
    calibration_run_id = serializers.IntegerField(required=True, allow_null=True)
    errors = serializers.ListField(required=False, child=serializers.CharField(required=True))


##################################
# Import/Export
##################################
# All fields are required, so that the user can see what is missing.
# Any objects will be set to an empty object, {} or []
# Booleans will default to False
# Scalers will be set to None
class ExportResponseSerializer(BaseSerializer):
    metadata = serializers.JSONField(required=False)
    run_after_import = serializers.BooleanField(default=False)
    gage_id = serializers.CharField(required=True, allow_null=True)
    forcing_source = serializers.CharField(required=True, allow_null=True, validators=[forcingSourceValidator])
    forcing_hydrofabric_dir_path = serializers.CharField(required=True, allow_blank=False, allow_null=True)
    forcing_user_uploaded_dir_path = serializers.CharField(required=False, allow_blank=False, allow_null=True)
    observational_source = serializers.CharField(required=True, allow_null=True, validators=[observationSourceValidator])
    observational_hydrofabric_file_path = serializers.CharField(required=True, allow_blank=False, allow_null=True)
    observational_user_uploaded_file_path = serializers.CharField(required=False, allow_blank=False, allow_null=True)
    geopackage_path_from_hydrofabric = serializers.CharField(required=True, allow_blank=False, allow_null=True)
    geopackage_user_uploaded_file_path = serializers.CharField(required=True, allow_blank=False, allow_null=True)
    modules = serializers.ListField(child=serializers.CharField(required=False), default=[])
    formulation_name = serializers.CharField(required=True, allow_null=True, allow_blank=False)
    use_sloth = serializers.BooleanField(default=False)
    sloth_parameters = SlothParameters(many=True, default={})
    automatic_validation = serializers.BooleanField(default=False)
    output_variable_to_calibrate = OutputVariableSerializerAllowEmpty(required=True)
    calibration_times = CalibrationTimeControlsAllowEmpty(required=False)
    validation_times = ValidationTimeControlsAllowEmpty(required=False)
    streamflow_threshold = serializers.FloatField(required=False, allow_null=True)
    peak_flow_threshold = serializers.FloatField(required=False, allow_null=True)
    parameters = SaveTuningParametersSerializer(many=True, required=True)
    objective_function = serializers.CharField(required=True, allow_null=True)
    optimization_inputs = OptimizationInputsSerializer(many=True, default={})
    optimization = serializers.CharField(allow_blank=False, required=True, allow_null=True, validators=[optimizationValidator])
    plot_frequency = serializers.IntegerField(required=True, allow_null=True)
    stop_criteria = serializers.IntegerField(required=True, allow_null=True, min_value=2)


class ImportSerializer(BaseSerializer):
    run_after_import = serializers.BooleanField(required=False, default=False)
    metadata = serializers.JSONField(required=False)
    gage_id = serializers.CharField(required=False, allow_null=True)
    forcing_source = serializers.CharField(required=False, allow_null=True, validators=[forcingSourceValidator])
    forcing_user_dir = serializers.CharField(required=False, allow_null=True, allow_blank=False)
    forcing_hydrofabric_dir_path = serializers.CharField(required=False, allow_null=True, allow_blank=False)
    forcing_user_uploaded_dir_path = serializers.CharField(required=False, allow_null=True, allow_blank=False)
    observational_source = serializers.CharField(required=False, allow_null=True, validators=[observationSourceValidator])
    observational_user_file_path = serializers.CharField(required=False, allow_null=True, allow_blank=False)
    observational_hydrofabric_file_path = serializers.CharField(required=False, allow_null=True, allow_blank=False)
    observational_user_uploaded_file_path = serializers.CharField(required=False, allow_null=True, allow_blank=False)
    geopackage_path_from_hydrofabric = serializers.CharField(required=False, allow_null=True, allow_blank=False)
    geopackage_user_uploaded_file_path = serializers.CharField(required=False, allow_null=True, allow_blank=False)
    modules = serializers.ListField(child=serializers.CharField(required=False), required=False, allow_empty=True)
    sloth_parameters = SlothParameters(required=False, many=True, allow_empty=True)
    formulation_name = serializers.CharField(required=False, allow_null=True, allow_blank=False)
    use_sloth = serializers.BooleanField(required=False, default=False)
    automatic_validation = serializers.BooleanField(required=False, default=False)
    output_variable_to_calibrate = OutputVariableSerializerAllowEmpty(required=False)
    calibration_times = CalibrationTimeControlsAllowEmpty(required=False)
    validation_times = ValidationTimeControlsAllowEmpty(required=False)
    streamflow_threshold = serializers.FloatField(required=False, allow_null=True)
    peak_flow_threshold = serializers.FloatField(required=False, allow_null=True)
    parameters = SaveTuningParametersSerializer(many=True, required=False)
    objective_function = serializers.CharField(required=False, allow_null=True)
    optimization_inputs = OptimizationInputsSerializer(many=True, required=False)
    optimization = serializers.CharField(allow_blank=False, allow_null=True, required=False, validators=[optimizationValidator])

    plot_frequency = serializers.IntegerField(required=False, allow_null=True)
    stop_criteria = serializers.IntegerField(required=False, allow_null=True, min_value=2)


##################################
# Misc
##################################
class ReportIterationSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    optimization = serializers.CharField(allow_blank=False, required=True, validators=[optimizationValidator])
    iteration = serializers.IntegerField(required=True, min_value=0)
    worker_name = serializers.CharField(required=True)


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


# class ValidationExceptionSerializer(BaseSerializer):
#     # validation_error = serializers.DictField(child=ErrorDetailListField(), required=True)
#     validation_error = serializers.JSONField(required=True)


class ErrorResponseSerializer(BaseSerializer):
    response_type = serializers.CharField(required=True, allow_blank=False, allow_null=False)
    message = serializers.CharField(required=True, allow_blank=False, allow_null=False)
    validation_errors = serializers.JSONField(required=False, allow_null=True)

#
#
# class ExceptionResponseSerializer(BaseSerializer):
#     exception = serializers.CharField(required=True)
