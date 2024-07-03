from django.db import models

from calibration.models.base_model import BaseModel


class CalibrationSlothParam(BaseModel):
    calibration_run = models.ForeignKey('CalibrationRun', null=True, on_delete=models.SET_NULL)
    param_name = models.TextField()
    param_count = models.IntegerField()
    param_type = models.TextField()
    param_units = models.TextField()
    param_location = models.TextField()
    param_value = models.FloatField()
    maps_to_module = models.ForeignKey('Module', null=True, on_delete=models.SET_NULL)
    maps_to_variable_name = models.TextField()

    class Meta:
        db_table = 'calibration_sloth_param'
