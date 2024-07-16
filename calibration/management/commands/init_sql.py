import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from calibration.enums import StatusEnum, DataTypeEnum
from calibration.models import Domain, ObservationalSource, Optimization, Metric, NgenCalFormulation, MetricInput, OptimizationInput
from calibration.models.status import Status


class Command(BaseCommand):
    help = "Initializes static tables"

    # Don't turn this flag on unless you know what you're doing.  These values are foreign keys in other tables.
    # If they are deleted, you'll lose the relationship.
    # You can re-run this script with DELETE_FLAG=False, and any new values will be added, without touching the existing values.
    DELETE_FLAG = False

    # need to get a user that is guaranteed to be there, such as admin
    user = get_user_model().objects.get(username='admin')
    print('user:', user)

    def handle(self, *args, **options):
        self.stdout.write('Initializing static tables')

        # self.define_modules_and_groups()
        self.define_domains()
        self.define_observational_source()
        self.define_optimization()
        self.define_metric()
        self.define_status()
        self.define_ngen_formulations()

    def define_domains(self):
        if self.DELETE_FLAG:
            Domain.objects.all().delete()

        values = [{"name": "Alaska", "description": "Alaska"},
                  {"name": "Hawaii", "description": "Hawaii"},
                  {"name": "CONUS", "description": "Continental United Status"},
                  {"name": "Puerto Rico, including US Virgin Island", "description": "Puerto Rico, including US Virgin Island"}
                  ]

        for v in values:
            Domain.objects.get_or_create(name=v.get('name'), is_active=True, description=v.get('description'),
                                         created_by=self.user)

    def define_observational_source(self):
        if self.DELETE_FLAG:
            ObservationalSource.objects.all().delete()

        values = [{"name": "USGS", "description": "Needs description"},
                  {"name": "USACE", "description": "Needs description"},
                  {"name": "BOR", "description": "Needs description"},
                  {"name": "ENV", "description": "Needs description"},
                  {"name": "State Agency", "description": "Needs description"},
                  {"name": "RFC", "description": "Needs description"}
                  ]

        for v in values:
            ObservationalSource.objects.get_or_create(name=v.get('name'), is_active=True, description=v.get('description'),
                                                      created_by=self.user)

    def define_optimization(self):
        if self.DELETE_FLAG:
            Optimization.objects.all().delete()
            OptimizationInput.objects.all().delete()

        values = [{"name": "DDS", "description": "Dynamically Dimensioned Search",
                   "inputs": [{"name": "r", "description": "Sample region size", "data_type": DataTypeEnum.DOUBLE}]},
                  {"name": "PSO", "description": "Particle Swarm Optimization",
                   "inputs": [{"name": "swarm_size", "description": "Swarm size", "data_type": DataTypeEnum.INTEGER},
                              {"name": "c1", "description": "Acceleration coefficient c1", "data_type": DataTypeEnum.DOUBLE},
                              {"name": "c2", "description": "Acceleration coefficient c2 ", "data_type": DataTypeEnum.DOUBLE},
                              {"name": "w", "description": "Inertia weight", "data_type": DataTypeEnum.DOUBLE}]},
                  {"name": "GWO", "description": "Grey Wolf Optimization",
                   "inputs": [{"name": "swarm_size", "description": "Swarm size", "data_type": DataTypeEnum.INTEGER}]},
                  ]

        for v in values:
            optimization, created = Optimization.objects.get_or_create(name=v.get('name'), is_active=True, description=v.get('description'),
                                                                       created_by=self.user)

            for i in v.get('inputs'):
                OptimizationInput.objects.get_or_create(name=i.get('name'), is_active=True, description=i.get('description'),
                                                        data_type=i.get('data_type'), optimization=optimization,
                                                        created_by=self.user)

    def define_metric(self):
        if self.DELETE_FLAG:
            Metric.objects.all().delete()
            MetricInput.objects.all().delete()

        values = [{"name": "Cor", "description": "Pearson Correlation", "inputs": []},
                  {"name": "MAE", "description": "Mean Absolute Error", "inputs": []},
                  {"name": "RMSE", "description": "Root Mean Square Error", "inputs": [
                      {"name": "root", "description": "True to compute RMSE, False to compute MSE", "data_type": DataTypeEnum.BOOLEAN,
                       "default": "True"}]},
                  {"name": "RSR", "description": "Ratio of RMSE to standard deviation of observation", "inputs": []},
                  {"name": "PBIAS", "description": "Percent Bias", "inputs": []},
                  {"name": "KGE", "description": "Kling-Gupta Efficiency",
                   "inputs": [{"name": "r", "description": "Correlation scaling factor", "data_type": DataTypeEnum.DOUBLE, "default": "1.0"},
                              {"name": "a", "description": "Relative variability scaling factor", "data_type": DataTypeEnum.DOUBLE, "default": "1.0"},
                              {"name": "b", "description": "Relative mean scaling factor", "data_type": DataTypeEnum.DOUBLE, "default": "1.0"}]},
                  {"name": "NSE", "description": "Nash-Sutcliffe-Efficiency", "inputs": [
                      {"name": "fun", "description": "Transformation function applied to y_true and y_pred", "data_type": DataTypeEnum.STRING,
                       "default": "None"},
                      {"name": "epsilon",
                       "description": "Value added to both modeled and observed time series if fun is logarithm or other functions",
                       "data_type": DataTypeEnum.STRING, "default": "Pushpalatha2012"},
                      {"name": "normalized",
                       "description": "If True, return NNSE instead",
                       "data_type": DataTypeEnum.BOOLEAN, "default": "False"},
                  ]},
                  {"name": "LogNSE", "description": "NSE of Logarithmic values", "inputs": [
                      {"name": "fun", "description": "Transformation function applied to y_true and y_pred", "data_type": DataTypeEnum.STRING,
                       "default": "None"},
                      {"name": "epsilon",
                       "description": "Value added to both modeled and observed time series if fun is logarithm or other functions",
                       "data_type": DataTypeEnum.STRING, "default": "Pushpalatha2012"},
                      {"name": "normalized",
                       "description": "If True, return NNSE instead",
                       "data_type": DataTypeEnum.BOOLEAN, "default": "False"},
                  ]},
                  {"name": "NNSE", "description": "Normalized NSE", "inputs": [
                      {"name": "fun", "description": "Transformation function applied to y_true and y_pred", "data_type": DataTypeEnum.STRING,
                       "default": "None"},
                      {"name": "epsilon",
                       "description": "Value added to both modeled and observed time series if fun is logarithm or other functions",
                       "data_type": DataTypeEnum.STRING, "default": "Pushpalatha2012"},
                      {"name": "normalized",
                       "description": "If True, return NNSE instead",
                       "data_type": DataTypeEnum.BOOLEAN, "default": "False"},
                  ]},
                  {"name": "PoD", "description": "Probability of Detection",
                   "inputs": [{"name": "flow_threshold", "description": "Flow threshold in m3/s", "data_type": DataTypeEnum.DOUBLE, "default": "0"}]},
                  {"name": "CSI", "description": "Critical Success Index",
                   "inputs": [{"name": "flow_threshold", "description": "Flow threshold in m3/s", "data_type": DataTypeEnum.DOUBLE, "default": "0"}]},
                  {"name": "FAR", "description": "False Alarm Ratio",
                   "inputs": [{"name": "flow_threshold", "description": "Flow threshold in m3/s", "data_type": DataTypeEnum.DOUBLE, "default": "0"}]},
                  {"name": "HFDC", "description": "Percent bias of high flow segment of flow duration curve", "inputs": [
                      {"name": "peak_flow_exceedance_probability", "description": "Peek flow exceedance probability",
                       "data_type": DataTypeEnum.DOUBLE,
                       "default": "0.1"}]},
                  {"name": "LFDC", "description": "Percent bias of low flow segment of flow duration curve", "inputs": [
                      {"name": "base_flow_exceedance_probability", "description": "Base flow exceedance probability",
                       "data_type": DataTypeEnum.DOUBLE,
                       "default": "0.9"}]},
                  {"name": "PKBIAS", "description": "Absolute Peak Flow Bias", "inputs": []},
                  {"name": "pPKBIAS", "description": "Percent Peak Flow Bias", "inputs": []},
                  {"name": "PKTE", "description": "Peak Flow Timing Error", "inputs": []},
                  {"name": "EVBIAS", "description": "Event Volume Bias", "inputs": []},
                  ]

        for v in values:
            metric, created = Metric.objects.get_or_create(name=v.get('name'), is_active=True, description=v.get('description'),
                                                           created_by=self.user)

            for i in v.get('inputs'):
                MetricInput.objects.get_or_create(name=i.get('name'), is_active=True, description=i.get('description'), data_type=i.get('data_type'),
                                                  default_value=i.get('default'), metric=metric, created_by=self.user)

    def define_status(self):
        if self.DELETE_FLAG:
            Status.objects.all().delete()

        e: StatusEnum
        for e in StatusEnum:
            Status.objects.get_or_create(name=e.value, created_by=self.user)

    def define_ngen_formulations(self):
        if self.DELETE_FLAG:
            NgenCalFormulation.objects.all().delete()

        values = [
            {"name": "cfe_noah", "modules": json.dumps(["CFE-S", "Noah-OWP-Modular"]), "description": "CFE-S, Noah-OWP-Modular"},
            {"name": "cfe_noah_sft", "modules": json.dumps(["CFE-S", "Noah-OWP-Modular", "SFT", "SMP"]),
             "description": "CFE-S, Noah-OWP-Modular, SFT, SMP"},
            {"name": "cfe_xaj_noah", "modules": json.dumps(["CFE-X", "Noah-OWP-Modular"]),
             "description": "CFE-X, Noah-OWP-Modular"},
            {"name": "cfe_xaj_noah-sft", "modules": json.dumps(["CFE-X", "Noah-OWP-Modular", "SFT", "SMP"]),
             "description": "CFE-X, Noah-OWP-Modular, SFT, SMP"},
            {"name": "lasam_noah_sft", "modules": json.dumps(["LASAM", "Noah-OWP-Modular", "SFT", "SMP"]),
             "description": "LASAM, Noah-OWP-Modular, SFT, SMP"},
            {"name": "topmodel_noah", "modules": json.dumps(["TopModel", "Noah-OWP-Modular"]),
             "description": "TopModel, Noah-OWP-Modular"},
        ]

        for v in values:
            NgenCalFormulation.objects.get_or_create(name=v.get('name'), modules=v.get('modules'),
                                                     description=v.get('description'),
                                                     created_by=self.user)
