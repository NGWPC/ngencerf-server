from django.db import models
from calibration.models.base_model import BaseModel


class PerformanceMetrics(BaseModel):
    job_id = models.CharField(max_length=50, null=False)
    elapsed_time = models.DurationField(null=False)
    num_cpus = models.IntegerField(null=False)
    cpu_time = models.DurationField(null=False)
    max_rss = models.CharField(max_length=50, null=False)
    max_disk_read = models.CharField(max_length=50, null=False)
    max_disk_write = models.CharField(max_length=50, null=False)
    reserved_time = models.DurationField(null=True, blank=True)

    class Meta:
        db_table = 'performance_metrics'
