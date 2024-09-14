from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.calibration_run import CalibrationRun
from calibration.models.optimization_input import OptimizationInput


class CalibrationOptimizationInput(BaseModel):
    calibration_run = models.ForeignKey('CalibrationRun', null=False, on_delete=models.CASCADE)
    optimization_input = models.ForeignKey('OptimizationInput', null=False, on_delete=models.CASCADE)
    value = models.FloatField(null=False)

    class Meta:
        db_table = 'calibration_optimization_input'

    def __str__(self):
        return (
            f"CalibrationOptimizationInput: {self.id}, "
            f"Optimization input: ({self.optimization_input}), "
            f"Value: {self.value}"
        )
