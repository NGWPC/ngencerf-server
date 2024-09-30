from django.db import models

from calibration.models.base_model import BaseModel


class IterationParameter(BaseModel):
    iteration = models.ForeignKey('Iteration', null=False, on_delete=models.CASCADE, db_index=True)
    calibration_parameter = models.ForeignKey('CalibrationParameter', null=False, on_delete=models.CASCADE)
    data_type = models.CharField(max_length=50, null=False)
    tuned_value = models.FloatField(null=False)
    best = models.BooleanField(null=False, default=False)

    class Meta:
        db_table = 'iteration_parameter'

    def __str__(self):
        return (
            f"IterationParameter: {self.id}, "
            f"calibration_parameter: ({self.calibration_parameter}), "
            f"tuned_value: {str(self.tuned_value)}, "
            f"best: {self.best}"
        )

