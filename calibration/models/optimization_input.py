from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.optimization import Optimization


class OptimizationInput(BaseModel):
    description = models.TextField(null=False, blank=False)
    is_active = models.BooleanField(null=False, default=True)
    name = models.TextField(unique=True, null=False)
    optimization = models.ForeignKey(Optimization, null=True, on_delete=models.SET_NULL)

    class Meta:
        db_table = 'optimization_input'
