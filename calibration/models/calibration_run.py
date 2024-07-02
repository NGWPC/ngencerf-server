from django.db import models

from calibration.models.base_model import BaseModel
from calibration.models.gage import Gage
from calibration.models.module_output_variable import ModuleOutputVariable
from calibration.models.optimization import Optimization
from calibration.models.status import Status


class CalibrationRun(BaseModel):
    is_active = models.BooleanField()
    gage = models.ForeignKey(Gage, null=True, on_delete=models.SET_NULL)
    optimization = models.OneToOneField(Optimization, null=True, on_delete=models.SET_NULL)
    module_output_variable = models.ForeignKey(ModuleOutputVariable, null=True, on_delete=models.SET_NULL)
    time_range_start = models.DateTimeField(null=True)
    time_range_end = models.DateTimeField(null=True)
    calibration_start_period = models.DateTimeField(null=True)
    calibration_end_period = models.DateTimeField(null=True)
    calibration_eval_start_period = models.DateTimeField(null=True)
    calibration_eval_end_period = models.DateTimeField(null=True)
    hydrofabric_gpkg_path = models.TextField(null=True)
    forcing_path = models.TextField()
    forcing_user_filename = models.TextField(null=True)
    forcing_source = models.TextField()
    observational_path = models.TextField(null=True)
    status = models.OneToOneField(Status, null=True, on_delete=models.SET_NULL)
    seed = models.IntegerField(null=True)
    formulation_name = models.TextField(null=True)
    plot_frequency = models.IntegerField(null=True)
    run_type = models.TextField(null=True)
    ngen_commit_hash = models.BinaryField(null=True)


    class Meta:
        db_table = 'calibration_run'
