from django.db import models

from calibration.models import BaseModel
from calibration.models.calibration_metric import CalibrationMetric
from calibration.models.metric import Metric


class CalibrationMetricInput(BaseModel):
    calibration_metric_pk = models.ForeignKey(CalibrationMetric, on_delete=models.SET_NULL)
    metric_pk = models.ForeignKey(Metric, on_delete=models.SET_NULL)
    data_type = models.TextField()
    value = models.FloatField()

    class Meta:
        db_table = 'calibration_metric_input'
