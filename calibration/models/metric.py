from django.db import models

from calibration.models.base_model import BaseModel


class Metric(BaseModel):
    description = models.TextField(null=False)
    is_active = models.BooleanField(null=False, default=True)
    name = models.TextField(unique=True, null=False)
    categorical = models.BooleanField(null=False, default=False)

    class Meta:
        db_table = 'metric'
