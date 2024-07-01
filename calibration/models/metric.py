from django.db import models

from calibration.models.base_model import BaseModel


class Metric(BaseModel):
    description = models.TextField()
    is_active = models.BooleanField()
    name = models.TextField(unique=True, null=False)

    class Meta:
        db_table = 'metric'
