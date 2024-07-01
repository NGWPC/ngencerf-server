from django.db import models

from calibration.models.base_model import BaseModel


class ObservationalSource(BaseModel):
    description = models.TextField()
    is_active = models.BooleanField()
    name = models.TextField()
    url = models.TextField()

    class Meta:
        db_table = 'observational_source'
