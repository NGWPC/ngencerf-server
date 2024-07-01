from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.module_group import ModuleGroup


class Module(BaseModel):
    description = models.TextField()
    is_active = models.BooleanField()
    name = models.TextField()
    ngen_cal_active = models.BooleanField()
    groups = models.ManyToManyField(ModuleGroup)

    class Meta:
        db_table = 'module'
