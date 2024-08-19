from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.calibration_run import CalibrationRun


class Iteration(BaseModel):
    iteration_num = models.IntegerField(null=False)
    calibration_run = models.ForeignKey(CalibrationRun, null=False, on_delete=models.RESTRICT)
    calibration_output_variable_value = models.FloatField(null=True)
    worker = models.TextField(null=False)
    best_for_worker = models.BooleanField(null=False, default=False)
    best_overall = models.BooleanField(null=False, default=False)

    class Meta:
        db_table = 'iteration'
        constraints = [
            models.UniqueConstraint(fields=['iteration_num', 'calibration_run'], name='iteration_iteration_num_calibration_run__unique')
        ]
