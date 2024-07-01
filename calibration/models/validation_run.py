from django.db import models

from calibration.models import BaseModel
from calibration.models.calibration_run import CalibrationRun
from calibration.models.status import Status


class ValidationRun(BaseModel):
    description = models.TextField()
    is_active = models.BooleanField()
    calibration_run_pk = models.ForeignKey(CalibrationRun, on_delete=models.SET_NULL)
    calibration_run_pk_tune_parameters = models.ForeignKey(CalibrationRun, on_delete=models.SET_NULL)
    validation_start_period = models.DateTimeField()
    validation_end_period = models.DateTimeField()
    validation_eval_start_period = models.DateTimeField()
    validation_eval_end_period = models.DateTimeField()
    status_pk = models.ForeignKey(Status, on_delete=models.SET_NULL)

    class Meta:
        db_table = 'validation_run'
