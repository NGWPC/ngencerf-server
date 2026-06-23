from django.conf import settings
from django.db import models
from dateutil.relativedelta import relativedelta

from calibration.models.base_run import BaseRun


class CalibrationRun(BaseRun):  # Inherit from BaseRun
    is_active = models.BooleanField(null=False, default=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=False, on_delete=models.RESTRICT, db_index=True)
    gage = models.ForeignKey('Gage', null=True, on_delete=models.RESTRICT)
    job_genesis = models.CharField(max_length=20, null=False)
    job_data_dir = models.CharField(max_length=255, null=False)
    optimization = models.ForeignKey('Optimization', null=True, on_delete=models.RESTRICT)
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
    warmup_duration = models.IntegerField(null=True)
    calibration_duration = models.IntegerField(null=True)
    validation_window = models.BooleanField(null=True,default=True)
    validation_duration = models.IntegerField(null=True)
    use_sloth = models.BooleanField(null=False, default=False)
    streamflow_threshold = models.FloatField(null=True)
    peak_flow_threshold = models.FloatField(null=True)
    geopackage_source = models.ForeignKey('GeopackageSource', null=True, on_delete=models.RESTRICT)
    forcing_source = models.ForeignKey('ForcingSource', null=True, on_delete=models.RESTRICT, related_name='+', related_query_name='+')
    observational_source = models.ForeignKey('ObservationalSource', null=True, on_delete=models.RESTRICT)
    user_parameter_filename = models.TextField(null=True)
    realization_file_path = models.TextField(null=True)
    status = models.ForeignKey('Status', null=False, on_delete=models.RESTRICT, db_index=True)
    job_name = models.CharField(max_length=100, null=True)
    save_plot_iteration_frequency = models.PositiveIntegerField(null=True)
    save_output_iteration = models.BooleanField(default=False)
    automatic_validation = models.BooleanField(null=False, default=False)
    is_archived = models.BooleanField(default=False)
    archive_status_updated_at = models.DateTimeField(null=True)
    is_locked = models.BooleanField(default=False)
    mpi_nprocs = models.IntegerField(null=True)
    next_worker_number = models.PositiveIntegerField(default=1)
    num_catchments = models.IntegerField(null=True)
    node_type = models.CharField(max_length=20, null=True)

    class Meta:
        db_table = 'calibration_run'
        indexes = [
            models.Index(fields=['owner', 'status', 'is_archived'], name='idx_run_owner_status_archived'),
            models.Index(fields=['owner', 'is_archived'], name='idx_run_owner_archived'),
            models.Index(fields=['owner', 'is_archived', 'status', '-id'], name='idx_run_owner_arch_stat_id'),
            models.Index(fields=['owner', 'is_archived', 'created_at'], name='idx_run_owner_arch_created'),
        ]

    def __str__(self):
        gage_info = f"Gage: {self.gage.gage_id}" if self.gage else "No Gage"
        return (
            f"CalibrationRun {self.id}, {gage_info}, "
            f"owner: {self.owner.username}, "  # type: ignore[attr-defined]  # Suppress PyCharm warning for unresolved attribute
            f"job_data_directory: {self.job_data_dir},"
            f"objective_function.name: {self.objective_function.name if self.objective_function else 'None'}, "
            f"optimization.name: {self.optimization.name if self.optimization else 'None'}, "
            f"status.name: {self.status.name}, "
            f"is_archived: {self.is_archived}"
        )

    @property
    def calibration_end_period(self):
        # Simulation ends when calibration ends, also at 23:00
        return self.calibration_eval_end_period

    @property
    def calibration_eval_start_period(self):
        # Calibration starts at 00:00, following warmup duration
        if self.calibration_start_period is None or self.warmup_duration is None:
            return None
        return self.calibration_start_period + relativedelta(months=self.warmup_duration)
    
    @property
    def calibration_eval_end_period(self):
        # Calibration ends at 23:00, following calibration duration
        if self.calibration_start_period is None or self.warmup_duration is None or self.calibration_duration is None:
            return None
        start = self.calibration_start_period + relativedelta(months=self.warmup_duration)
        return start + relativedelta(months=self.calibration_duration) - relativedelta(hours=1)

    @property
    def validation_start_period(self):
        if self.calibration_start_period is None:
            return None
        if self.validation_window:
            # Both simulations start at the same time, 00:00
            return self.calibration_start_period
        else:
            # Simulation starts at 00:00, preceding warmup duration
            if self.validation_eval_start_period is None or self.warmup_duration is None:
                return None
            return self.validation_eval_start_period - relativedelta(months=self.warmup_duration)

    @property
    def validation_end_period(self):
        if self.validation_window:
            # Simulation ends when validation ends, at 23:00
            return self.validation_eval_end_period
        else:
            # Simulation ends when calibration ends, at 23:00
            return self.calibration_eval_end_period

    @property
    def validation_eval_start_period(self):
        if self.calibration_start_period is None:
            return None
        if self.validation_window:
            # Validation starts at 00:00, an hour after calibration ends
            if self.calibration_duration is None or self.warmup_duration is None:
                return None
            cal_start = self.calibration_start_period + relativedelta(months=self.warmup_duration)
            cal_end = cal_start + relativedelta(months=self.calibration_duration) - relativedelta(hours=1)
            return cal_end + relativedelta(hours=1)
        else:
            # Validation starts at 00:00, preceding validation duration
            if self.validation_duration is None or self.warmup_duration is None:
                return None
            return self.calibration_start_period + relativedelta(months=self.warmup_duration) - relativedelta(months=self.validation_duration)
    
    @property
    def validation_eval_end_period(self):
        if self.calibration_start_period is None:
            return None
        if self.validation_window:
            # Validation ends at 23:00, following validation duration
            if self.calibration_duration is None or self.validation_duration is None or self.warmup_duration is None:
                return None
            cal_start = self.calibration_start_period + relativedelta(months=self.warmup_duration)
            cal_end = cal_start + relativedelta(months=self.calibration_duration) - relativedelta(hours=1)
            return cal_end + relativedelta(months=self.validation_duration)
        else:
            # Validation ends at 23:00, an hour before calibration starts
            if self.warmup_duration is None:
                return None
            return self.calibration_start_period + relativedelta(months=self.warmup_duration) - relativedelta(hours=1)