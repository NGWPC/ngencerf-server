from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.calibration_run import CalibrationRun
from calibration.models.optimization_input import OptimizationInput


class CalibrationOptimizationInput(BaseModel):
    calibration_run = models.ForeignKey(CalibrationRun, null=True, on_delete=models.SET_NULL)
    optimization_input = models.ForeignKey(OptimizationInput, null=True, on_delete=models.SET_NULL)
    value = models.FloatField()

    class Meta:
        db_table = 'calibration_optimization_input'
