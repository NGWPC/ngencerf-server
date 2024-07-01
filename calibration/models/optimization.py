from django.db import models

from calibration.models import BaseModel


class Optimization(BaseModel):
    description = models.TextField()
    is_active = models.BooleanField()
    name = models.TextField()
    stop_criteria_name = models.TextField()
    stop_criteria_data_type = models.TextField()

    class Meta:
        db_table = 'optimization'
