from django.db import models

from calibration.models.base_model import BaseModel


class PlotDefinitions(BaseModel):
    description = models.TextField()
    is_active = models.BooleanField()
    name = models.TextField(unique=True, null=False)

    class Meta:
        db_table = 'plot_definitions'
