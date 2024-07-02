from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.module import Module


class ModuleInputVariable(BaseModel):
    description = models.TextField()
    is_active = models.BooleanField()
    name = models.TextField(null=False)
    data_type = models.TextField()
    module = models.ForeignKey(Module, null=True, on_delete=models.SET_NULL)

    class Meta:
        db_table = 'module_input_variable'
        unique_together = ('name', 'module')
