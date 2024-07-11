from django.contrib.auth import get_user_model
from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.calibration_run import CalibrationRun


class ValidationRun(BaseModel):
    description = models.TextField()
    is_active = models.BooleanField()
    calibration_run = models.ForeignKey(CalibrationRun, null=True, related_name="validations", on_delete=models.SET_NULL)
    calibration_run_pk_tune_parameters = models.ForeignKey(CalibrationRun, related_name="validations_tune_parameters", null=True, on_delete=models.SET_NULL)
    validation_start_period = models.DateTimeField()
    validation_end_period = models.DateTimeField()
    validation_eval_start_period = models.DateTimeField()
    validation_eval_end_period = models.DateTimeField()
    # This should be a required field (null=FALSE), but we'll leave it as optional for now
    owner = models.ForeignKey(get_user_model(), null=True, on_delete=models.SET_NULL)
    status = models.TextField()

    class Meta:
        db_table = 'validation_run'
