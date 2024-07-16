from django.contrib.auth import get_user_model
from django.db import models

from calibration.models.status import Status
from calibration.models.base_model import BaseModel
from calibration.models.gage import Gage
from calibration.models.module_output_variable import ModuleOutputVariable
from calibration.models.optimization import Optimization


class CalibrationRun(BaseModel):
    is_active = models.BooleanField(null=False, default=True)
    gage = models.ForeignKey(Gage, null=True, on_delete=models.SET_NULL)
    optimization = models.ForeignKey(Optimization, null=True, on_delete=models.SET_NULL)
    module_output_variable = models.ForeignKey(ModuleOutputVariable, null=True, on_delete=models.SET_NULL)
    run_date = models.DateTimeField(null=True)
    time_range_start = models.DateTimeField(null=True)
    time_range_end = models.DateTimeField(null=True)
    calibration_start_period = models.DateTimeField(null=True)
    calibration_end_period = models.DateTimeField(null=True)
    calibration_eval_start_period = models.DateTimeField(null=True)
    calibration_eval_end_period = models.DateTimeField(null=True)
    # This should be a required field (null=FALSE), but we'll leave it as optional for now
    owner = models.ForeignKey(get_user_model(), null=True, on_delete=models.SET_NULL)
    hydrofabric_gpkg_path = models.TextField(null=True)
    forcing_path = models.TextField()
    forcing_user_filename = models.TextField(null=True)
    forcing_source = models.TextField()
    observational_path = models.TextField(null=True)
    status = models.ForeignKey(Status, null=False, on_delete=models.CASCADE)
    seed = models.IntegerField(null=True)
    formulation_name = models.TextField(null=True)
    plot_frequency = models.IntegerField(null=True)
    run_type = models.TextField(null=True)
    ngen_commit_hash = models.BinaryField(null=True)

    class Meta:
        db_table = 'calibration_run'
