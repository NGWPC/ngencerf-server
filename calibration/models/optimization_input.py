from django.db import models

from calibration.models import BaseModel
from calibration.models.optimization import Optimization


class OptimizationInput(BaseModel):
    description = models.TextField()
    is_active = models.BooleanField()
    name = models.TextField()
    optimization_pk = models.ForeignKey(Optimization, on_delete=models.SET_NULL)

    class Meta:
        db_table = 'optimization_input'
