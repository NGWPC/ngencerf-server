from django.db import models

from calibration.models import BaseModel
from calibration.models.calibration_initial_parameter import CalibrationInitialParameter
from calibration.models.calibration_run import CalibrationRun


class CalibrationTuneParameter(BaseModel):
    calibration_run_pk = models.ForeignKey(CalibrationRun, on_delete=models.SET_NULL)
    calibration_initial_parameter_pk = models.ForeignKey(CalibrationInitialParameter, on_delete=models.SET_NULL)
    minimum = models.FloatField()
    maximum = models.FloatField()
    initial = models.FloatField()

    class Meta:
        db_table = 'calibration_tune_parameter'
