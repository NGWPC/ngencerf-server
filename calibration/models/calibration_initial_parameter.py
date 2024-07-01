from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.calibration_run import CalibrationRun
from calibration.models.module import Module


class CalibrationInitialParameter(BaseModel):
    calibration_run_pk = models.ForeignKey(CalibrationRun, null=True, on_delete=models.SET_NULL)
    module_pk = models.ForeignKey(Module, null=True, on_delete=models.SET_NULL)
    name = models.TextField(unique=True, null=False)
    default_value = models.FloatField()

    class Meta:
        db_table = 'calibration_initial_parameter'
