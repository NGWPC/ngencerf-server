from django.db import models
from django.db.models import Q

from calibration.models.base_model import BaseModel


class ModuleProperty(BaseModel):
    module = models.ForeignKey("Module", on_delete=models.RESTRICT, related_name="properties")
    description = models.TextField(null=False)
    name = models.CharField(max_length=50)
    data_type = models.CharField(max_length=50)
    default_value = models.CharField(max_length=200, null=False)

    class Meta:
        db_table = "module_property"

        constraints = [
            models.UniqueConstraint(fields=["module", "name"], name="uq_module_property__module_name"),
        ]

    def __str__(self):
        return f"ModuleProperty: {self.id}, module_id={self.module_id}, name={self.name}"
