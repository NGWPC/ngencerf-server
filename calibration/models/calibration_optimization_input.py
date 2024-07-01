from django.db import models

from calibration.models import BaseModel
from calibration.models.calibration_run import CalibrationRun
from calibration.models.optimization_input import OptimizationInput


class CalibrationOptimizationInput(BaseModel):
    calibration_run_pk = models.ForeignKey(CalibrationRun, on_delete=models.SET_NULL)
    optimization_input_pk = models.ForeignKey(OptimizationInput, on_delete=models.SET_NULL)
    value = models.FloatField()

    class Meta:
        db_table = 'calibration_optimization_input'
