from django.db import models

from calibration.models.base_model import BaseModel


class OptimizationInput(BaseModel):
    description = models.TextField(null=False)
    is_active = models.BooleanField(null=False, default=True)
    name = models.CharField(max_length=50, null=False)
    data_type = models.CharField(max_length=50, null=False)
    default_value = models.FloatField(null=False)
    min = models.FloatField(null=True)
    max = models.FloatField(null=True)
    optimization = models.ForeignKey('Optimization', null=False, on_delete=models.CASCADE, related_name='inputs')

    class Meta:
        db_table = 'optimization_input'
        constraints = [
            models.UniqueConstraint(fields=['name', 'optimization'], name='optimization_input__name__optimization__unique')
        ]

    def __str__(self):
        return (
            f"OptimizationInput: {self.id}, "
            f"name: {self.name:20}, "
            f"data_type: {self.data_type}, "
            f"optimization.name: {self.optimization.name}"
        )
