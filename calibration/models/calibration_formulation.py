from django.db import models

from calibration.models.base_model import BaseModel


class CalibrationFormulation(BaseModel):
    description = models.TextField()
    module = models.ForeignKey('Module', null=False, on_delete=models.RESTRICT)
    bmi_config_path = models.CharField(max_length=255, null=True)
    calibration_run = models.ForeignKey('CalibrationRun', null=False, on_delete=models.RESTRICT)
    module_commit_hash = models.CharField(max_length=50, null=True)

    class Meta:
        db_table = 'calibration_formulation'
        constraints = [
            models.UniqueConstraint(fields=['module', 'calibration_run'], name='calibration_formulation__module__calibration_run__unique')
        ]

    def __str__(self):
        return (
            f"CalibrationFormulation: {self.id}, "
            f"module: {self.module.name:20}, "
            f"calibration_run: {self.calibration_run.id}"
        )
