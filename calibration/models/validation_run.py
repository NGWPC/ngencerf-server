from django.db import models

from calibration.models.base_model import BaseModel


class ValidationRun(BaseModel):
    calibration_run = models.ForeignKey('CalibrationRun', null=False, related_name="validations", on_delete=models.CASCADE, db_index=True)
    iteration = models.ForeignKey('Iteration', null=True, on_delete=models.CASCADE)
    status = models.ForeignKey('Status', null=False, on_delete=models.RESTRICT, db_index=True)
    submit_date = models.DateTimeField(null=True)
    run_start = models.DateTimeField(null=True)
    run_end = models.DateTimeField(null=True)
    performance_metrics = models.ForeignKey('PerformanceMetrics', null=True, on_delete=models.CASCADE)
    ngen_commit_hash = models.CharField(max_length=50, null=True)
    ngen_cal_commit_hash = models.CharField(max_length=50, null=True)
    slurm_job_id = models.IntegerField(null=True)
    validation_type = models.CharField(max_length=20, null=False)
    validation_worker_name = models.CharField(null=True)

    class Meta:
        db_table = 'validation_run'

    @property
    def worker_name(self):
        return self.iteration.worker_name if self.iteration else None

    @property
    def iteration_num(self):
        return self.iteration.iteration_num if self.iteration else None

    def __str__(self):
        return (
            f"ValidationRun {self.id}, "
            f"Calibration Run {self.calibration_run.id}, "
            f"owner: {self.calibration_run.owner.username}, "  # type: ignore[attr-defined]  # Suppress PyCharm warning for unresolved attribute
            f"status.name: {self.status.name}"
        )
