from django.db import models

from calibration.models.base_model import BaseModel


class ForcingSource(BaseModel):
    description = models.TextField(null=False, blank=False)
    is_active = models.BooleanField(null=False, default=True)
    name = models.TextField(unique=True, null=False)

    class Meta:
        db_table = 'forcing_source'
