from django.db import models

from calibration.models.base_model import BaseModel


class Optimization(BaseModel):
    description = models.TextField(null=False)
    is_active = models.BooleanField(null=False, default=True)
    name = models.TextField(unique=True, null=False)
    stop_criteria_name = models.TextField(null=False)
    stop_criteria_data_type = models.TextField(null=False)

    class Meta:
        db_table = 'optimization'
