from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.calibration_formulation import CalibrationFormulation


class ModuleOutputVariable(BaseModel):
    description = models.TextField()
    is_active = models.BooleanField()
    name = models.TextField(null=False)
    data_type = models.TextField()
    calibration_formulation = models.ForeignKey(CalibrationFormulation, null=True, on_delete=models.SET_NULL)

