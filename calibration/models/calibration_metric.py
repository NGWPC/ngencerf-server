from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.calibration_run import CalibrationRun
from calibration.models.metric import Metric


class CalibrationMetric(BaseModel):
    calibration_run = models.ForeignKey(CalibrationRun, null=False, on_delete=models.CASCADE)
    metric = models.ForeignKey(Metric, null=False, on_delete=models.CASCADE)
    objective_function = models.BooleanField(null=False, default=False)

    class Meta:
        db_table = 'calibration_metric'
