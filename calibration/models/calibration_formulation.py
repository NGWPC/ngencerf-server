from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.calibration_run import CalibrationRun
from calibration.models.module import Module


class CalibrationFormulation(BaseModel):
    description = models.TextField()
    module = models.ForeignKey(Module, null=True, on_delete=models.SET_NULL)
    calibration_run = models.ForeignKey(CalibrationRun, null=True, on_delete=models.SET_NULL)
    module_commit_hash = models.BinaryField()

    class Meta:
        db_table = 'calibration_formulation'
