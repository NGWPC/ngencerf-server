from django.db import models

from calibration.models.base_model import BaseModel


class DataValidation(BaseModel):
    start_date = models.DateTimeField(null=True)
    end_date = models.DateTimeField(null=True)
    status = models.ForeignKey('Status', null=False, on_delete=models.RESTRICT, db_index=True)

    class Meta:
        db_table = 'data_validation'
