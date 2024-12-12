from django.db import models
from django.db.models import ExpressionWrapper, FloatField, Value, F, Func, When, Case
from django.db.models.functions import Coalesce, NullIf

from calibration.models.base_model import BaseModel


# Custom PostgreSQL function for extracting seconds from interval
class ExtractEpoch(Func):
    function = 'EXTRACT'
    template = '%(function)s(EPOCH FROM %(expressions)s)'
    output_field = FloatField()


class PerformanceMetrics(BaseModel):
    slurm_job_id = models.CharField(max_length=50, null=True)
    elapsed_time = models.DurationField(null=False)
    num_cpus = models.IntegerField(null=True)
    cpu_time = models.DurationField(null=True)
    max_rss = models.FloatField(null=True)  # Stored as KB
    max_disk_read = models.FloatField(null=True)  # Stored as KB
    max_disk_write = models.FloatField(null=True)  # Stored as KB
    reserved_time = models.DurationField(null=True, blank=True)

    # io_throughput as a generated field
    io_throughput = models.GeneratedField(
        expression=Case(
            # If any required field is NULL, set io_throughput to NULL
            When(
                models.Q(max_disk_read__isnull=True) |
                models.Q(max_disk_write__isnull=True) |
                models.Q(elapsed_time__isnull=True),
                then=Value(None)
            ),
            # Otherwise, calculate io_throughput
            default=ExpressionWrapper(
                (Coalesce(F('max_disk_read'), Value(0)) + Coalesce(F('max_disk_write'), Value(0))) /
                NullIf(ExtractEpoch(F('elapsed_time')), 0),  # Avoid division by zero
                output_field=FloatField(),
            ),
            output_field=FloatField(),
        ),
        output_field=FloatField(),  # Specifies the type of the generated field
        db_persist=True,  # Persist the computed value in the database
    )

    class Meta:
        db_table = 'performance_metrics'

    def __str__(self):
        return (
            f"PerformanceMetrics(slurm_job_id={self.slurm_job_id}, "
            f"elapsed_time={self.elapsed_time}, num_cpus={self.num_cpus}, "
            f"max_rss={self.max_rss} KB, max_disk_read={self.max_disk_read} KB, "
            f"max_disk_write={self.max_disk_write} KB, io_throughput={self.io_throughput} K/s)"
        )
