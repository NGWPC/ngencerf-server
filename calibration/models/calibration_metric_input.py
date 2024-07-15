from django.db import models

from calibration.models.base_model import BaseModel


class CalibrationMetricInput(BaseModel):
    calibration_metric = models.ForeignKey('CalibrationMetric', null=False, on_delete=models.CASCADE)
    metric_input = models.ForeignKey("MetricInput", null=False, on_delete=models.CASCADE)
    data_type = models.TextField(null=False, blank=False)
    value = models.FloatField(null=False)

    class Meta:
        db_table = 'calibration_metric_input'
