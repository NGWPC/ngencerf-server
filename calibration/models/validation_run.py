from django.contrib.auth import get_user_model
from django.db import models

from calibration.models.base_model import BaseModel


class ValidationRun(BaseModel):
    description = models.TextField(null=False)
    is_active = models.BooleanField(null=False, default=True)
    calibration_run = models.ForeignKey('CalibrationRun', null=False, related_name="validations", on_delete=models.CASCADE, db_index=True)
    iteration = models.IntegerField(null=True)
    validation_start_period = models.DateTimeField()
    validation_end_period = models.DateTimeField()
    validation_eval_start_period = models.DateTimeField()
    validation_eval_end_period = models.DateTimeField()
    owner = models.ForeignKey(get_user_model(), null=False, on_delete=models.RESTRICT, db_index=True)
    status = models.ForeignKey('Status', null=False, on_delete=models.CASCADE, db_index=True)

    class Meta:
        db_table = 'validation_run'
