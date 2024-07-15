from django.db import models

from calibration.models.base_model import BaseModel


class Gage(BaseModel):
    is_active = models.BooleanField(null=False, blank=False)
    gage_id = models.TextField(unique=True, null=False)
    agency = models.TextField(null=False, blank=False)
    station_name = models.TextField(null=False, blank=False)
    site_type = models.TextField(null=False, blank=False)
    latitude = models.FloatField(null=False)
    longitude = models.FloatField(null=False)
    lat_long_accuracy = models.TextField(null=False, blank=False)
    lat_long_datum = models.TextField(null=False, blank=False)
    altitude = models.FloatField(null=True)
    altitude_accuracy = models.TextField(null=True)
    altitude_datum = models.TextField(null=True)
    huc = models.TextField(null=False, blank=False)
    drainage_area = models.FloatField(null=True)
    contrib_drainage_area = models.FloatField(null=True)
    domain = models.ForeignKey('Domain', null=True, on_delete=models.CASCADE)
    observational_source = models.ForeignKey('ObservationalSource', null=True, on_delete=models.CASCADE)

    class Meta:
        db_table = 'gage'


