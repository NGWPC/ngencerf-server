from django.db import models
from django.db.models import CharField

from calibration.models.base_model import BaseModel


class CalibrationFormulation(BaseModel):
    description = models.TextField(null=False)
    name = models.CharField(max_length=50, null=False)
    groups = models.TextField(max_length=50, null=False)
    used_by_calibration_run = models.BooleanField(default=False)
    bmi_config_path = models.CharField(max_length=255)
    version = models.TextField(null=True)
    calibration_run = models.ForeignKey('CalibrationRun', null=False, on_delete=models.CASCADE)

    class Meta:
        db_table = 'calibration_formulation'
        constraints = [
            models.UniqueConstraint(fields=['name', 'calibration_run'], name='calibration_formulation__name__calibration_run__unique')
        ]

    def __str__(self):
        return (
            f"CalibrationFormulation: {self.id}, "
            f"Name: {self.name:20}, "
            f"Used by calibration run: {str(self.used_by_calibration_run):<5}, "
            f"Calibration Run: {self.calibration_run.id}"
        )
