from datetimerange import DateTimeRange
from django.core.validators import RegexValidator
from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail
from rest_framework.fields import empty
from rest_framework.settings import api_settings

from calibration.enums import DataTypeEnum, UnitsEnum, LocationEnum, ForcingSourceEnum, ObservationalSourceEnum, DomainEnum, StatusEnum, \
    OptimizationEnum, GeopackageSourceEnum, SlurmStatusEnum


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


def enum_validator(enum_class):
    """
    Should be used for enum class that extend AbstractEnum only
    """

    def validate_enum(value):
        if value not in enum_class.get_names():
            raise serializers.ValidationError(f"This field must be one of {enum_class.get_names()}")

    return validate_enum


def no_space_validator(value):
    if ' ' in value:
        raise serializers.ValidationError("This field must not contain spaces.")


class CalibrationRunSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)


class ValidationRunSerializer(BaseSerializer):
    validation_run_id = serializers.IntegerField(required=True)


class CalibrationOrValidationRunSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=False, allow_null=True)
    validation_run_id = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, data):
        calibration_run_id = data.get('calibration_run_id')
        validation_run_id = data.get('validation_run_id')

        # Ensure that only one of them is specified
        if bool(calibration_run_id) == bool(validation_run_id):  # Both are specified or both are None
            raise serializers.ValidationError(
                "You must specify either 'calibration_run_id' or 'validation_run_id', but not both."
            )

        return data


class CreateValidationRequestSerializer(CalibrationRunSerializer):
    iteration_id = serializers.IntegerField(required=True)


##################################
# Common serializers that need to be defined before usage
##################################
class SlothParameters(BaseSerializer):
    param_name = serializers.CharField(required=True, allow_blank=False)
    param_count = serializers.IntegerField(required=True)
    param_type = serializers.CharField(required=True, validators=[enum_validator(DataTypeEnum)])
    param_units = serializers.CharField(required=True, validators=[enum_validator(UnitsEnum)])
    param_location = serializers.CharField(required=True, validators=[enum_validator(LocationEnum)])
    param_value = serializers.FloatField(required=True)
    maps_to_module = serializers.CharField(required=True, allow_blank=False)
    maps_to_variable_name = serializers.CharField(required=True, allow_blank=False)


class TimeRangeValidatorMixin:
    # noinspection PyMethodMayBeStatic
    def validate_time_range(self, start_time, end_time, field_name, allow_empty=False):
        if allow_empty and (start_time is None or end_time is None):
            return None

        if start_time and end_time:
            time_range = DateTimeRange(start_time, end_time)
            if not time_range.is_valid_timerange():
                raise serializers.ValidationError(f'{time_range} is not a valid time range for {field_name}')
            return time_range

        # If one of the fields is None but allow_empty is not True, raise an error
        raise serializers.ValidationError(f'{field_name} requires both start and end times')


class TimeRangeSerializerAllowEmpty(BaseSerializer):
    start_time = serializers.DateTimeField(required=False)
    end_time = serializers.DateTimeField(required=False)


