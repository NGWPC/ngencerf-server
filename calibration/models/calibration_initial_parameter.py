from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.calibration_formulation import CalibrationFormulation
from calibration.models.calibration_run import CalibrationRun


class CalibrationInitialParameter(BaseModel):
    calibration_run = models.ForeignKey(CalibrationRun, null=False, on_delete=models.CASCADE)
    calibration_formulation = models.ForeignKey(CalibrationFormulation, null=False, on_delete=models.CASCADE)
    name = models.TextField(null=False)
    data_type = models.TextField(null=False, blank=False)
    default_value = models.FloatField(null=False)

    class Meta:
        db_table = 'calibration_initial_parameter'
        constraints = [
            models.UniqueConstraint(fields=['name', 'calibration_formulation', 'calibration_run'], name='calibration_initial_parameter__name__calibration_formulation__unique')
        ]
