from django.db import models
from calibration.models.base_model import BaseModel


class PerformanceMetrics(BaseModel):
    slurm_job_id = models.CharField(max_length=50, null=False)
    elapsed_time = models.DurationField(null=False)
    num_cpus = models.IntegerField(null=False)
    cpu_time = models.DurationField(null=False)
    max_rss = models.CharField(max_length=50, null=False)
    max_disk_read = models.CharField(max_length=50, null=False)
    max_disk_write = models.CharField(max_length=50, null=False)
    reserved_time = models.DurationField(null=True, blank=True)

    class Meta:
        db_table = 'performance_metrics'

    @property
    def io_throughput(self):
        """
        Computes the I/O Throughput defined as (max_disk_read + max_disk_write) / elapsed_time
        Returns None if any of the necessary fields are missing or invalid.
        """
        try:
            # Convert max_disk_read and max_disk_write to float (assuming they're in KB)
            max_disk_read = float(self.max_disk_read.replace('K', '').replace('M', 'e3').replace('G', 'e6'))
            max_disk_write = float(self.max_disk_write.replace('K', '').replace('M', 'e3').replace('G', 'e6'))

            # Compute total disk I/O
            total_io = max_disk_read + max_disk_write

            # Compute elapsed time in seconds
            elapsed_seconds = self.elapsed_time.total_seconds()

            # Compute throughput (I/O per second)
            if elapsed_seconds > 0:
                return total_io / elapsed_seconds
            else:
                return None
        except (ValueError, AttributeError, TypeError):
            # Return None if any field is missing or invalid
            return None
