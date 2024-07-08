from rest_framework import serializers


class SaveTab1Serializer(serializers.Serializer):
    calibration_run_id = serializers.IntegerField(required=False)
    gage_id = serializers.CharField(min_length=1, required=True),
    forcing_source = serializers.CharField(min_length=1, required=True)
    forcing_path = serializers.CharField(min_length=1, required=True)
