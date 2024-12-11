from django.core.validators import RegexValidator
from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail
from rest_framework.fields import empty
from rest_framework.settings import api_settings

from calibration.enums import DataTypeEnum, UnitsEnum, LocationEnum, ForcingSourceEnum, ObservationalSourceEnum, DomainEnum, StatusEnum, \
    OptimizationEnum, GeopackageSourceEnum, SlurmStatusEnum, JobGenesis, PlotDefinitionsEnum, ForecastCycleEnum


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
    Validates if the value is a valid name or alias of the enum class, case-insensitively.
    """

    def validate_enum(value):
        # Convert input value to lowercase for case-insensitive comparison
        original_value = value  # Store original value for error message
        value = value.lower()

        # Retrieve valid names, converting each to lowercase for case-insensitive comparison
        if hasattr(enum_class, 'get_all_valid_names'):
            # Enum with get_all_valid_names() method (typically from AbstractEnum)
            valid_names = [name.lower() for name in enum_class.get_all_valid_names()]
        else:
            # Standard enum without aliases, using get_names() if available
            valid_names = [name.lower() for name in enum_class.get_names()] if hasattr(enum_class, 'get_names') else []

        if value not in valid_names:
            raise serializers.ValidationError(f"Invalid value '{original_value}'. This field must be one of {valid_names}.")

    return validate_enum


def no_space_validator(value):
    if ' ' in value:
        raise serializers.ValidationError("This field must not contain spaces.")


def greater_than_zero(value):
    if value <= 0:
        raise serializers.ValidationError("This field must be greater than 0.")


class EmptySerializer(BaseSerializer):
    pass


class GenericMessageResponseSerializer(BaseSerializer):
    message = serializers.CharField(required=True)


class GenericMessageAndStatusResponseSerializer(GenericMessageResponseSerializer):
    message = serializers.CharField(required=True)
    status = serializers.CharField(validators=[enum_validator(StatusEnum)], required=True)


class GenericResponseSerializer(GenericMessageAndStatusResponseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)


class GenericResponseSerializerWithValidation(GenericResponseSerializer):
    validation_run_id = serializers.IntegerField(required=False)


class CalibrationRunSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)


class ForecastRunSerializer(BaseSerializer):
    forecast_run_id = serializers.IntegerField(required=True)


class DeleteForecastRunResponseSerializer(GenericMessageResponseSerializer):
    forecast_run_id = serializers.IntegerField(required=True)


class GetStatusRequestSerializer(CalibrationRunSerializer):
    include_performance_metrics = serializers.BooleanField(required=False, default=False)


class ValidationRunSerializer(BaseSerializer):
    validation_run_id = serializers.IntegerField(required=True)


# TDOO Do we still need this after we've fully implemented Forecast
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


class CalibrationOrValidationOrForecastRunSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=False, allow_null=False)
    validation_run_id = serializers.IntegerField(required=False, allow_null=False)
    forecast_run_id = serializers.IntegerField(required=False, allow_null=False)

    def validate(self, data):
        """
        Ensure that only one of calibration_run_id, validation_run_id, or forecast_run_id is specified.
        """
        calibration_run_id = data.get('calibration_run_id')
        validation_run_id = data.get('validation_run_id')
        forecast_run_id = data.get('forecast_run_id')

        # Collect the IDs that are specified (non-null and non-zero values)
        specified_ids = [
            id_value
            for id_value in [calibration_run_id, validation_run_id, forecast_run_id]
            if id_value is not None
        ]

        # Check that exactly one ID is specified
        if len(specified_ids) != 1:
            raise serializers.ValidationError(
                "You must specify exactly one of 'calibration_run_id', 'validation_run_id', or 'forecast_run_id'."
            )

        return data


class CancelJobResponseSerializer(GenericMessageAndStatusResponseSerializer, CalibrationOrValidationOrForecastRunSerializer):
    def validate(self, data):
        # Call the parent validate method to include its logic
        return super().validate(data)


class CreateValidationRequestSerializer(CalibrationRunSerializer):
    iteration_id = serializers.IntegerField(required=True)


class CreateForecastRequestSerializer(CalibrationRunSerializer):
    cycle_name = serializers.CharField(required=True, validators=[enum_validator(ForecastCycleEnum)])


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


class TimeRangeSerializerAllowEmpty(BaseSerializer):
    start_time = serializers.DateTimeField(required=False)
    end_time = serializers.DateTimeField(required=False)


class CalibrationTimeControls(BaseSerializer):
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


class ValidationTimeControls(BaseSerializer):
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
    minimum = serializers.FloatField(required=True, allow_null=False)
    maximum = serializers.FloatField(required=True, allow_null=False)
    initial_value = serializers.FloatField(required=True, allow_null=False)
    module = serializers.CharField(required=True, allow_blank=False)

    def __init__(self, *args, allow_empty=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.allow_empty = allow_empty

        # Adjust field requirements based on allow_empty
        if self.allow_empty:
            for field in ['minimum', 'maximum', 'initial_value']:
                self.fields[field].required, self.fields[field].allow_null = False, True

    def validate(self, data):
        # Only validate ranges if minimum, maximum, and initial_value are provided
        min_val = data.get('minimum')
        max_val = data.get('maximum')
        initial = data.get('initial_value')

        if min_val is not None and max_val is not None:
            if min_val > max_val:
                raise serializers.ValidationError(
                    f"Minimum ({min_val}) must be less than maximum ({max_val}) for parameter {data['name']}"
                )
            if initial is not None and not (min_val <= initial <= max_val):
                raise serializers.ValidationError(
                    f"Value {initial} must be between minimum ({min_val:.10f}) and maximum ({max_val:.10f}) for parameter {data['name']}"
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
    job_genesis = serializers.CharField(required=True, validators=[enum_validator(JobGenesis)])
    created_at = serializers.DateTimeField(required=True)
    status = serializers.CharField(required=True, validators=[enum_validator(StatusEnum)])
    calibration_start_period = serializers.DateTimeField(required=False, allow_null=True)
    calibration_end_period = serializers.DateTimeField(required=False, allow_null=True)
    formulation_name = serializers.CharField(required=False, allow_null=True, validators=[no_space_validator])
    submit_date = serializers.DateTimeField(required=True, allow_null=True)
    objective_function = serializers.CharField(required=False, allow_null=True)
    optimization_algorithm = serializers.CharField(required=False, allow_null=True)


class CalibrationJobsForValidationResponseSerializer(CalibrationJobsResponseSerializer):
    validation_runs = serializers.IntegerField(required=False)
    validation_run_ids = serializers.ListSerializer(child=serializers.IntegerField())


class GetCalibrationJobsResponseSerializer(BaseSerializer):
    jobs = serializers.ListSerializer(child=CalibrationJobsResponseSerializer(), required=True, allow_empty=True)


class GetCalibrationJobsForEvaluationResponseSerializer(BaseSerializer):
    jobs = serializers.ListSerializer(child=CalibrationJobsForValidationResponseSerializer(), required=True, allow_empty=True)


class ValidationJobsParameter(BaseSerializer):
    name = serializers.CharField(required=True, allow_null=False, allow_blank=False)
    value = serializers.FloatField(required=True, allow_null=False)


class FooterResponseSerializer(BaseSerializer):
    version = serializers.CharField(required=True)
    date = serializers.CharField(required=True)
    contact_email = serializers.CharField(required=True)
    commit_hash = serializers.CharField(required=True)
    ngenCerf_version = serializers.CharField(required=True)
    ngenCerf_date = serializers.CharField(required=True)


def validate_automatic_validation(value):
    if value is not True:
        raise serializers.ValidationError("automatic_validation must always be True.")
    return value


class LoadCalibrationRunResponseSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    submit_date = serializers.DateTimeField(required=True, allow_null=True)
    gage = GageSerializer(required=True, allow_null=True)
    forcing_source = serializers.CharField(required=True, allow_null=True, validators=[enum_validator(ForcingSourceEnum)])
    observational_source = serializers.CharField(required=True, allow_null=True, validators=[enum_validator(ObservationalSourceEnum)])
    geopackage_source = serializers.CharField(required=True, allow_null=True, validators=[enum_validator(GeopackageSourceEnum)])
    geopackage_image_url = serializers.CharField(required=False)
    external_data_status = serializers.JSONField(required=False)
    modules = serializers.ListField(child=serializers.CharField(required=False))
    formulation_name = serializers.CharField(required=True, allow_null=True, allow_blank=False, validators=[no_space_validator])
    formulation_warning = serializers.JSONField(required=False)
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
    streamflow_threshold = serializers.FloatField(required=False, allow_null=True, validators=[greater_than_zero])
    peak_flow_threshold = serializers.FloatField(required=False, allow_null=True, validators=[greater_than_zero])
    optimization = serializers.CharField(allow_blank=False, required=True, allow_null=True, validators=[enum_validator(OptimizationEnum)])
    optimization_inputs = OptimizationInputsSerializer(many=True, default=[])
    save_plot_iteration_frequency = serializers.IntegerField(min_value=1, required=True, allow_null=True)
    save_output_iteration = serializers.BooleanField(required=True, allow_null=True)
    stop_criteria = serializers.IntegerField(required=True, allow_null=True, min_value=2)
    status = serializers.CharField(validators=[enum_validator(StatusEnum)], required=True)


##################################
# Gage Tab
##################################

class DomainSerializer(BaseSerializer):
    domain = serializers.CharField(required=True, validators=[enum_validator(DomainEnum)])


class GageIdSerializer(BaseSerializer):
    gage_id = serializers.CharField(required=True, allow_blank=False)


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
    eds_errors = serializers.JSONField(required=False)


class DomainResponseSerializer(BaseSerializer):
    name = serializers.CharField(required=True, validators=[enum_validator(DomainEnum)])
    description = serializers.CharField(required=True, allow_blank=False)


class GagesSerializer(BaseSerializer):
    gage_id = serializers.CharField(required=True, allow_blank=False)
    nws_id = serializers.CharField(required=False, allow_null=True, allow_blank=False)
    domain = serializers.CharField(required=True, validators=[enum_validator(DomainEnum)])
    nwm_v3_calibration = serializers.BooleanField(required=True)


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


class CreateCalibrationRunResponseSerializer(GenericMessageResponseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)


class CreateAndRunValidationResponseSerializer(GenericResponseSerializer):
    validation_run_id = serializers.IntegerField(required=True)
    submit_date = serializers.DateTimeField(required=True, allow_null=False)


class CreateAndRunForecastResponseSerializer(GenericResponseSerializer):
    forecast_run_id = serializers.IntegerField(required=True)
    submit_date = serializers.DateTimeField(required=True, allow_null=False)


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


class GetPLotNamesResponseSerializer(CalibrationOrValidationOrForecastRunSerializer):
    plot_names = PlotListStaticSerializer(many=True)
    status = serializers.CharField(required=True, validators=[enum_validator(StatusEnum)])


class GetPlotRequestSerializer(CalibrationOrValidationOrForecastRunSerializer):
    plot_name = serializers.CharField(required=True, allow_null=False, validators=[enum_validator(PlotDefinitionsEnum)])
    include_data = serializers.BooleanField(required=False, default=False)
    force_include_plot = serializers.BooleanField(required=False, default=False)
    start = serializers.IntegerField(required=False, default=0, min_value=0)
    limit = serializers.IntegerField(required=False, default=100, min_value=1)


class PaginationMetadataSerializer(BaseSerializer):
    start = serializers.IntegerField(required=True)
    limit = serializers.IntegerField(required=True)
    count = serializers.IntegerField(required=True)


class GetPlotResponseSerializer(CalibrationRunSerializer):
    validation_run_id = serializers.IntegerField(required=False)
    forecast_run_id = serializers.IntegerField(required=False)
    plot_name = serializers.CharField(required=True, allow_null=False)
    plot_file_path = serializers.CharField(required=False, allow_null=False)
    plot_url = serializers.CharField(required=False, allow_null=False)
    plot_data = serializers.JSONField(required=False)
    pagination_metadata = PaginationMetadataSerializer(required=False)


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
    formulation_warning = serializers.JSONField(required=False)
    eds_errors = serializers.JSONField(required=False)


class ModuleStaticSerializer(BaseSerializer):
    name = serializers.CharField(required=True, allow_blank=False)
    groups = serializers.ListField(child=serializers.CharField(required=True))
    is_active = serializers.BooleanField(required=True)


class LoadFormulationResponseSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    modules = ModuleStaticSerializer(many=True)
    module_groups = serializers.ListSerializer(child=serializers.CharField(required=True), required=True, allow_null=False, allow_empty=False)
    status = serializers.CharField(required=True, validators=[enum_validator(StatusEnum)])


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


class LoadTuningResponseSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    modules = ModuleMetadataStaticSerializer(many=True, required=False)
    time_range = TimeRangeSerializerAllowEmpty(required=True)
    status = serializers.CharField(required=True, validators=[enum_validator(StatusEnum)])


##################################
# Optimization Tab
##################################


class SaveOptimizationRequestSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    optimization_inputs = OptimizationInputsSerializer(many=True, required=False)
    optimization = serializers.CharField(allow_blank=False, required=False, validators=[enum_validator(OptimizationEnum)])
    objective_function = serializers.CharField(allow_blank=False, required=False)
    streamflow_threshold = serializers.FloatField(required=False, validators=[greater_than_zero])
    peak_flow_threshold = serializers.FloatField(required=False, validators=[greater_than_zero])
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

class PerformanceMetricsSerializer(BaseSerializer):
    elapsed_time = serializers.DurationField(required=True, allow_null=True)
    num_cpus = serializers.IntegerField(required=True, allow_null=True)
    cpu_time = serializers.DurationField(required=True, allow_null=True)
    max_rss = serializers.CharField(required=True, allow_null=True)
    max_disk_read = serializers.CharField(required=True, allow_null=True)
    max_disk_write = serializers.CharField(required=True, allow_null=True)
    reserved_time = serializers.DurationField(required=False, allow_null=True)
    io_throughput = serializers.CharField(required=False, allow_null=True)


class CommonStatusFieldsMixin(serializers.Serializer):
    status = serializers.CharField(validators=[enum_validator(StatusEnum)], required=True)
    submit_date = serializers.DateTimeField(required=False, allow_null=True)
    run_start = serializers.DateTimeField(required=False, allow_null=True)
    run_end = serializers.DateTimeField(required=False, allow_null=True)
    elapsed_time = serializers.DurationField(required=False, allow_null=True)
    performance_metrics = PerformanceMetricsSerializer(required=False)


class GetStatusValidationsResponseSerializer(CommonStatusFieldsMixin, ValidationRunSerializer):
    validation_type = serializers.CharField(required=True)
    iteration_num = serializers.IntegerField(allow_null=True)


class GetStatusForecastsResponseSerializer(CommonStatusFieldsMixin, ForecastRunSerializer):
    pass


class GetStatusResponseSerializer(GenericResponseSerializer):
    status = serializers.CharField(validators=[enum_validator(StatusEnum)], required=True)
    errors = serializers.ListField(required=False, child=serializers.CharField(required=True))
    validations = GetStatusValidationsResponseSerializer(many=True)
    forecasts = GetStatusForecastsResponseSerializer(many=True)
    submit_date = serializers.DateTimeField(required=False, allow_null=True)
    run_start = serializers.DateTimeField(required=False, allow_null=True)
    run_end = serializers.DateTimeField(required=False, allow_null=True)
    elapsed_time = serializers.DurationField(required=False, allow_null=True)
    performance_metrics = PerformanceMetricsSerializer(required=False)


class ImportResponseSerializer(GenericResponseSerializer):
    errors = serializers.ListField(required=False, child=serializers.CharField(required=True))
    messages = serializers.JSONField(required=False)


class SubmitCalibrationJobResponseSerializer(GenericResponseSerializer):
    submit_date = serializers.DateTimeField(required=True, allow_null=False)


class GetIterationsResponseSerializer(GenericResponseSerializer):
    iteration = serializers.IntegerField(required=True, allow_null=True)


class CalibrationJobSlurmCallbackRequestSerializer(CalibrationRunSerializer):
    job_status = serializers.CharField(required=True, validators=[SlurmStatusEnum])


class ValidationJobSlurmCallbackRequestSerializer(ValidationRunSerializer):
    job_status = serializers.CharField(required=True, validators=[SlurmStatusEnum])


class GetJobDirResponseSerializer(GenericResponseSerializer):
    data_dir = serializers.CharField(required=True)


##################################
# Forecast Tab
##################################
class ForecastCycleSerializer(BaseSerializer):
    name = serializers.CharField(required=True, validators=[enum_validator(ForecastCycleEnum)])
    data_sources = serializers.CharField(required=False, allow_null=True)
    time_range = serializers.CharField(required=False, allow_null=True)
    is_active = serializers.BooleanField(required=True)


class LoadForecastTabResponseSerializer(BaseSerializer):
    forecast_cycle_values = ForecastCycleSerializer(many=True)


class ForecastJobsResponseSerializer(BaseSerializer):
    calibration_run_id = serializers.IntegerField(required=True)
    forecast_run_id = serializers.IntegerField(required=True)
    cycle = serializers.CharField(required=True)
    gage_id = serializers.CharField(required=True)
    status = serializers.CharField(required=True, validators=[enum_validator(StatusEnum)])
    submit_date = serializers.DateTimeField(required=True)


class GetForecastJobsResponseSerializer(BaseSerializer):
    forecast_jobs = serializers.ListSerializer(child=ForecastJobsResponseSerializer(), required=True, allow_empty=True)


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
    streamflow_threshold = serializers.FloatField(required=False, allow_null=True, validators=[greater_than_zero])
    peak_flow_threshold = serializers.FloatField(required=False, allow_null=True, validators=[greater_than_zero])
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
    streamflow_threshold = serializers.FloatField(required=False, allow_null=True, validators=[greater_than_zero])
    peak_flow_threshold = serializers.FloatField(required=False, allow_null=True, validators=[greater_than_zero])
    parameters = serializers.ListSerializer(child=SaveTuningParametersSerializer(allow_empty=True), required=False)
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
    validation_run_id = serializers.IntegerField(required=False)
    worker_name = serializers.CharField(required=True, allow_null=False, allow_blank=False)
    best_params = serializers.BooleanField(required=True, allow_null=False)
    objective_function_value = serializers.FloatField(required=True, allow_null=False)
    parameters = ParameterDataByIteration(many=True, required=True)
    metrics = MetricDataByIteration(many=True, required=True)


class RetrospectiveData(BaseSerializer):
    name = serializers.CharField(required=True)
    data = MetricDataByIteration(many=True, required=True)


class GetCalibrationDataByIterationResponseSerializer(GenericMessageResponseSerializer):
    objective_function_metric = serializers.CharField(required=True)
    iteration_data = CalibrationDataByIteration(many=True, required=True)
    retrospective_data = RetrospectiveData(many=True, required=True)


class ValidationJobsResponseSerializer(BaseSerializer):
    validation_run_id = serializers.IntegerField(required=True)
    submit_date = serializers.DateTimeField(required=True, allow_null=True)
    validation_type = serializers.CharField(required=True)
    iteration_num = serializers.IntegerField(required=True)
    status = serializers.CharField(required=True, validators=[enum_validator(StatusEnum)])
    parameters = serializers.ListSerializer(child=ValidationJobsParameter(), required=True, allow_empty=False)
    best = serializers.BooleanField(required=True)


class GetValidationJobsResponseSerializer(BaseSerializer):
    validation_jobs = serializers.ListSerializer(child=ValidationJobsResponseSerializer(), required=True, allow_empty=True)


class GetLogsValidations(BaseSerializer):
    validation_run_id = serializers.IntegerField(required=True)
    status = serializers.CharField(required=True, validators=[enum_validator(StatusEnum)])
    validation_type = serializers.CharField(required=True)
    logs = serializers.ListField(child=serializers.DictField(child=serializers.ListField(child=serializers.CharField(allow_blank=True))), required=True, allow_empty=True)


class GetLogsResponseSerializer(GenericResponseSerializer):
    validations = GetLogsValidations(many=True, required=True)
    logs = serializers.ListField(child=serializers.DictField(child=serializers.ListField(child=serializers.CharField(allow_blank=True))), required=False, allow_empty=True)


##################################
# Slurm
##################################
class SlurmSubmitJobResponse(BaseSerializer):
    slurm_job_id = serializers.IntegerField(required=False, allow_null=False)
    ngen_cal_commit_hash = serializers.CharField(required=True, allow_null=False, allow_blank=False)
    ngen_commit_hash = serializers.CharField(required=True, allow_null=False, allow_blank=False)
