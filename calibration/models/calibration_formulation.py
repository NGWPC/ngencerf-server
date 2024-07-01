from django.db import models

from calibration.models import BaseModel
from calibration.models.calibration_run import CalibrationRun
from calibration.models.module import Module


class CalibrationFormulation(BaseModel):
    description = models.TextField()
    module_pk = models.ForeignKey(Module, on_delete=models.SET_NULL)
    calibration_run_pk = models.ForeignKey(CalibrationRun, on_delete=models.SET_NULL)
    module_commit_hash = models.BinaryField()

    class Meta:
        db_table = 'calibration_formulation'
