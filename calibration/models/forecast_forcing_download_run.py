from django.db import models

from calibration.models.base_model import BaseModel


class ForecastForcingDownloadRun(BaseModel):
    status = models.ForeignKey('Status', null=False, on_delete=models.RESTRICT, db_index=True)
    submit_date = models.DateTimeField(null=True)
    run_start = models.DateTimeField(null=True)
    run_end = models.DateTimeField(null=True)
    performance_metrics = models.ForeignKey('PerformanceMetrics', null=True, on_delete=models.CASCADE)
    slurm_job_id = models.IntegerField(null=True)

    class Meta:
        db_table = 'forecast_forcing_download_run'

    def __str__(self):
        return (
            f"ForecastForcingDownloadRun {self.id}, "
            f"cycle {self.forecast_run.cycle.name}, "
            f"Calibration Job {self.forecast_run.calibration_run.id}, "
            f"owner: {selfforecast_run.calibration_run.owner.username}, "  # type: ignore[attr-defined]  # Suppress PyCharm warning for unresolved attribute
            f"status.name: {self.status.name}"
        )
