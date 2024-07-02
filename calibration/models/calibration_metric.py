from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.calibration_run import CalibrationRun
from calibration.models.metric import Metric


class CalibrationMetric(BaseModel):
    calibration_run = models.ForeignKey(CalibrationRun, null=True, on_delete=models.SET_NULL)
    metric = models.OneToOneField(Metric, null=True, on_delete=models.SET_NULL)
    objective_function = models.BooleanField()

    class Meta:
        db_table = 'calibration_metric'
