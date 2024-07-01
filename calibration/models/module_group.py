from django.db import models

from calibration.models import BaseModel
from calibration.models.module import Module


class ModuleGroup(BaseModel):
    description = models.TextField()
    is_active = models.BooleanField()
    name = models.TextField()
    modules = models.ManyToManyField(Module, related_name="groups")

    class Meta:
        db_table = 'module_group'
