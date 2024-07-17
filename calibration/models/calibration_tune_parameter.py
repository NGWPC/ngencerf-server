from django.db import models

from calibration.models.base_model import BaseModel


class CalibrationTuneParameter(BaseModel):
    calibration_run = models.ForeignKey('CalibrationRun', null=False, on_delete=models.CASCADE)
    calibration_formulation = models.ForeignKey('CalibrationFormulation', null=False, on_delete=models.CASCADE)
    name = models.TextField(null=False)
    data_type = models.TextField(null=False, blank=False)
    default_value = models.FloatField(null=False)
    initial_value = models.FloatField(null=False)
    minimum = models.FloatField(null=False)
    maximum = models.FloatField(null=False)
    calibratable = models.BooleanField(null=False, default=False)

    class Meta:
        db_table = 'calibration_tune_parameter'
        constraints = [
            models.UniqueConstraint(fields=['name', 'calibration_formulation', 'calibration_run'],
                                    name='calibration_tune_parameter__name__calibration_formulation__unique')
        ]
