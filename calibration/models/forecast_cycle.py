from django.db import models

from calibration.models.base_model import BaseModel


class ForecastCycle(BaseModel):
    is_active = models.BooleanField(null=False, default=True)
    name = models.CharField(max_length=50, unique=True, null=False)
    internal_name = models.CharField(max_length=50, unique=True, null=False)
    data_sources = models.CharField(max_length=100, null=False)
    time_range = models.CharField(max_length=100, null=False)

    class Meta:
        db_table = 'forecast_cycle'

    def __str__(self):
        return f"{self.name}"
