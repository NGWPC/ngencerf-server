from django.contrib.auth import get_user_model
from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.status import Status


class ValidationRun(BaseModel):
    description = models.TextField(null=False)
    is_active = models.BooleanField(null=False, default=True)
    calibration_run = models.ForeignKey('CalibrationRun', null=True, related_name="validations", on_delete=models.SET_NULL)
    iteration = models.IntegerField(null=True)
    validation_start_period = models.DateTimeField()
    validation_end_period = models.DateTimeField()
    validation_eval_start_period = models.DateTimeField()
    validation_eval_end_period = models.DateTimeField()
    # This should be a required field (null=FALSE), but we'll leave it as optional for now
    owner = models.ForeignKey(get_user_model(), null=True, on_delete=models.SET_NULL)
    status = models.ForeignKey(Status, null=False, on_delete=models.CASCADE)

    class Meta:
        db_table = 'validation_run'
