from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.calibration_run import CalibrationRun


class Iteration(BaseModel):
    iteration_num = models.IntegerField()
    calibration_run_pk = models.ForeignKey(CalibrationRun, null=True, on_delete=models.SET_NULL)
    realization_filename = models.TextField()
    calibration_output_variable_value = models.FloatField()
    best = models.BooleanField()

    class Meta:
        db_table = 'iteration'
