from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.metric import Metric


class MetricInput(BaseModel):
    description = models.TextField()
    is_active = models.BooleanField()
    name = models.TextField(unique=True, null=False)
    metric = models.OneToOneField(Metric, null=True, on_delete=models.SET_NULL)
    data_type = models.TextField()
    default_value = models.TextField()

    class Meta:
        db_table = 'metric_input'
