from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.calibration_formulation import CalibrationFormulation


class ModuleOutputVariable(BaseModel):
    description = models.TextField(null=False)
    name = models.CharField(max_length=255, null=False)
    calibration_formulation = models.ForeignKey(CalibrationFormulation, null=False, on_delete=models.CASCADE, related_name='output_variables')

    class Meta:
        db_table = 'module_output_variable'
        constraints = [
            models.UniqueConstraint(fields=['name', 'calibration_formulation'], name='module_output_variable__name__calibration_formulation__unique')
        ]

    def __str__(self):
        return (
            f"ModuleOutputVariable: {self.id}, "
            f"name: {self.name:20}, "
            f"calibration_formulation: {self.calibration_formulation.id} ({self.calibration_formulation.name})"
        )


