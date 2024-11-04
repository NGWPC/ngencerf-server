from django.contrib.auth import get_user_model
from django.db import models

from calibration.models.base_model import BaseModel


class CalibrationRun(BaseModel):
    is_active = models.BooleanField(null=False, default=True)
    gage = models.ForeignKey('Gage', null=True, on_delete=models.RESTRICT)
    job_genesis = models.CharField(max_length=20, null=False)
    job_data_dir = models.CharField(max_length=255, null=False)
    optimization = models.ForeignKey('Optimization', null=True, on_delete=models.RESTRICT)
    module_output_variable = models.ForeignKey('ModuleOutputVariable', null=True, on_delete=models.RESTRICT)
    run_date = models.DateTimeField(null=True)
    objective_function = models.ForeignKey('Metric', null=True, on_delete=models.RESTRICT)
    time_range_start = models.DateTimeField(null=True)
    time_range_end = models.DateTimeField(null=True)
    calibration_start_period = models.DateTimeField(null=True)
    calibration_end_period = models.DateTimeField(null=True)
    calibration_eval_start_period = models.DateTimeField(null=True)
    calibration_eval_end_period = models.DateTimeField(null=True)
    validation_start_period = models.DateTimeField(null=True)
    validation_end_period = models.DateTimeField(null=True)
    validation_eval_start_period = models.DateTimeField(null=True)
    validation_eval_end_period = models.DateTimeField(null=True)
    owner = models.ForeignKey(get_user_model(), null=False, on_delete=models.RESTRICT, db_index=True)
    use_sloth = models.BooleanField(null=False, default=False)
    streamflow_threshold = models.FloatField(null=True)
    peak_flow_threshold = models.FloatField(null=True)
    geopackage_source = models.ForeignKey('GeopackageSource', null=True, on_delete=models.RESTRICT)
    geopackage_hydrofabric_file_path = models.TextField(null=True)
    forcing_hydrofabric_dir_path = models.TextField(null=True)
    forcing_source = models.ForeignKey('ForcingSource', null=True, on_delete=models.RESTRICT)
    observational_hydrofabric_file_path = models.TextField(null=True)
    observational_source = models.ForeignKey('ObservationalSource', null=True, on_delete=models.RESTRICT)
    user_parameter_filename = models.TextField(null=True)
    realization_file_path = models.TextField(null=True)
    status = models.ForeignKey('Status', null=False, on_delete=models.RESTRICT, db_index=True)
    user_formulation_name = models.CharField(max_length=50, null=True)
    save_plot_iteration_frequency = models.PositiveIntegerField(null=True)
    save_output_iteration = models.BooleanField(default=False)
    automatic_validation = models.BooleanField(null=False, default=False)
    ngen_commit_hash = models.CharField(max_length=50, null=True)
    ngen_cal_commit_hash = models.CharField(max_length=50, null=True)
    is_deleted = models.BooleanField(default=False)
    slurm_job_id = models.IntegerField(null=True)
    performance_metrics = models.ForeignKey('PerformanceMetrics', null=True, on_delete=models.RESTRICT)

    class Meta:
        db_table = 'calibration_run'

    def __str__(self):
        gage_info = f"Gage: {self.gage.gage_id}" if self.gage else "No Gage"
        return (
            f"CalibrationRun {self.id}, {gage_info}, "
            f"owner: {self.owner.username}, "  # type: ignore[attr-defined]  # Suppress PyCharm warning for unresolved attribute
            f"job_data_directory: {self.job_data_dir},"
            f"geopackage_hydrofabric_file_path: {self.geopackage_hydrofabric_file_path}, "
            f"forcing_hydrofabric_dir_path: {self.forcing_hydrofabric_dir_path}, "
            f"observational_hydrofabric_file_path: {self.observational_hydrofabric_file_path}, "
            f"status.name: {self.status.name}, "
            f"is_deleted: {self.is_deleted}"
        )
