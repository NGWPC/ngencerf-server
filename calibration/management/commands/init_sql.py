import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from calibration.enums import StatusEnum, DataTypeEnum
from calibration.models import Domain, ObservationalSource, Optimization, Metric, NgenCalFormulation, OptimizationInput
from calibration.models.forcing_source import ForcingSource
from calibration.models.status import Status


class Command(BaseCommand):
    help = "Initializes static tables"

    # This script can be run multiple times without harm.  The name field will not be changed, but all other fields, such as
    # 'description' and 'is_active' will be.
    # Do not delete any of the data entries.  They will not be deleted.  Deleting any entries in the database cana cause problems
    # because these fields are Foreign Keys in other tables.
    # Instead, do a 'soft' delete by setting 'is_active' to false.
    # You can add new records and this script will add them.

    # Don't turn this flag on unless you know what you're doing.
    # For Development oly
    DELETE_FLAG = False

    # need to get a user that is guaranteed to be there, such as admin
    user = get_user_model().objects.get(username='admin')
    print('user:', user)

    def handle(self, *args, **options):
        self.stdout.write('Initializing static tables')

        self.define_domains()
        self.define_forcing_source()
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
            Domain.objects.get_or_create(name=v['name'], defaults={"is_active": v.get('is_active', True),
                                                                   "description": v['description'],
                                                                   "created_by": self.user})

    def define_forcing_source(self):
        if self.DELETE_FLAG:
            ForcingSource.objects.all().delete()

        values = [{"name": "AORC", "description": "Analysis of Record For Calibration"},
                  {"name": "Upload", "description": "Uploaded by the user from a local file"},
                  ]

        for v in values:
            ForcingSource.objects.get_or_create(name=v['name'], defaults={"is_active": v.get('is_active', True),
                                                                          "description": v['description'],
                                                                          "created_by": self.user})

    def define_observational_source(self):
        if self.DELETE_FLAG:
            ObservationalSource.objects.all().delete()

        values = [{"name": "USGS", "description": "US Geological Society", "is_active": True},
                  {"name": "USACE", "description": "US Army Corp of Engineers", "is_active": True},
                  {"name": "BOR", "description": "Bureau of Reclamation", "is_active": False},
                  {"name": "ENV", "description": "Environmental Canada", "is_active": True},
                  {"name": "CA DWR", "description": "California Department of Water Resources", "is_active": True},
                  {"name": "TX DoT", "description": "Texas Department of Transportation", "is_active": False},
                  {"name": "RFC", "description": "River Forecast Center", "is_active": False},
                  {"name": "SNOTEL", "description": "Snow Telemetry", "is_active": False},
                  {"name": "Upload", "description": "Upload by the user from a local file", "is_active": False},
                  ]

        for v in values:
            ObservationalSource.objects.get_or_create(name=v['name'],
                                                      defaults={"is_active": v.get('is_active', True),
                                                                "description": v['description'],
                                                                "created_by": self.user})

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

        # stop_criteria_name and stop_criteria_data_type are not used at this time.  Setting to these values for now, but we never look at it
        for v in values:
            optimization, created = Optimization.objects.get_or_create(name=v['name'],
                                                                       defaults={"is_active": v.get('is_active', True),
                                                                                 "description": v['description'],
                                                                                 "stop_criteria_name": "iterations",
                                                                                 "stop_criteria_data_type": DataTypeEnum.INTEGER,
                                                                                 "created_by": self.user})

            for i in v['inputs']:
                OptimizationInput.objects.get_or_create(name=i['name'], defaults={"is_active": i.get('is_active', True),
                                                                                  "description": i['description'],
                                                                                  "data_type": i['data_type'],
                                                                                  "optimization": optimization,
                                                                                  "created_by": self.user})

    def define_metric(self):
        if self.DELETE_FLAG:
            Metric.objects.all().delete()

        values = [{"name": "Cor", "description": "Pearson Correlation"},
                  {"name": "MAE", "description": "Mean Absolute Error"},
                  {"name": "RMSE", "description": "Root Mean Square Error"},
                  {"name": "RSR", "description": "Ratio of RMSE to standard deviation of observation"},
                  {"name": "PBIAS", "description": "Percent Bias"},
                  {"name": "KGE", "description": "Kling-Gupta Efficiency"},
                  {"name": "NSE", "description": "Nash-Sutcliffe-Efficiency"},
                  {"name": "LogNSE", "description": "NSE of Logarithmic values"},
                  {"name": "NNSE", "description": "Normalized NSE"},
                  {"name": "POD", "description": "Probability of Detection", "categorical": True},
                  {"name": "CSI", "description": "Critical Success Index", "categorical": True},
                  {"name": "FAR", "description": "False Alarm Ratio", "categorical": True},
                  {"name": "HFDC", "description": "Percent bias of high flow segment of flow duration curve"},
                  {"name": "LFDC", "description": "Percent bias of low flow segment of flow duration curve"},
                  {"name": "PKBIAS", "description": "Absolute Peak Flow Bias", "is_active": False},
                  {"name": "pPKBIAS", "description": "Percent Peak Flow Bias", "is_active": False},
                  {"name": "PKTE", "description": "Peak Flow Timing Error", "is_active": False},
                  {"name": "EVBIAS", "description": "Event Volume Bias", "is_active": False},
                  ]

        for v in values:
            Metric.objects.get_or_create(name=v['name'], defaults={"is_active": v.get('is_active', True),
                                                                   "description": v['description'],
                                                                   "categorical": v.get('categorical', False),
                                                                   "created_by": self.user})

    def define_status(self):
        if self.DELETE_FLAG:
            print('deleting')
            Status.objects.all().delete()

        e: StatusEnum
        for e in StatusEnum:
            print('creating', e)
            Status.objects.get_or_create(name=e.value, defaults={"created_by": self.user})

    def define_ngen_formulations(self):
        if self.DELETE_FLAG:
            NgenCalFormulation.objects.all().delete()

        values = [
            {"name": "cfe_noah", "modules": json.dumps(["CFE-S", "Noah-OWP-Modular", "T-Route"]),
             "description": "CFE-S, Noah-OWP-Modular, T-Route"},
            {"name": "cfe_noah_sft", "modules": json.dumps(["CFE-S", "Noah-OWP-Modular", "SFT", "SMP", "T-Route"]),
             "description": "CFE-S, Noah-OWP-Modular, SFT, SMP, T-Route"},
            {"name": "cfe_xaj_noah", "modules": json.dumps(["CFE-X", "Noah-OWP-Modular", "T-Route"]),
             "description": "CFE-X, Noah-OWP-Modular, T-Route"},
            {"name": "cfe_xaj_noah-sft", "modules": json.dumps(["CFE-X", "Noah-OWP-Modular", "SFT", "SMP", "T-Route"]),
             "description": "CFE-X, Noah-OWP-Modular, SFT, SMP, T-Route"},
            {"name": "lasam_noah_sft", "modules": json.dumps(["LASAM", "Noah-OWP-Modular", "SFT", "SMP", "T-Route"]),
             "description": "LASAM, Noah-OWP-Modular, SFT, SMP, T-Route"},
            {"name": "topmodel_noah", "modules": json.dumps(["TopModel", "Noah-OWP-Modular", "T-Route"]),
             "description": "TopModel, Noah-OWP-Modular, T-Route"},
        ]

        for v in values:
            NgenCalFormulation.objects.get_or_create(name=v['name'], defaults={"modules": v['modules'],
                                                                               "description": v['description'],
                                                                               "created_by": self.user})
