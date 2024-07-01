from django.db import models

from calibration.models.base_model import BaseModel


class Domain(BaseModel):
    description = models.TextField()
    is_active = models.BooleanField()
    name = models.TextField(unique=True, null=False)
    forcing_url = models.TextField(null=True)

    class Meta:
        db_table = 'domain'
