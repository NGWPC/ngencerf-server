from django.db import models

from calibration.models.base_model import BaseModel


class Gage(BaseModel):
    is_active = models.BooleanField(null=False, blank=False)
    gage_id = models.TextField(unique=True, null=False)
    nws_id = models.TextField(null=True)
    rfc = models.ForeignKey('Rfc', null=True, on_delete=models.SET_NULL)
    nwm_v3_calibrated = models.BooleanField(null=False, blank=False, default=False)
    agency = models.TextField(null=False, blank=False)
    station_name = models.TextField(null=False, blank=False)
    site_type = models.TextField(null=False, blank=False)
    latitude = models.FloatField(null=True)
    longitude = models.FloatField(null=True)
    lat_long_accuracy = models.TextField(null=False, blank=False)
    lat_long_datum = models.TextField(null=False, blank=False)
    altitude = models.FloatField(null=True)
    altitude_accuracy = models.TextField(null=True)
    altitude_datum = models.TextField(null=True)
    huc = models.TextField(null=False, blank=False)
    drainage_area = models.FloatField(null=True)
    contrib_drainage_area = models.FloatField(null=True)
    domain = models.ForeignKey('Domain', null=True, on_delete=models.SET_NULL)
    observational_source = models.ForeignKey('ObservationalSource', null=True, on_delete=models.CASCADE)

    class Meta:
        db_table = 'gage'


