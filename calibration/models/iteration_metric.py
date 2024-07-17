from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.iteration import Iteration


class IterationMetric(BaseModel):
    iteration = models.ForeignKey(Iteration, null=True, on_delete=models.SET_NULL)
    metric = models.ForeignKey('Metric', null=True, on_delete=models.SET_NULL)

    class Meta:
        db_table = 'iteration_metric'
