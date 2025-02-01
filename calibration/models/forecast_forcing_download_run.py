from calibration.models.base_run import BaseRun


class ForecastForcingDownloadRun(BaseRun):
    # No additional fields needed
    pass

    class Meta:
        db_table = 'forecast_forcing_download_run'

    def __str__(self):
        return (
            f"ForecastForcingDownloadRun {self.id}, "
            f"cycle {self.forecast_run.cycle.name}, "
            f"Calibration Job {self.forecast_run.calibration_run.id}, "
            f"owner: {self.forecast_run.calibration_run.owner.username}, "  # type: ignore[attr-defined]  # Suppress PyCharm warning for unresolved attribute
            f"status.name: {self.status.name}"
        )
