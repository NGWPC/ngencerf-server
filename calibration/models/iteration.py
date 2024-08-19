from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.calibration_run import CalibrationRun


class Iteration(BaseModel):
    iteration_num = models.IntegerField(null=False)
    calibration_run = models.ForeignKey(CalibrationRun, null=False, on_delete=models.RESTRICT)
    calibration_output_variable_value = models.FloatField(null=True)
    worker_name = models.TextField(null=False)
    worker_number = models.PositiveIntegerField(null=False)

    class Meta:
        db_table = 'iteration'
        constraints = [
            models.UniqueConstraint(fields=['iteration_num', 'worker_name', 'calibration_run'], name='iteration_iteration_num_worker_calibration_run__unique')
        ]