class CalibrationTimeControls(BaseSerializer, TimeRangeValidatorMixin):
    calibration_start_time = serializers.DateTimeField()
    calibration_end_time = serializers.DateTimeField()
    simulation_start_time = serializers.DateTimeField()
    simulation_end_time = serializers.DateTimeField()

    def __init__(self, *args, allow_empty=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.allow_empty = allow_empty  # Explicitly define allow_empty attribute

        # If allow_empty is True, make the fields not required
        if allow_empty:
            self.fields['calibration_start_time'].required = False
            self.fields['calibration_end_time'].required = False
            self.fields['simulation_start_time'].required = False
            self.fields['simulation_end_time'].required = False
        else:
            self.fields['calibration_start_time'].required = True
            self.fields['calibration_end_time'].required = True
            self.fields['simulation_start_time'].required = True
            self.fields['simulation_end_time'].required = True

    def validate(self, data):
        calibration_range = self.validate_time_range(
            data.get('calibration_start_time'),
            data.get('calibration_end_time'),
            field_name="calibration",
            allow_empty=self.allow_empty
        )
        simulation_range = self.validate_time_range(
            data.get('simulation_start_time'),
            data.get('simulation_end_time'),
            field_name="simulation",
            allow_empty=self.allow_empty
        )

        if calibration_range and simulation_range:
            if calibration_range.start_datetime not in simulation_range or calibration_range.end_datetime not in simulation_range:
                raise serializers.ValidationError({
                    'calibration_range': f'Calibration range {calibration_range} must be contained within simulation range {simulation_range}'
                })

        return data


class ValidationTimeControls(BaseSerializer, TimeRangeValidatorMixin):
    validation_start_time = serializers.DateTimeField()
    validation_end_time = serializers.DateTimeField()
    simulation_start_time = serializers.DateTimeField()
    simulation_end_time = serializers.DateTimeField()

    def __init__(self, *args, allow_empty=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.allow_empty = allow_empty  # Explicitly define allow_empty attribute

        # If allow_empty is True, make the fields not required
        if allow_empty:
            self.fields['validation_start_time'].required = False
            self.fields['validation_end_time'].required = False
            self.fields['simulation_start_time'].required = False
            self.fields['simulation_end_time'].required = False
        else:
            self.fields['validation_start_time'].required = True
            self.fields['validation_end_time'].required = True
            self.fields['simulation_start_time'].required = True
            self.fields['simulation_end_time'].required = True

    def validate(self, data):
        validation_range = self.validate_time_range(
            data.get('validation_start_time'),
            data.get('validation_end_time'),
            field_name="calibration",
            allow_empty=self.allow_empty
        )
        simulation_range = self.validate_time_range(
            data.get('simulation_start_time'),
            data.get('simulation_end_time'),
            field_name="simulation",
            allow_empty=self.allow_empty
        )

        if validation_range and simulation_range:
            if validation_range.start_datetime not in simulation_range or validation_range.end_datetime not in simulation_range:
                raise serializers.ValidationError({
                    'validation_range': f'Validation range {validation_range} must be contained within simulation range {simulation_range}'
                })

        return data


# TODO See if we can eliminate 1 of these after Hydrofabric implementation
# Used for the output from Hydrofabric
class OutputVariableMetadataSerializer(BaseSerializer):
    name = serializers.CharField(required=True, allow_blank=False)
    description = serializers.CharField(required=True, allow_blank=False)


class OutputVariableSerializer(BaseSerializer):
    name = serializers.CharField(allow_blank=False)
    module = serializers.CharField(allow_blank=False)

    def __init__(self, *args, allow_empty=False, **kwargs):
        super().__init__(*args, **kwargs)

        # If allow_empty is True, make the fields not required
        if allow_empty:
            self.fields['name'].required = False
            self.fields['module'].required = False
        else:
            self.fields['name'].required = True
            self.fields['module'].required = True


class SaveTuningParametersSerializer(BaseSerializer):
    name = serializers.CharField(required=True, allow_blank=False)
    minimum = serializers.FloatField(required=True)
    maximum = serializers.FloatField(required=True)
    initial_value = serializers.FloatField(required=True, allow_null=True)
    module = serializers.CharField(required=True, allow_blank=False)

    def validate(self, data):
        if data['minimum'] is not None and data['maximum'] is not None:
            if data['minimum'] > data['maximum']:
                raise serializers.ValidationError(
                    f"Minimum ({data['minimum']}) must be less than maximum ({data['maximum']}) for parameter {data['name']}"
                )
            if data['initial_value'] is not None and not (data['minimum'] <= data['initial_value'] <= data['maximum']):
                raise serializers.ValidationError(
                    f"Value {data['initial_value']} must be between minimum ({data['minimum']:.10f}) and maximum ({data['maximum']:.10f}) for parameter {data['name']}"
                )

        return data

class LoadTuningParametersSerializer(BaseSerializer):
    """
    This serializer is used when loading, so min, max and initial_value are not required
    """
    name = serializers.CharField(required=True, allow_blank=False)
    minimum = serializers.FloatField(required=False, allow_null=True)
    maximum = serializers.FloatField(required=False, allow_null=True)
    initial_value = serializers.FloatField(required=False, allow_null=True)
    data_type = serializers.CharField(required=True, validators=[enum_validator(DataTypeEnum)])
    description = serializers.CharField(required=True, allow_blank=False)
    user_selected_for_tuning = serializers.BooleanField(required=True)
    units = serializers.CharField(required=False, allow_null=True, allow_blank=True)


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
# initial_value, min and max are strings, since Hydrofabric sometimes has some extra crap in there, like units
# We save them in the db as floats, so we'll have to sanitize them
class ModuleParametersSerializer(serializers.Serializer):
    name = serializers.CharField(required=True, allow_blank=False)
    data_type = serializers.CharField(required=True, validators=[enum_validator(DataTypeEnum)])
    description = serializers.CharField(required=True, allow_blank=False)
    minimum = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    maximum = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    initial_value = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    units = serializers.CharField(required=False, allow_null=True, allow_blank=True)


# Used by LoadTuningParameters
class ModuleMetadataStaticSerializer(BaseSerializer):
    name = serializers.CharField(required=True, allow_blank=False)
    parameters = LoadTuningParametersSerializer(required=True, many=True)
    output_variables = OutputVariableMetadataSerializer(required=True, many=True)


##################################
# Landing page
##################################


class CalibrationJobsResponseSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    gage_id = serializers.CharField(required=True, allow_null=True)
    status = serializers.CharField(required=True, validators=[enum_validator(StatusEnum)])
    calibration_start_period = serializers.DateTimeField(required=False, allow_null=True)
    calibration_end_period = serializers.DateTimeField(required=False, allow_null=True)
    formulation_name = serializers.CharField(required=False, allow_null=True, validators=[no_space_validator])
    objective_function = serializers.CharField(required=False, allow_null=False)
    optimization_algorithm = serializers.CharField(required=False, allow_null=False)
    run_date = serializers.DateTimeField(required=True, allow_null=True)
    validation_runs = serializers.IntegerField(required=False)


class GetCalibrationJobsResponseSerializer(BaseSerializer):
    jobs = serializers.ListSerializer(child=CalibrationJobsResponseSerializer(), required=True, allow_empty=True)


class ValidationJobsParameter(BaseSerializer):
    name = serializers.CharField(required=True, allow_null=False, allow_blank=False)
    value = serializers.FloatField(required=True, allow_null=False)


class FooterResponseSerializer(BaseSerializer):
    version = serializers.CharField(required=True)
    contact_email = serializers.CharField(required=True)


def validate_automatic_validation(value):
    if value is not True:
        raise serializers.ValidationError("automatic_validation must always be True.")
    return value


class LoadCalibrationRunResponseSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    run_date = serializers.DateTimeField(required=True, allow_null=True)
    gage = GageSerializer(required=True, allow_null=True)
    forcing_source = serializers.CharField(required=True, allow_null=True, validators=[enum_validator(ForcingSourceEnum)])
    # forcing_hydrofabric_dir_path = serializers.CharField(required=True, allow_blank=False, allow_null=True)
    observational_source = serializers.CharField(required=True, allow_null=True, validators=[enum_validator(ObservationalSourceEnum)])
    # observational_hydrofabric_file_path = serializers.CharField(required=True, allow_blank=False, allow_null=True)
    geopackage_source = serializers.CharField(required=True, allow_null=True, validators=[enum_validator(GeopackageSourceEnum)])
    # geopackage_hydrofabric_file_path = serializers.CharField(required=True, allow_blank=False, allow_null=True)
    geopackage_image_url = serializers.CharField(required=False)
    external_data_status = serializers.JSONField(required=False)
    modules = serializers.ListField(child=serializers.CharField(required=False))
    formulation_name = serializers.CharField(required=True, allow_null=True, allow_blank=False, validators=[no_space_validator])
    parameters_selected = serializers.BooleanField(required=True)
    nwm_warning = serializers.BooleanField(required=True)
    use_sloth = serializers.BooleanField(default=False)
    sloth_parameters = SlothParameters(many=True, default=[])
    automatic_validation = serializers.BooleanField(default=True, validators=[validate_automatic_validation])
    time_range = TimeRangeSerializerAllowEmpty(required=False)
    calibration_times = CalibrationTimeControls(required=False, allow_empty=True)
    validation_times = ValidationTimeControls(required=False, allow_empty=True)
    output_variable_to_calibrate = OutputVariableSerializer(required=True, allow_empty=True)

    objective_function = serializers.CharField(required=True, allow_null=True)
    streamflow_threshold = serializers.FloatField(required=False, allow_null=True)
    peak_flow_threshold = serializers.FloatField(required=False, allow_null=True)
    optimization = serializers.CharField(allow_blank=False, required=True, allow_null=True, validators=[enum_validator(OptimizationEnum)])
    optimization_inputs = OptimizationInputsSerializer(many=True, default=[])
    save_plot_iteration_frequency = serializers.IntegerField(min_value=1, required=True, allow_null=True)
    save_output_iteration = serializers.BooleanField(required=True, allow_null=True)
    stop_criteria = serializers.IntegerField(required=True, allow_null=True, min_value=2)
    status = serializers.CharField(validators=[enum_validator(StatusEnum)], required=True)


class GenericResponseSerializer(BaseSerializer):
    message = serializers.CharField(required=True)
    calibration_run_id = serializers.IntegerField(required=True)
    status = serializers.CharField(validators=[enum_validator(StatusEnum)], required=True)


##################################
# Gage Tab
##################################

class DomainSerializer(BaseSerializer):
    domain = serializers.CharField(required=True, validators=[enum_validator(DomainEnum)])


class GageIdSerializer(BaseSerializer):
    gage_id = serializers.CharField(required=True, allow_blank=False)


class GetCalibrationJobsRequestSerializer(BaseSerializer):
    gage_id = serializers.CharField(required=False, allow_blank=False)
    include_validations = serializers.BooleanField(required=False, default=False)


class GetValidationJobsRequestSerializer(BaseSerializer):
    validation_run_id = serializers.IntegerField(required=True)
    include_validations = serializers.BooleanField(required=False, default=False)


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
    return_geopackage_url = serializers.BooleanField(default=True)

    def validate_geopackage_file(self, value):
        request = self.context.get('request')
        files = request.FILES.getlist('geopackage_file')
        if len(files) != 1:
            raise serializers.ValidationError("Only one geopackage file should be uploaded.")

        return value


class UploadGeopackageResponseSerializer(GenericResponseSerializer):
    geopackage_image_url = serializers.CharField(required=False)


class SaveGageRequestSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    gage_id = serializers.CharField(required=False, allow_blank=False)
    forcing_source = serializers.CharField(required=False, allow_null=True, validators=[enum_validator(ForcingSourceEnum)])
    observational_source = serializers.CharField(required=False, allow_null=True, validators=[enum_validator(ObservationalSourceEnum)])
    geopackage_source = serializers.CharField(required=False, allow_null=True, validators=[enum_validator(GeopackageSourceEnum)])


class SaveGageResponseSerializer(GenericResponseSerializer):
    geopackage_image_url = serializers.CharField(required=False, allow_null=True)
    hydrofabric_errors = serializers.JSONField(required=False)


class DomainResponseSerializer(BaseSerializer):
    name = serializers.CharField(required=True, validators=[enum_validator(DomainEnum)])
    description = serializers.CharField(required=True, allow_blank=False)


class GagesSerializer(BaseSerializer):
    gage_id = serializers.CharField(required=True, allow_blank=False)
    nws_id = serializers.CharField(required=False, allow_null=True, allow_blank=False)
    domain = serializers.CharField(required=True, validators=[enum_validator(DomainEnum)])

    nwm_v3_calibrated = serializers.BooleanField(required=True)


class ForcingSourceSerializer(BaseSerializer):
    name = serializers.CharField(required=True, validators=[enum_validator(ForcingSourceEnum)])
    description = serializers.CharField(required=True)


class ObservationalSourceSerializer(BaseSerializer):
    name = serializers.CharField(required=True, validators=[enum_validator(ObservationalSourceEnum)])
    description = serializers.CharField(required=True)


class GeopackageSourceSerializer(BaseSerializer):
    name = serializers.CharField(required=True, validators=[enum_validator(GeopackageSourceEnum)])
    description = serializers.CharField(required=True)


class LoadGageResponseSerializer(BaseSerializer):
    status = serializers.CharField(required=True, validators=[enum_validator(StatusEnum)])
    calibration_run_id = serializers.IntegerField(required=True)
    forcing_source_values = ForcingSourceSerializer(many=True)
    observational_source_values = ObservationalSourceSerializer(many=True)
    geopackage_source_values = GeopackageSourceSerializer(many=True)
    gages = GagesSerializer(required=True, many=True)
    gage = GageSerializer(required=False)
    geopackage_image_url = serializers.CharField(required=False)
    domain_values = DomainResponseSerializer(many=True)


class CreateCalibrationRunSerializer(BaseSerializer):
    message = serializers.CharField(required=True)
    calibration_run_id = serializers.IntegerField(required=True)


class CreateValidationRunSerializer(BaseSerializer):
    message = serializers.CharField(required=True)
    calibration_run_id = serializers.IntegerField(required=True)
    validation_run_id = serializers.IntegerField(required=True)


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
    # filename = serializers.CharField(required=True, allow_blank=False)


class GetPLotNamesResponseSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    plot_names = PlotListStaticSerializer(many=True)
    status = serializers.CharField(required=True, validators=[enum_validator(StatusEnum)])


class GetPlotRequestSerializer(CalibrationRunSerializer):
    plot_name = serializers.CharField(required=True, allow_null=False)


class GetPlotResponseSerializer(CalibrationRunSerializer):
    plot_name = serializers.CharField(required=True, allow_null=False)
    plot_file_name = serializers.CharField(required=True, allow_null=False)
    plot_url = serializers.CharField(required=True, allow_null=False)


##################################
# Formulation Tab
##################################


class S3UriField(serializers.CharField):
    def __init__(self, validate_directory=False, **kwargs):
        regex = r'^s3://([^/]+)/(.*?([^/]+)/)$' if validate_directory else r'^s3://([^/]+)/(.*?([^/]+))$'
        self.default_validators = [RegexValidator(regex, 'This field must be a valid S3 URI')]
        super().__init__(**kwargs)


class S3DirectoryValidator(BaseSerializer):
    uri = S3UriField(validate_directory=True)


class S3FileValidator(BaseSerializer):
    uri = S3UriField()


class SaveFormulationRequestSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    formulation_name = serializers.CharField(required=False, allow_blank=False, validators=[no_space_validator])
    modules = serializers.ListField(child=serializers.CharField(required=True), required=False)
    use_sloth = serializers.BooleanField(required=True)
    sloth_parameters = SlothParameters(required=False, many=True)


class SaveFormulationResponseSerializer(GenericResponseSerializer):
    nwm_warning = serializers.BooleanField(required=True)


class ModuleStaticSerializer(BaseSerializer):
    name = serializers.CharField(required=True, allow_blank=False)
    groups = serializers.ListField(child=serializers.CharField(required=True))
    is_active = serializers.BooleanField(required=True)


class LoadFormulationResponseSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    modules = ModuleStaticSerializer(many=True)
    module_groups = serializers.ListSerializer(child=serializers.CharField(required=True), required=True, allow_null=False, allow_empty=False)
    status = serializers.CharField(required=True, validators=[enum_validator(StatusEnum)])
    hydrofabric_errors = serializers.JSONField(required=False)


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
    variable = serializers.CharField(required=True, allow_blank=False)
    # TODO This is required, cannot be null
    description = serializers.CharField(required=True, allow_blank=False, allow_null=True)


# Module object from Hydrofabric containing module parameters and output variables
class ModuleMetadataHydrofabricSerializer(BaseSerializer):
    module_name = serializers.CharField(required=True, allow_blank=False)
    calibrate_parameters = ModuleParametersSerializer(many=True)
    output_variables = ModuleOutputVariablesSerializer(many=True)
    parameter_file = S3FileValidator(required=True)


# List of module objects from Hydrofabric containing module parameters and output variables
class ModuleDataHydrofabricListSerializer(BaseSerializer):
    modules = ModuleMetadataHydrofabricSerializer(many=True, min_length=1, required=True)


class SaveTuningRequestSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    parameters = SaveTuningParametersSerializer(many=True, required=False)
    calibration_times = CalibrationTimeControls(required=False, allow_empty=False)
    validation_times = ValidationTimeControls(required=False, allow_empty=False)
    automatic_validation = serializers.BooleanField(default=True, validators=[validate_automatic_validation])
    output_variable_to_calibrate = OutputVariableSerializer(required=False, allow_empty=False)

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
    status = serializers.CharField(required=True, validators=[enum_validator(StatusEnum)])
    hydrofabric_errors = serializers.JSONField(required=False)


##################################
# Optimization Tab
##################################


class SaveOptimizationRequestSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    optimization_inputs = OptimizationInputsSerializer(many=True, required=False)
    optimization = serializers.CharField(allow_blank=False, required=False, validators=[enum_validator(OptimizationEnum)])
    objective_function = serializers.CharField(allow_blank=False, required=False)
    streamflow_threshold = serializers.FloatField(required=False)
    peak_flow_threshold = serializers.FloatField(required=False)
    stop_criteria = serializers.IntegerField(required=False, min_value=2)
    save_plot_iteration_frequency = serializers.IntegerField(min_value=1, required=False)
    save_output_iteration = serializers.BooleanField(required=False)


class OptimizationInputStaticSerializer(serializers.Serializer):
    name = serializers.CharField(required=True)
    description = serializers.CharField(required=True)
    data_type = serializers.CharField(required=True, validators=[enum_validator(DataTypeEnum)])
    default_value = serializers.FloatField(required=True)
    min = serializers.FloatField(required=False, allow_null=True)
    max = serializers.FloatField(required=False, allow_null=True)
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
    status = serializers.CharField(required=True, validators=[enum_validator(StatusEnum)])
    metrics = MetricSerializer(many=True)
    optimizations = OptimizationStaticSerializer(many=True)


##################################
# Run Tab
##################################
class GetStatusValidationsResponseSerializer(ValidationRunSerializer):
    status = serializers.CharField(validators=[enum_validator(StatusEnum)], required=True)
    validation_type = serializers.CharField(required=True)


class IsReadyResponseSerializer(GenericResponseSerializer):
    errors = serializers.ListField(required=False, child=serializers.CharField(required=True))
    validations = GetStatusValidationsResponseSerializer(many=True)


class ImportResponseSerializer(GenericResponseSerializer):
    errors = serializers.ListField(required=False, child=serializers.CharField(required=True))
    messages = serializers.ListField(required=False, child=serializers.CharField(required=True))


class SubmitCalibrationJobResponseSerializer(GenericResponseSerializer):
    run_date = serializers.DateTimeField(required=True, allow_null=False)


class SubmitValidationJobResponseSerializer(BaseSerializer):
    message = serializers.CharField(required=True)
    validation_run_id = serializers.IntegerField(required=True)
    status = serializers.CharField(validators=[enum_validator(StatusEnum)], required=True)
    run_date = serializers.DateTimeField(required=True, allow_null=False)


class GetIterationsResponseSerializer(GenericResponseSerializer):
    iterations = serializers.IntegerField(required=True)


class CalibrationJobSlurmCallbackRequestSerializer(CalibrationRunSerializer):
    job_status = serializers.CharField(required=True, validators=[SlurmStatusEnum])


class ValidationJobSlurmCallbackRequestSerializer(ValidationRunSerializer):
    job_status = serializers.CharField(required=True, validators=[SlurmStatusEnum])


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
    forcing_source = serializers.CharField(required=True, allow_null=True, validators=[enum_validator(ForcingSourceEnum)])
    forcing_hydrofabric_dir_path = serializers.CharField(required=True, allow_blank=False, allow_null=True)
    forcing_user_uploaded_dir_path = serializers.CharField(required=False, allow_blank=False, allow_null=True)
    observational_source = serializers.CharField(required=True, allow_null=True, validators=[enum_validator(ObservationalSourceEnum)])
    observational_hydrofabric_file_path = serializers.CharField(required=True, allow_blank=False, allow_null=True)
    observational_user_uploaded_file_path = serializers.CharField(required=False, allow_blank=False, allow_null=True)
    geopackage_source = serializers.CharField(required=True, allow_null=True, validators=[enum_validator(GeopackageSourceEnum)])
    geopackage_hydrofabric_file_path = serializers.CharField(required=True, allow_blank=False, allow_null=True)
    geopackage_user_uploaded_file_path = serializers.CharField(required=True, allow_blank=False, allow_null=True)
    modules = serializers.ListField(child=serializers.CharField(required=False), default=[])
    formulation_name = serializers.CharField(required=True, allow_null=True, allow_blank=False, validators=[no_space_validator])
    use_sloth = serializers.BooleanField(default=False)
    sloth_parameters = SlothParameters(many=True, default={})
    automatic_validation = serializers.BooleanField(default=True, validators=[validate_automatic_validation])
    output_variable_to_calibrate = OutputVariableSerializer(required=True, allow_empty=True)
    calibration_times = CalibrationTimeControls(required=False, allow_empty=True)
    validation_times = ValidationTimeControls(required=False, allow_empty=True)
    streamflow_threshold = serializers.FloatField(required=False, allow_null=True)
    peak_flow_threshold = serializers.FloatField(required=False, allow_null=True)
    parameters = SaveTuningParametersSerializer(many=True, required=True)
    objective_function = serializers.CharField(required=True, allow_null=True)
    optimization_inputs = OptimizationInputsSerializer(many=True, default={})
    optimization = serializers.CharField(allow_blank=False, required=True, allow_null=True, validators=[enum_validator(OptimizationEnum)])
    save_plot_iteration_frequency = serializers.IntegerField(min_value=1, required=True, allow_null=True)
    save_output_iteration = serializers.BooleanField(required=True, allow_null=True)
    stop_criteria = serializers.IntegerField(required=True, allow_null=True, min_value=2)


class ImportSerializer(BaseSerializer):
    run_after_import = serializers.BooleanField(required=False, default=False)
    metadata = serializers.JSONField(required=False)
    gage_id = serializers.CharField(required=False, allow_null=True)
    forcing_source = serializers.CharField(required=False, allow_null=True, validators=[enum_validator(ForcingSourceEnum)])
    forcing_user_dir = serializers.CharField(required=False, allow_null=True, allow_blank=False)
    forcing_hydrofabric_dir_path = serializers.CharField(required=False, allow_null=True, allow_blank=False)
    forcing_user_uploaded_dir_path = serializers.CharField(required=False, allow_null=True, allow_blank=False)
    observational_source = serializers.CharField(required=False, allow_null=True, validators=[enum_validator(ObservationalSourceEnum)])
    observational_user_file_path = serializers.CharField(required=False, allow_null=True, allow_blank=False)
    observational_hydrofabric_file_path = serializers.CharField(required=False, allow_null=True, allow_blank=False)
    observational_user_uploaded_file_path = serializers.CharField(required=False, allow_null=True, allow_blank=False)
    geopackage_source = serializers.CharField(required=False, allow_null=True, validators=[enum_validator(GeopackageSourceEnum)])
    geopackage_hydrofabric_file_path = serializers.CharField(required=False, allow_null=True, allow_blank=False)
    geopackage_user_uploaded_file_path = serializers.CharField(required=False, allow_null=True, allow_blank=False)
    modules = serializers.ListField(child=serializers.CharField(required=False), required=False, allow_empty=True)
    sloth_parameters = SlothParameters(required=False, many=True, allow_empty=True)
    formulation_name = serializers.CharField(required=False, allow_null=True, allow_blank=False, validators=[no_space_validator])
    use_sloth = serializers.BooleanField(required=False, default=False)
    automatic_validation = serializers.BooleanField(default=True, validators=[validate_automatic_validation])
    output_variable_to_calibrate = OutputVariableSerializer(required=False, allow_empty=True)
    calibration_times = CalibrationTimeControls(required=False, allow_empty=True)
    validation_times = ValidationTimeControls(required=False, allow_empty=True)
    streamflow_threshold = serializers.FloatField(required=False, allow_null=True)
    peak_flow_threshold = serializers.FloatField(required=False, allow_null=True)
    parameters = SaveTuningParametersSerializer(many=True, required=False)
    objective_function = serializers.CharField(required=False, allow_null=True)
    optimization_inputs = OptimizationInputsSerializer(many=True, required=False)
    optimization = serializers.CharField(allow_blank=False, required=False, allow_null=True, validators=[enum_validator(OptimizationEnum)])
    save_plot_iteration_frequency = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    save_output_iteration = serializers.BooleanField(required=False, allow_null=False, default=False)
    stop_criteria = serializers.IntegerField(required=False, allow_null=True, min_value=2)


##################################
# Misc
##################################
class ReportIterationSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    iteration = serializers.IntegerField(required=True, min_value=0)
    worker_name = serializers.CharField(required=True)
    first_iteration_for_worker = serializers.BooleanField(required=True)


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


class ErrorResponseSerializer(BaseSerializer):
    response_type = serializers.CharField(required=True, allow_blank=False, allow_null=False)
    message = serializers.CharField(required=True, allow_blank=False, allow_null=False)
    validation_errors = serializers.JSONField(required=False, allow_null=True)


##################################
# Evaluation
##################################
class ParameterDataByIteration(BaseSerializer):
    parameter_name = serializers.CharField(required=True, allow_blank=False, allow_null=False)
    parameter_value = serializers.FloatField(required=True, allow_null=False)


class MetricDataByIteration(BaseSerializer):
    metric_name = serializers.CharField(required=True, allow_blank=False, allow_null=False)
    # Need to allow Null for NaN
    metric_value = serializers.FloatField(required=True, allow_null=True)


class CalibrationDataByIteration(BaseSerializer):
    iteration_num = serializers.IntegerField(required=True, allow_null=False, min_value=0)
    iteration_id = serializers.IntegerField(required=True, allow_null=False)
    worker_name = serializers.CharField(required=True, allow_null=False, allow_blank=False)
    best_params = serializers.BooleanField(required=True, allow_null=False)
    calibration_output_variable_value = serializers.FloatField(required=True, allow_null=False)
    parameters = ParameterDataByIteration(many=True, required=True)
    metrics = MetricDataByIteration(many=True, required=True)


class GetCalibrationDataByIterationResponseSerializer(GenericMessageResponseSerializer):
    iteration_data = CalibrationDataByIteration(many=True, required=True)
    nwm_retrospective_data = MetricDataByIteration(many=True, required=True)


class ValidationJobsResponseSerializer(BaseSerializer):
    validation_run_id = serializers.IntegerField(required=True)
    run_date = serializers.DateTimeField(required=True, allow_null=True)
    parameters = serializers.ListSerializer(child=ValidationJobsParameter(), required=True, allow_empty=False)
    best = serializers.BooleanField(required=True)


class GetValidationJobsResponseSerializer(BaseSerializer):
    validation_jobs = serializers.ListSerializer(child=ValidationJobsResponseSerializer(), required=True, allow_empty=True)


##################################
# Slurm
##################################
class SlurmSubmitJobResponse(BaseSerializer):
    slurm_job_id = serializers.IntegerField(required=False, allow_null=False)
    ngen_cal_commit_hash = serializers.CharField(required=True, allow_null=False, allow_blank=False)
    ngen_commit_hash = serializers.CharField(required=True, allow_null=False, allow_blank=False)
