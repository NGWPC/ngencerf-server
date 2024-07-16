from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.calibration_initial_parameter import CalibrationInitialParameter


class CalibrationTuneParameter(BaseModel):
    calibration_initial_parameter = models.ForeignKey(CalibrationInitialParameter, null=False, on_delete=models.CASCADE)
    minimum = models.FloatField(null=False)
    maximum = models.FloatField(null=False)
    initial = models.FloatField(null=False)

    class Meta:
        db_table = 'calibration_tune_parameter'
