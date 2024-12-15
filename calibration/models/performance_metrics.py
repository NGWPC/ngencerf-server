from django.db import models
from django.db.models import ExpressionWrapper, FloatField, Value, F, Func, When, Case
from django.db.models.functions import Coalesce, NullIf

from calibration.models.base_model import BaseModel

class ExtractEpoch(models.Func):
    function = "EXTRACT"
    template = "%(function)s(EPOCH FROM %(expressions)s)"
    output_field = models.FloatField()


class PerformanceMetrics(BaseModel):
    slurm_job_id = models.CharField(max_length=50, null=True)
    elapsed_time = models.DurationField(null=False)
    num_cpus = models.IntegerField(null=True)
    cpu_time = models.DurationField(null=True)
    max_rss = models.FloatField(null=True)  # Stored as KB
    max_disk_read = models.FloatField(null=True)  # Stored as KB
    max_disk_write = models.FloatField(null=True)  # Stored as KB
    reserved_time = models.DurationField(null=True, blank=True)

    @property
    def io_throughput(self):
        if not self.elapsed_time or not self.max_disk_read or not self.max_disk_write:
            return None
        elapsed_seconds = self.elapsed_time.total_seconds()
        if elapsed_seconds == 0:
            return None
        return (self.max_disk_read + self.max_disk_write) / elapsed_seconds

    class Meta:
        db_table = 'performance_metrics'

    def __str__(self):
        return (
            f"PerformanceMetrics(slurm_job_id={self.slurm_job_id}, "
            f"elapsed_time={self.elapsed_time}, num_cpus={self.num_cpus}, "
            f"max_rss={self.max_rss} KB, max_disk_read={self.max_disk_read} KB, "
            f"max_disk_write={self.max_disk_write} KB, io_throughput={self.io_throughput} K/s)"
        )
