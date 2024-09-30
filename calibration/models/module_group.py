from django.db import models

from calibration.models.base_model import BaseModel


class ModuleGroup(BaseModel):
    description = models.TextField(null=False)
    is_active = models.BooleanField(default=False)
    name = models.CharField(max_length=50, unique=True, null=False)

    class Meta:
        db_table = 'module_group'

    def __str__(self):
        return (
            f"Module: {self.id}, "
            f"name: {self.name:20}"
        )
