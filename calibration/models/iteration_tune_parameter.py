from django.db import models

from calibration.models import BaseModel
from calibration.models.calibration_initial_parameter import CalibrationInitialParameter
from calibration.models.iteration import Iteration


class IterationTuneParameter(BaseModel):
    iteration_pk = models.ForeignKey(Iteration, on_delete=models.SET_NULL)
    calibration_initial_parameter_pk = models.ForeignKey(CalibrationInitialParameter, on_delete=models.SET_NULL)
    data_type = models.TextField()
    tuned_value = models.FloatField()

    class Meta:
        db_table = 'iteration_tune_parameter'
