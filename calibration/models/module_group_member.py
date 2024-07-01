from django.db import models

from calibration.models import BaseModel
from calibration.models.module import Module
from calibration.models.module_group import ModuleGroup


class ModuleGroupMember(BaseModel):
    description = models.TextField()
    is_active = models.BooleanField()
    module_pk = models.ForeignKey(Module, on_delete=models.SET_NULL)
    module_group_pk = models.ForeignKey(ModuleGroup, on_delete=models.SET_NULL)

    class Meta:
        db_table = 'module_group_member'
