from django.db import models

from calibration.models import HindcastRun
from calibration.models.base_run import BaseRun


class VerificationRun(BaseRun):
    hindcast_run = models.ForeignKey(HindcastRun, on_delete=models.CASCADE, db_index=True, related_name="verification_runs")

    class Meta:
        db_table = "verification_run"
        indexes = [
            models.Index(fields=["hindcast_run"], name="idx_verif_hindcast_run"),
            models.Index(fields=["status"], name="idx_verif_status"),
        ]

    def __str__(self):
        return (
            f"VerificationRun {self.id}, "
            f"hindcast_run_id: {self.hindcast_run_id}, "
            f"status.name: {self.status.name}"
        )
