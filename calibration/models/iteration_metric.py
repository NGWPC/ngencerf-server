from django.db import models

from calibration.models.base_model import BaseModel


class IterationMetric(BaseModel):
    iteration = models.ForeignKey('Iteration', null=False, on_delete=models.CASCADE)
    metric = models.ForeignKey('Metric', null=False, on_delete=models.CASCADE)
    metric_value = models.FloatField(null=True)

    class Meta:
        db_table = 'iteration_metric'
