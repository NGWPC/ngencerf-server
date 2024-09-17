from django.db import models

from calibration.models.base_model import BaseModel


class PlotDefinitions(BaseModel):
    description = models.TextField(null=False)
    is_active = models.BooleanField(null=False, default=True)
    name = models.CharField(max_length=50, unique=True, null=False)
    location = models.CharField(max_length=50, null=False)
    valid_optimizations = models.TextField(null=False)
    # True if validation plot; False if calibration plot
    validation = models.BooleanField(null=False)
    filename_mask = models.TextField(null=False)

    class Meta:
        db_table = 'plot_definitions'
