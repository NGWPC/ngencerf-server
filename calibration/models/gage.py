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
    huc = models.TextField()
    drainage_area = models.FloatField()
    contrib_drainage_area = models.FloatField()
    domain_pk = models.ForeignKey(Domain, null=True, on_delete=models.SET_NULL)

    class Meta:
        db_table = 'gage'


