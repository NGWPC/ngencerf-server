from django.db import models

from calibration.models import BaseModel
from calibration.models.calibration_run import CalibrationRun


class CalibrationStopCriteria(BaseModel):
    description = models.TextField()
    calibration_run_pk = models.ForeignKey(CalibrationRun, on_delete=models.SET_NULL)
    value = models.IntegerField()
    ordinal = models.IntegerField()

    class Meta:
        db_table = 'calibration_stop_criteria'
