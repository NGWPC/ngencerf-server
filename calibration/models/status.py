from django.db import models

from calibration.models.base_model import BaseModel


class Status(BaseModel):
    name = models.CharField(max_length=50, unique=True, null=False)

    class Meta:
        db_table = 'status'
