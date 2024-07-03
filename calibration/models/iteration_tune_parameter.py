from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.calibration_initial_parameter import CalibrationInitialParameter
from calibration.models.iteration import Iteration


class IterationTuneParameter(BaseModel):
    iteration = models.ForeignKey(Iteration, null=True, on_delete=models.SET_NULL)
    calibration_initial_parameter = models.ForeignKey(CalibrationInitialParameter, null=True, on_delete=models.SET_NULL)
    data_type = models.TextField()
    tuned_value = models.FloatField()

    class Meta:
        db_table = 'iteration_tune_parameter'
