from django.db import models

from calibration.models.base_model import BaseModel


class CalibrationFormulation(BaseModel):
    description = models.TextField()
    name = models.TextField(null=False)
    groups = models.TextField(null=False)
    used_by_calibration_run = models.BooleanField()

    class Meta:
        db_table = 'calibration_formulation'
