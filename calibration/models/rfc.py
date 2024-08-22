from django.db import models

from calibration.models.base_model import BaseModel


class Rfc(BaseModel):
    description = models.TextField(null=False)
    is_active = models.BooleanField(null=False, default=True)
    name = models.CharField(max_length=50, unique=True, null=False)

    class Meta:
        db_table = 'rfc'
