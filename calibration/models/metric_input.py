from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.metric import Metric


class MetricInput(BaseModel):
    description = models.TextField()
    name = models.TextField(unique=True, null=False)
    metric = models.ForeignKey(Metric, null=False, on_delete=models.CASCADE)
    data_type = models.TextField(null=False, blank=False)
    default_value = models.TextField(null=False)

    class Meta:
        db_table = 'metric_input'
