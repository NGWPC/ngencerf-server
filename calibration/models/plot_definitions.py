from django.db import models

from calibration.models.base_model import BaseModel


class PlotDefinitions(BaseModel):
    description = models.TextField(null=False)
    is_active = models.BooleanField(null=False, default=True)
    name = models.TextField(unique=True, null=False)

    class Meta:
        db_table = 'plot_definitions'
