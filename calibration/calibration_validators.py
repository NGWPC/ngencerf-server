from rest_framework import serializers


class SaveGageValidator(serializers.Serializer):
    calibration_run_id = serializers.IntegerField(required=False)
    gage_id = serializers.CharField(min_length=1, required=True)
    forcing_source = serializers.CharField(min_length=1, required=True)
    forcing_path = serializers.CharField(min_length=1, required=True)


class SaveFormulationValidator(serializers.Serializer):
    calibration_run_id = serializers.IntegerField(required=False)
    formulation_name = serializers.CharField(min_length=1, required=True)
    modules = serializers.ListField(child=serializers.CharField(min_length=2, required=True), min_length=2)
    # Sloth parameters
