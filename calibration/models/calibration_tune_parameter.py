from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.calibration_initial_parameter import CalibrationInitialParameter
from calibration.models.calibration_run import CalibrationRun


class CalibrationTuneParameter(BaseModel):
    calibration_run = models.ForeignKey(CalibrationRun, null=False, on_delete=models.CASCADE)
    calibration_initial_parameter = models.ForeignKey(CalibrationInitialParameter, null=False, on_delete=models.CASCADE)
    minimum = models.FloatField(null=False)
    maximum = models.FloatField(null=False)
    initial = models.FloatField(null=False)

    class Meta:
        db_table = 'calibration_tune_parameter'
