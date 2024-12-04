from django.db import models
from django.db.models import ExpressionWrapper, FloatField, Value, F, Func
from django.db.models.functions import Coalesce, NullIf, Cast

from calibration.models.base_model import BaseModel


# Custom PostgreSQL function for extracting seconds from interval
class ExtractEpoch(Func):
    function = 'EXTRACT'
    template = '%(function)s(EPOCH FROM %(expressions)s)'
    output_field = FloatField()


class PerformanceMetrics(BaseModel):
    slurm_job_id = models.CharField(max_length=50, null=False)
    elapsed_time = models.DurationField(null=False)
    num_cpus = models.IntegerField(null=False)
    cpu_time = models.DurationField(null=False)
    max_rss = models.IntegerField(null=True)  # Stored as KB
    max_disk_read = models.IntegerField(null=True)  # Stored as KB
    max_disk_write = models.IntegerField(null=True)  # Stored as KB
    reserved_time = models.DurationField(null=True, blank=True)

    # io_throughput as a generated field
    io_throughput = models.GeneratedField(
        expression=ExpressionWrapper(
            (Coalesce(F('max_disk_read'), Value(0)) + Coalesce(F('max_disk_write'), Value(0))) /
            NullIf(ExtractEpoch(F('elapsed_time')), 0),  # Convert elapsed_time to seconds
            output_field=FloatField(),
        ),
        output_field=FloatField(),  # Specifies the type of the generated field
        db_persist=True,  # Persist the computed value in the database
    )

    class Meta:
        db_table = 'performance_metrics'
