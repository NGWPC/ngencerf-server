from django.db import models

from calibration.models.base_model import BaseModel


class CalibrationFormulation(BaseModel):
    description = models.TextField(null=False, blank=False)
    name = models.TextField(null=False)
    groups = models.TextField(null=False)
    used_by_calibration_run = models.BooleanField(default=False)
    calibration_run = models.ForeignKey('CalibrationRun', null=False, on_delete=models.CASCADE)

    class Meta:
        db_table = 'calibration_formulation'
        constraints = [
            models.UniqueConstraint(fields=['name', 'calibration_run'], name='calibration_formulation__name__calibration_run__unique')
        ]

