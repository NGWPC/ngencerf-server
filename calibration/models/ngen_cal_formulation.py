from django.db import models

from calibration.models import BaseModel


class NgenCalFormulation(BaseModel):
    description = models.TextField()
    name = models.TextField()
    modules = models.TextField()

    class Meta:
        db_table = 'ngen_cal_formulation'
