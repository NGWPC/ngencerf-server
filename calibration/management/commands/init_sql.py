import json
from pprint import pprint

from django.core.management.base import BaseCommand

from calibration.models import Module, ModuleGroup, Domain, ObservationalSource, ModuleInputVariable, ModuleOutputVariable, \
    Optimization, Metric, Status, NgenCalFormulation


class Command(BaseCommand):
    help = "Initializes static tables"

    def handle(self, *args, **options):
        self.stdout.write('Initializing status tables')

        self.define_modules_and_groups()
        self.define_domains()
        self.define_observational_source()
        self.define_module_input_variable()
        self.define_module_output_variable()
        self.define_optimization()
        self.define_metric()
        self.define_status()
        self.define_ngen_formulations()

    def define_modules_and_groups(self):
        Module.objects.all().delete()
        ModuleGroup.objects.all().delete()

        group_inject = ModuleGroup(name="Inject", is_active=True, description='Need description')
        group_inject.save()
        group_glacier = ModuleGroup(name="Glacier", is_active=True, description='Need description')
        group_glacier.save()
        group_snowmelt = ModuleGroup(name="Snowmelt", is_active=True, description='Need description')
        group_snowmelt.save()
        group_evapotranspiration = ModuleGroup(name="Evapotranspiration", is_active=True, description='Need description')
        group_evapotranspiration.save()
        group_rainfall = ModuleGroup(name="Rainfall Runoff", is_active=True, description='Need description')
        group_rainfall.save()
        group_soil = ModuleGroup(name="Soil Moisture", is_active=True, description='Need description')
        group_soil.save()
        group_routing = ModuleGroup(name="Routing", is_active=True, description='Need description')
        group_routing.save()
        group_coastal = ModuleGroup(name="Coastal", is_active=True, description='Need description')
        group_coastal.save()

        self.define_module(Module(name="GC2D", is_active=True, ngen_cal_active=True, description='Need description'),
                           [group_glacier])
        self.define_module(Module(name="Noah-OWP-Modular", is_active=True, ngen_cal_active=True, description='Need description'),
                           [group_snowmelt, group_evapotranspiration])
        self.define_module(Module(name="Snow-17", is_active=True, ngen_cal_active=True, description='Need description'),
                           [group_snowmelt])
        self.define_module(Module(name="UEB", is_active=True, ngen_cal_active=True, description='Need description'),
                           [group_snowmelt, group_evapotranspiration])
        self.define_module(Module(name="CFE-S", is_active=True, ngen_cal_active=True, description='Need description'),
                           [group_rainfall])
        self.define_module(Module(name="CFE-X", is_active=True, ngen_cal_active=True, description='Need description'),
                           [group_rainfall])
        self.define_module(Module(name="PET", is_active=True, ngen_cal_active=True, description='Need description'),
                           [group_evapotranspiration])
        self.define_module(Module(name="TopModel", is_active=True, ngen_cal_active=True, description='Need description'),
                           [group_rainfall])
        self.define_module(Module(name="Sac-SMA", is_active=True, ngen_cal_active=True, description='Need description'),
                           [group_rainfall])
        self.define_module(Module(name="LASAM", is_active=True, ngen_cal_active=True, description='Need description'),
                           [group_rainfall])
        self.define_module(Module(name="SMP", is_active=True, ngen_cal_active=True, description='Need description'), [group_soil])
        self.define_module(Module(name="SFT", is_active=True, ngen_cal_active=True, description='Need description'),
                           [group_snowmelt])
        self.define_module(Module(name="T-Route", is_active=True, ngen_cal_active=True, description='Need description'),
                           [group_routing])
        self.define_module(Module(name="SCHISM", is_active=True, ngen_cal_active=True, description='Need description'),
                           [group_coastal])
        self.define_module(Module(name="SFINCS", is_active=True, ngen_cal_active=True, description='Need description'),
                           [group_coastal])
        self.define_module(Module(name="Sloth", is_active=True, ngen_cal_active=True, description='Need description'),
                           [group_inject])

    def define_module(self, module, groups):
        module.save()
        module.groups.add(*groups)

    def define_domains(self):
        Domain.objects.all().delete()

        Domain(name="Alaska", is_active=True, description='Need description').save()
        Domain(name="Hawaii", is_active=True, description='Need description').save()
        Domain(name="CONUS", is_active=True, description='Need description').save()
        Domain(name="Puerto Rico, including US Virgin Island", is_active=True, description='Need description').save()

    def define_observational_source(self):
        ObservationalSource.objects.all().delete()

        ObservationalSource(name="USGS", is_active=True, description='Need description').save()
        ObservationalSource(name="USACE", is_active=True, description='Need description').save()
        ObservationalSource(name="BOR", is_active=True, description='Need description').save()
        ObservationalSource(name="ENV", is_active=True, description='Need description').save()
        ObservationalSource(name="State Agency", is_active=True, description='Need description').save()
        ObservationalSource(name="RFC", is_active=True, description='Need description').save()

    def define_module_input_variable(self):
        ModuleInputVariable.objects.all().delete()

        self.save_module_input_variable(ModuleInputVariable(name="SFCTMP", is_active=True, description='Need description'),
                                        'Noah-OWP-Modular')
        self.save_module_input_variable(ModuleInputVariable(name="SOLDN", is_active=True, description='Need description'),
                                        'Noah-OWP-Modular')
        self.save_module_input_variable(ModuleInputVariable(name="LWDN", is_active=True, description='Need description'),
                                        'Noah-OWP-Modular')
        self.save_module_input_variable(ModuleInputVariable(name="UU", is_active=True, description='Need description'),
                                        'Noah-OWP-Modular')
        self.save_module_input_variable(ModuleInputVariable(name="VV", is_active=True, description='Need description'),
                                        'Noah-OWP-Modular')
        self.save_module_input_variable(ModuleInputVariable(name="Q2", is_active=True, description='Need description'),
                                        'Noah-OWP-Modular')
        self.save_module_input_variable(ModuleInputVariable(name="PRCPNONC", is_active=True, description='Need description'),
                                        'Noah-OWP-Modular')
        self.save_module_input_variable(
            ModuleInputVariable(name="atmosphere_water__liquid_equivalent_precipitation_rate", is_active=True,
                                description='Need description'), 'CFE-S')
        self.save_module_input_variable(
            ModuleInputVariable(name="water_potential_evaporation_flux", is_active=True, description='Need description'), 'CFE-S')
        self.save_module_input_variable(
            ModuleInputVariable(name="ice_fraction_schaake", is_active=True, description='Need description'), 'CFE-S')
        self.save_module_input_variable(
            ModuleInputVariable(name="ice_fraction_xinanjiang", is_active=True, description='Need description'), 'CFE-S')
        self.save_module_input_variable(
            ModuleInputVariable(name="soil_moisture_profile", is_active=True, description='Need description'), 'CFE-S')
        self.save_module_input_variable(
            ModuleInputVariable(name="atmosphere_water__liquid_equivalent_precipitation_rate", is_active=True,
                                description='Need description'), 'CFE-X')
        self.save_module_input_variable(
            ModuleInputVariable(name="water_potential_evaporation_flux", is_active=True, description='Need description'), 'CFE-X')
        self.save_module_input_variable(
            ModuleInputVariable(name="ice_fraction_schaake", is_active=True, description='Need description'), 'CFE-X')
        self.save_module_input_variable(
            ModuleInputVariable(name="ice_fraction_xinanjiang", is_active=True, description='Need description'), 'CFE-X')
        self.save_module_input_variable(
            ModuleInputVariable(name="soil_moisture_profile", is_active=True, description='Need description'), 'CFE-X')
        self.save_module_input_variable(ModuleInputVariable(name="land_surface_water_source__volume_flow_rate", is_active=True,
                                                            description='Need description'), 'T-Route')
        self.save_module_input_variable(ModuleInputVariable(name="upstream_id", is_active=True, description='Need description'),
                                        'T-Route')
        self.save_module_input_variable(ModuleInputVariable(name="upstream_fvd", is_active=True, description='Need description'),
                                        'T-Route')
        self.save_module_input_variable(
            ModuleInputVariable(name="coastal_boundary__depth", is_active=True, description='Need description'), 'T-Route')
        self.save_module_input_variable(
            ModuleInputVariable(name="usgs_gage_observation__volume_flow_rate", is_active=True, description='Need description'),
            'T-Route')
        self.save_module_input_variable(
            ModuleInputVariable(name="reservoir_usgs_gage_observation__volume_flow_rate", is_active=True,
                                description='Need description'), 'T-Route')
        self.save_module_input_variable(
            ModuleInputVariable(name="reservoir_usace_gage_observation__volume_flow_rate", is_active=True,
                                description='Need description'), 'T-Route')
        self.save_module_input_variable(
            ModuleInputVariable(name="rfc_gage_observation__volume_flow_rate", is_active=True, description='Need description'),
            'T-Route')

    def save_module_input_variable(self, module_input_variable, moduleName):
        module_input_variable.module = Module.objects.get(name=moduleName)
        module_input_variable.save()

    def define_module_output_variable(self):
        ModuleOutputVariable.objects.all().delete()

        self.save_module_output_variable(ModuleOutputVariable(name="QINSUR", is_active=True, description='Need description'),
                                         'Noah-OWP-Modular')
        self.save_module_output_variable(ModuleOutputVariable(name="ETRAN", is_active=True, description='Need description'),
                                         'Noah-OWP-Modular')
        self.save_module_output_variable(ModuleOutputVariable(name="QSEVA", is_active=True, description='Need description'),
                                         'Noah-OWP-Modular')
        self.save_module_output_variable(ModuleOutputVariable(name="EVAPOTRANS", is_active=True, description='Need description'),
                                         'Noah-OWP-Modular')
        self.save_module_output_variable(ModuleOutputVariable(name="TG", is_active=True, description='Need description'),
                                         'Noah-OWP-Modular')
        self.save_module_output_variable(ModuleOutputVariable(name="SNEQV", is_active=True, description='Need description'),
                                         'Noah-OWP-Modular')
        self.save_module_output_variable(ModuleOutputVariable(name="TGS", is_active=True, description='Need description'),
                                         'Noah-OWP-Modular')
        self.save_module_output_variable(ModuleOutputVariable(name="RAIN_RATE", is_active=True, description='Need description'),
                                         'CFE-S')
        self.save_module_output_variable(
            ModuleOutputVariable(name="DIRECT_RUNOFF", is_active=True, description='Need description'), 'CFE-S')
        self.save_module_output_variable(ModuleOutputVariable(name="GIUH_RUNOFF", is_active=True, description='Need description'),
                                         'CFE-S')
        self.save_module_output_variable(
            ModuleOutputVariable(name="NASH_LATERAL_RUNOFF", is_active=True, description='Need description'), 'CFE-S')
        self.save_module_output_variable(
            ModuleOutputVariable(name="DEEP_GW_TO_CHANNEL_FLUX", is_active=True, description='Need description'), 'CFE-S')
        self.save_module_output_variable(
            ModuleOutputVariable(name="SOIL_TO_GW_FLUX", is_active=True, description='Need description'), 'CFE-S')
        self.save_module_output_variable(ModuleOutputVariable(name="Q_OUT", is_active=True, description='Need description'),
                                         'CFE-S')
        self.save_module_output_variable(
            ModuleOutputVariable(name="POTENTIAL_ET", is_active=True, description='Need description'), 'CFE-S')
        self.save_module_output_variable(ModuleOutputVariable(name="ACTUAL_ET", is_active=True, description='Need description'),
                                         'CFE-S')
        self.save_module_output_variable(ModuleOutputVariable(name="GW_STORAGE", is_active=True, description='Need description'),
                                         'CFE-S')
        self.save_module_output_variable(
            ModuleOutputVariable(name="SOIL_STORAGE", is_active=True, description='Need description'), 'CFE-S')
        self.save_module_output_variable(
            ModuleOutputVariable(name="SOIL_STORAGE_CHANGE", is_active=True, description='Need description'), 'CFE-S')
        self.save_module_output_variable(
            ModuleOutputVariable(name="SURF_RUNOFF_SCHEME", is_active=True, description='Need description'), 'CFE-S')
        self.save_module_output_variable(ModuleOutputVariable(name="RAIN_RATE", is_active=True, description='Need description'),
                                         'CFE-X')
        self.save_module_output_variable(
            ModuleOutputVariable(name="DIRECT_RUNOFF", is_active=True, description='Need description'), 'CFE-X')
        self.save_module_output_variable(ModuleOutputVariable(name="GIUH_RUNOFF", is_active=True, description='Need description'), 'CFE-X')
        self.save_module_output_variable(
            ModuleOutputVariable(name="NASH_LATERAL_RUNOFF", is_active=True, description='Need description'), 'CFE-X')
        self.save_module_output_variable(
            ModuleOutputVariable(name="DEEP_GW_TO_CHANNEL_FLUX", is_active=True, description='Need description'), 'CFE-X')
        self.save_module_output_variable(
            ModuleOutputVariable(name="SOIL_TO_GW_FLUX", is_active=True, description='Need description'), 'CFE-X')
        self.save_module_output_variable(ModuleOutputVariable(name="Q_OUT", is_active=True, description='Need description'),
                                         'CFE-X')
        self.save_module_output_variable(
            ModuleOutputVariable(name="POTENTIAL_ET", is_active=True, description='Need description'), 'CFE-X')
        self.save_module_output_variable(ModuleOutputVariable(name="ACTUAL_ET", is_active=True, description='Need description'),
                                         'CFE-X')
        self.save_module_output_variable(ModuleOutputVariable(name="GW_STORAGE", is_active=True, description='Need description'),
                                         'CFE-X')
        self.save_module_output_variable(
            ModuleOutputVariable(name="SOIL_STORAGE", is_active=True, description='Need description'), 'CFE-X')
        self.save_module_output_variable(
            ModuleOutputVariable(name="SOIL_STORAGE_CHANGE", is_active=True, description='Need description'), 'CFE-X')
        self.save_module_output_variable(
            ModuleOutputVariable(name="SURF_RUNOFF_SCHEME", is_active=True, description='Need description'), 'CFE-X')
        self.save_module_output_variable(
            ModuleOutputVariable(name="channel_exit_water_x-section__volume_flow_rate", is_active=True,
                                 description='Need description'), 'T-Route')
        self.save_module_output_variable(
            ModuleOutputVariable(name="channel_water_flow__speed", is_active=True, description='Need description'), 'T-Route')
        self.save_module_output_variable(
            ModuleOutputVariable(name="channel_water__mean_dept", is_active=True, description='Need description'), 'T-Route')
        self.save_module_output_variable(
            ModuleOutputVariable(name="lake_water~incoming__volume_flow_rate", is_active=True, description='Need description'),
            'T-Route')
        self.save_module_output_variable(
            ModuleOutputVariable(name="lake_water~outgoing__volume_flow_rate", is_active=True, description='Need description'),
            'T-Route')
        self.save_module_output_variable(
            ModuleOutputVariable(name="lake_surface__elevation", is_active=True, description='Need description'), 'T-Route')

    def save_module_output_variable(self, module_output_variable, moduleName):
        module_output_variable.module = Module.objects.get(name=moduleName)
        module_output_variable.save()

    def define_optimization(self):
        Optimization.objects.all().delete()

        Optimization(name="DDS", is_active=True, description='Need description').save()
        Optimization(name="PWO", is_active=True, description='Need description').save()
        Optimization(name="Grey Wolf", is_active=True, description='Need description').save()

    def define_metric(self):
        Metric.objects.all().delete()

        Metric(name="Cor", is_active=True, description='Pearson Correlation').save()
        Metric(name="MAE", is_active=True, description='Mean Absolute Error').save()
        Metric(name="RMSE", is_active=True, description='Root Mean Square Error').save()
        Metric(name="RSR", is_active=True, description='Ratio of RMSE to standard deviation of observation').save()
        Metric(name="PBIAS", is_active=True, description='Percent Bias').save()
        Metric(name="KGE", is_active=True, description='Kling-Gupta Efficiency').save()
        Metric(name="NSE", is_active=True, description='Nash-Sutcliffe-Efficiency').save()
        Metric(name="LogNSE", is_active=True, description='NSE of Logarithmic values').save()
        Metric(name="PoD", is_active=True, description='Probability of Detection').save()
        Metric(name="CSI", is_active=True, description='Critical Success Index').save()
        Metric(name="FAR", is_active=True, description='False Alarm Ratio').save()
        Metric(name="HFDC", is_active=True, description='Percent bias of high flow segment of flow duration curve').save()
        Metric(name="LFDC", is_active=True, description='Percent bias of low flow segment of flow duration curve').save()
        Metric(name="PKBIAS", is_active=True, description='Absolute Peak Flow Bias').save()
        Metric(name="pPKBIAS", is_active=True, description='Percent Peak Flow Bias').save()
        Metric(name="PKTE", is_active=True, description='Peak Flow Timing Error').save()
        Metric(name="EVBIAS", is_active=True, description='Event Volume Bias').save()

    def define_status(self):
        Status.objects.all().delete()

        Status(name="Saved", is_active=True, description='Need description').save()
        Status(name="Ready", is_active=True, description='Need description').save()
        Status(name="Running", is_active=True, description='Need description').save()
        Status(name="Done", is_active=True, description='Need description').save()
        Status(name="Cancelled", is_active=True, description='Need description').save()

    def define_ngen_formulations(self):
        NgenCalFormulation.objects.all().delete()

        NgenCalFormulation(name="cfe_noah", modules=json.dumps(["CFE-S", "Noah-OWP-Modular"]), description='Need description').save()
        NgenCalFormulation(name="cfe_noah_sft", modules=json.dumps(["CFE-S", "Noah-OWP-Modular", "SFT", "SMP"]), description='Need description').save()
        NgenCalFormulation(name="cfe_xaj_noah", modules=json.dumps(["CFE-X", "Noah-OWP-Modular"]), description='Need description').save()
        NgenCalFormulation(name="cfe_xaj_noah_sft", modules=json.dumps(["CFE-X", "Noah-OWP-Modular", "SFT", "SMP"]), description='Need description').save()
        NgenCalFormulation(name="lasam_noah_sft", modules=json.dumps(["LASAM", "Noah-OWP-Modular", "SFT", "SMP"]), description='Need description').save()
        NgenCalFormulation(name="topmodel_noah", modules=json.dumps(["TopModel", "Noah-OWP-Modular"]), description='Need description').save()
