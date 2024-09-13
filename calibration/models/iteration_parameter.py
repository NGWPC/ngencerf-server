from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.iteration import Iteration


class IterationParameter(BaseModel):
    iteration = models.ForeignKey(Iteration, null=False, on_delete=models.CASCADE, db_index=True)
    calibration_parameter = models.ForeignKey('CalibrationParameter', null=False, on_delete=models.CASCADE)
    data_type = models.CharField(max_length=50, null=False)
    tuned_value = models.FloatField(null=False)
    best = models.BooleanField(null=False, default=False)

    class Meta:
        db_table = 'iteration_parameter'

    def __str__(self):
        return (
            f"IterationParameter: {self.id}, "
            f"Calibration parameter: ({self.calibration_parameter}), "
            f"Value: {str(self.tuned_value)}, "
            f"Best: {self.best}"
        )

