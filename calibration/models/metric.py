from django.db import models

from calibration.models.base_model import BaseModel


class Metric(BaseModel):
    description = models.TextField(null=False)
    is_active = models.BooleanField(null=False, default=True)
    name = models.CharField(max_length=255, unique=True, null=False)
    categorical = models.BooleanField(null=False, default=False)
    event_based = models.BooleanField(null=False, default=False)

    class Meta:
        db_table = 'metric'

    def __str__(self):
        return (
            f"Metric: {self.id}, "
            f"Name: {self.name:10}"
        )
