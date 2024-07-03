from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.domain import Domain


class Gage(BaseModel):
    description = models.TextField()
    is_active = models.BooleanField()
    gage_id = models.TextField(unique=True, null=False)
    agency = models.TextField()
    station_name = models.TextField()
    site_type = models.TextField()
    latitude = models.FloatField()
    longitude = models.FloatField()
    lat_long_accuracy = models.TextField()
    lat_long_datum = models.TextField()
    discharge_period = models.IntegerField
    altitude = models.FloatField(null=True)
    altitude_accuracy = models.TextField(null=True)
    altitude_datum = models.TextField(null=True)
    huc = models.TextField()
    drainage_area = models.FloatField(null=True)
    contrib_drainage_area = models.FloatField(null=True)
    domain = models.ForeignKey(Domain, null=True, on_delete=models.SET_NULL)

    class Meta:
        db_table = 'gage'


