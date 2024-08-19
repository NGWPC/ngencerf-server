from django.db import models

from calibration.models.base_model import BaseModel


class NgenCalFormulation(BaseModel):
    description = models.TextField(null=False)
    name = models.CharField(max_length=50, unique=True, null=False)
    modules = models.TextField()

    class Meta:
        db_table = 'ngen_cal_formulation'
