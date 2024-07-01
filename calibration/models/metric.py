from django.db import models

from calibration.models import BaseModel


class Metric(BaseModel):
    description = models.TextField()
    is_active = models.BooleanField()
    name = models.TextField()

    class Meta:
        db_table = 'metric'
