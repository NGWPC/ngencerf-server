from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.calibration_initial_parameter import CalibrationInitialParameter
from calibration.models.iteration import Iteration


class IterationTuneParameter(BaseModel):
    iteration = models.ForeignKey(Iteration, null=False, on_delete=models.CASCADE)
    calibration_initial_parameter = models.ForeignKey(CalibrationInitialParameter, null=False, on_delete=models.CASCADE)
    data_type = models.TextField(null=False, blank=False)
    tuned_value = models.FloatField(null=False)

    class Meta:
        db_table = 'iteration_tune_parameter'
