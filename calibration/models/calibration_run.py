from django.contrib.auth import get_user_model
from django.db import models

from calibration.models.status import Status
from calibration.models.base_model import BaseModel
from calibration.models.gage import Gage
from calibration.models.module_output_variable import ModuleOutputVariable
from calibration.models.optimization import Optimization


class CalibrationRun(BaseModel):
    is_active = models.BooleanField(null=False, default=True)
    gage = models.ForeignKey(Gage, null=True, on_delete=models.RESTRICT)
    optimization = models.ForeignKey(Optimization, null=True, on_delete=models.RESTRICT)
    module_output_variable = models.ForeignKey(ModuleOutputVariable, null=True, on_delete=models.RESTRICT)
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
    # This should be a required field (null=FALSE), but we'll leave it as optional for now
    owner = models.ForeignKey(get_user_model(), null=True, on_delete=models.RESTRICT)
    use_sloth = models.BooleanField(null=False, default=False)
    streamflow_threshold = models.FloatField(null=True)
    hydrofabric_gpkg_path = models.TextField(null=True, blank=False)
    forcing_path = models.TextField(null=True, blank=False)
    forcing_user_filename = models.TextField(null=True, blank=False)
    forcing_source = models.TextField(null=True, blank=False)
    observational_path = models.TextField(null=True, blank=False)
    status = models.ForeignKey(Status, null=False, on_delete=models.RESTRICT)
    user_formulation_name = models.TextField(null=True, blank=False)
    ngen_formulation_name = models.TextField(null=True, blank=False)
    plot_frequency = models.IntegerField(null=True)
    run_type = models.TextField(null=True, blank=False)
    ngen_commit_hash = models.BinaryField(null=True)

    class Meta:
        db_table = 'calibration_run'
