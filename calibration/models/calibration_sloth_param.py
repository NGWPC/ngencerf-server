from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.calibration_run import CalibrationRun


class CalibrationSlothParam(BaseModel):
    calibration_run_pk = models.ForeignKey(CalibrationRun, null=True, on_delete=models.SET_NULL)
    param_name = models.TextField()
    param_count = models.IntegerField()
    param_type = models.TextField()
    param_units = models.TextField()
    param_location = models.TextField()
    param_value = models.FloatField()
    maps_to_module_pk = models.IntegerField
    maps_to_variable_name = models.TextField()

    class Meta:
        db_table = 'calibration_sloth_param'
