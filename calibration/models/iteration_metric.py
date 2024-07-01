from django.db import models

from calibration.models import BaseModel
from calibration.models.calibration_metric import CalibrationMetric
from calibration.models.iteration import Iteration


class IterationMetric(BaseModel):
    iteration_pk = models.ForeignKey(Iteration, on_delete=models.SET_NULL)
    calibration_metric_pk = models.ForeignKey(CalibrationMetric, on_delete=models.SET_NULL)

    class Meta:
        db_table = 'iteration_metric'
