from django.db import models

from calibration.models import BaseModel
from calibration.models.metric import Metric


class MetricInput(BaseModel):
    description = models.TextField()
    is_active = models.BooleanField()
    name = models.TextField()
    metric_pk = models.ForeignKey(Metric, on_delete=models.SET_NULL)
    data_type = models.TextField()
    default_value = models.TextField()

    class Meta:
        db_table = 'metric_input'
