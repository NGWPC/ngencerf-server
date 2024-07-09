from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.calibration_formulation import CalibrationFormulation


class ModuleOutputVariable(BaseModel):
    description = models.TextField()
    name = models.TextField(null=False)
    data_type = models.TextField()
    calibration_formulation = models.ForeignKey(CalibrationFormulation, null=True, on_delete=models.SET_NULL)

    class Meta:
        db_table = 'module_output_variable'
        constraints = [
            models.UniqueConstraint(fields=['name', 'calibration_formulation'], name='module_output_variable__name__calibration_formulation__unique')
        ]
