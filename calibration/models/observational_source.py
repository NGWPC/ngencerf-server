from django.db import models

from calibration.models.base_model import BaseModel


class ObservationalSource(BaseModel):
    description = models.TextField()
    is_active = models.BooleanField()
    name = models.TextField(unique=True, null=False)
    url = models.TextField(null=True)

    class Meta:
        db_table = 'observational_source'
