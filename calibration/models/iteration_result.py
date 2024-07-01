from django.db import models

from calibration.models import BaseModel
from calibration.models.iteration import Iteration


class IterationResult(BaseModel):
    iteration_pk = models.ForeignKey(Iteration, on_delete=models.SET_NULL)
    filename = models.TextField

    class Meta:
        db_table = 'iteration_result'
