from django.db import models

from calibration.models.base_model import BaseModel


class ValidationRun(BaseModel):
    calibration_run = models.ForeignKey('CalibrationRun', null=False, related_name="validations", on_delete=models.CASCADE, db_index=True)
    iteration = models.IntegerField(null=True)
    # validation_start_period = models.DateTimeField(null=True)
    # validation_end_period = models.DateTimeField(null=True)
    # validation_eval_start_period = models.DateTimeField(null=True)
    # validation_eval_end_period = models.DateTimeField(null=True)
    status = models.ForeignKey('Status', null=False, on_delete=models.CASCADE, db_index=True)

    class Meta:
        db_table = 'validation_run'

    def __str__(self):
        return (
            f"ValidationRun {self.id}, "
            f"Calibration Run {self.calibration_run.id}, "
            f"owner: {self.calibration_run.owner.username}, "  # type: ignore[attr-defined]  # Suppress PyCharm warning for unresolved attribute
            f"status.name: {self.status.name}"
        )
