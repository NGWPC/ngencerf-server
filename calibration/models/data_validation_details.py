from django.db import models

from calibration.models.base_model import BaseModel


class DataValidationDetails(BaseModel):
    filename = models.CharField(max_length=200, null=False, blank=False)
    line_number = models.IntegerField(null=False)
    line = models.CharField(max_length=200, null=False, blank=False)
    error = models.CharField(max_length=200, null=False, blank=False)
    data_validation = models.ForeignKey('DataValidation', null=False, on_delete=models.CASCADE)

    class Meta:
        db_table = 'data_validation_details'
