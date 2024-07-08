from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.calibration_formulation import CalibrationFormulation
from calibration.models.calibration_run import CalibrationRun


class CalibrationInitialParameter(BaseModel):
    calibration_run = models.ForeignKey(CalibrationRun, null=True, on_delete=models.SET_NULL)
    calibration_formulation = models.ForeignKey(CalibrationFormulation, null=True, on_delete=models.SET_NULL)
    name = models.TextField(unique=True, null=False)
    default_value = models.FloatField()

    class Meta:
        db_table = 'calibration_initial_parameter'
