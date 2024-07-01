from django.db import models

from calibration.models import BaseModel
from calibration.models.module import Module


class ModuleInputVariable(BaseModel):
    description = models.TextField()
    is_active = models.BooleanField()
    name = models.TextField()
    data_type = models.TextField()
    module_pk = models.ForeignKey(Module, on_delete=models.SET_NULL)

    class Meta:
        db_table = 'module_input_variable'
