from django.db import models

from calibration.models.base_model import BaseModel


class Status(BaseModel):
    name = models.TextField(unique=True, null=False)

    class Meta:
        db_table = 'status'
