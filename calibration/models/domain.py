from django.db import models

from calibration.models.base_model import BaseModel


class Domain(BaseModel):
    description = models.TextField(null=False, blank=False)
    is_active = models.BooleanField(null=False, default=True)
    name = models.TextField(unique=True, null=False)
    forcing_url = models.TextField(null=True)

    class Meta:
        db_table = 'domain'
