from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.iteration import Iteration


class IterationResult(BaseModel):
    iteration = models.ForeignKey(Iteration, null=True, on_delete=models.SET_NULL)
    filename = models.TextField(null=False)

    class Meta:
        db_table = 'iteration_result'

    def __str__(self):
        return (
            f"IterationResult: {self.id}, "
            f"({self.iteration}), "
            f"filename: {str(self.filename)}"
        )
