from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.module import Module
from calibration.models.module_group import ModuleGroup


class ModuleGroupMember(BaseModel):
    description = models.TextField()
    is_active = models.BooleanField()
    module_pk = models.ForeignKey(Module, null=True, on_delete=models.SET_NULL)
    module_group_pk = models.ForeignKey(ModuleGroup, null=True, on_delete=models.SET_NULL)

    class Meta:
        db_table = 'module_group_member'
