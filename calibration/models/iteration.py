from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.calibration_run import CalibrationRun


class Iteration(BaseModel):
    iteration_num = models.IntegerField(null=False)
    calibration_run = models.ForeignKey(CalibrationRun, null=False, on_delete=models.CASCADE)
    calibration_output_variable_value = models.FloatField(null=True)
    worker_name = models.TextField(null=False)
    worker_number = models.PositiveIntegerField(null=False)

    class Meta:
        db_table = 'iteration'
        constraints = [
            models.UniqueConstraint(fields=['iteration_num', 'worker_name', 'calibration_run'], name='iteration_iteration_num_worker_calibration_run__unique')
        ]

    def __str__(self):
        return (
            f"Iteration: {self.id}, "
            f"Iteration number: {self.iteration_num},"
            f"Worker name: {str(self.worker_name)}, "
            f"Worker number: {self.worker_number}"
        )

