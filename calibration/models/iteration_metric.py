from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.iteration import Iteration


class IterationMetric(BaseModel):
    iteration = models.ForeignKey('Iteration', null=False, on_delete=models.RESTRICT)
    metric = models.ForeignKey('Metric', null=False, on_delete=models.RESTRICT)
    metric_value = models.FloatField(null=True)

    class Meta:
        db_table = 'iteration_metric'
