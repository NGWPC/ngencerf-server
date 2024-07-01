from django.db import models

from calibration.models import BaseModel
from calibration.models.calibration_run import CalibrationRun
from calibration.models.metric import Metric


class CalibrationMetric(BaseModel):
    calibration_run_pk = models.ForeignKey(CalibrationRun, on_delete=models.SET_NULL)
    metric_pk = models.ForeignKey(Metric, on_delete=models.SET_NULL)
    objective_function = models.BooleanField()

    class Meta:
        db_table = 'calibration_metric'
