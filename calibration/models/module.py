from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.module_group import ModuleGroup


class Module(BaseModel):
    description = models.TextField(null=False)
    is_active = models.BooleanField(default=False)
    name = models.CharField(max_length=50, unique=True, null=False)
    groups = models.ManyToManyField(ModuleGroup, db_table='module_group_members')

    class Meta:
        db_table = 'module'

    def __str__(self):
        return (
            f"Module: {self.id}, "
            f"name: {self.name:20}"
        )
