from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.gage import Gage
from calibration.models.module_output_variable import ModuleOutputVariable
from calibration.models.optimization import Optimization
from calibration.models.status import Status


class CalibrationRun(BaseModel):
    description = models.TextField()
    is_active = models.BooleanField()
    gage_pk = models.ForeignKey(Gage, null=True, on_delete=models.SET_NULL)
    optimization_pk = models.ForeignKey(Optimization, null=True, on_delete=models.SET_NULL)
    module_output_variable_pk = models.ForeignKey(ModuleOutputVariable, null=True, on_delete=models.SET_NULL)
    time_range_start = models.DateTimeField()
    time_range_end = models.DateTimeField()
    calibration_start_period = models.DateTimeField()
    calibration_end_period = models.DateTimeField()
    calibration_eval_start_period = models.DateTimeField()
    calibration_eval_end_period = models.DateTimeField()
    hydrofabric_gpkg_path = models.TextField()
    forcing_path = models.TextField()
    forcing_user_filename = models.TextField()
    forcing_source = models.TextField()
    observational_path = models.TextField()
    status_pk = models.ForeignKey(Status, null=True, on_delete=models.SET_NULL)
    seed = models.IntegerField()
    formulation_name = models.TextField()
    plot_frequency = models.IntegerField()
    run_type = models.TextField()
    ngen_commit_hash = models.BinaryField


    class Meta:
        db_table = 'calibration_run'
