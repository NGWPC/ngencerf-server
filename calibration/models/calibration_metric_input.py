from django.db import models

from calibration.models.base_model import BaseModel


class CalibrationMetricInput(BaseModel):
    calibration_metric = models.ForeignKey('CalibrationMetric', null=True, on_delete=models.SET_NULL)
    metric_input = models.ForeignKey("MetricInput", null=True, on_delete=models.SET_NULL)
    data_type = models.TextField()
    value = models.FloatField()

    class Meta:
        db_table = 'calibration_metric_input'
