from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.metric import Metric


class MetricInput(BaseModel):
    description = models.TextField(null=False, blank=False)
    is_active = models.BooleanField(null=False, default=True)
    name = models.TextField(null=False)
    data_type = models.TextField(null=False, blank=False)
    default_value = models.TextField(null=False)
    metric = models.ForeignKey(Metric, null=False, on_delete=models.CASCADE)

    class Meta:
        db_table = 'metric_input'
        constraints = [
            models.UniqueConstraint(fields=['name', 'metric'], name='metric_input__name__metric__unique')
        ]
