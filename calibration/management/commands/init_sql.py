import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from calibration.enums import DataTypeEnum
from calibration.models import Domain, ObservationalSource, Optimization, Metric, NgenCalFormulation, OptimizationInput, PlotDefinition
from calibration.models.forcing_source import ForcingSource
from calibration.models.rfc import Rfc
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

    def __init__(self):
        super().__init__()
        self.user = None  # Define the attribute here

    def handle(self, *args, **options):
        self.stdout.write('Initializing static tables')
        # need to get a user that is guaranteed to be there, such as admin
        self.user = get_user_model().objects.get(username='admin')
        self.stdout.write(f"In init_sql: username: {self.user.username}, email: {self.user.email}")

        self.define_domains()
        self.define_rfc()
        self.define_forcing_source()
        self.define_observational_source()
        self.define_optimization()
        self.define_metric()
        self.define_status()
        self.define_ngen_formulations()
        self.define_plot_definitions()

    def define_domains(self):
        if self.DELETE_FLAG:
            Domain.objects.all().delete()

        values = [{"name": "Alaska", "description": "Alaska"},
                  {"name": "Hawaii", "description": "Hawaii"},
                  {"name": "CONUS", "description": "Continental United Status"},
                  {"name": "Puerto Rico", "description": "Puerto Rico, including US Virgin Islands"}
                  ]

        for v in values:
            Domain.objects.update_or_create(name=v['name'], defaults={"is_active": v.get('is_active', True),
                                                                      "description": v['description'],
                                                                      "created_by": self.user})

    def define_rfc(self):
        if self.DELETE_FLAG:
            Rfc.objects.all().delete()

        values = [{"name": "NWRFC", "description": "Northwest River Forecast Center"},
                  {"name": "CNRFC", "description": "California/Nevada River Forecast Center"},
                  {"name": "CBRFC", "description": "Colorado Basin River Forecast Center"},
                  {"name": "MBRFC", "description": "Missouri Basin River Forecast Center"},
                  {"name": "ABRFC", "description": "Arkansas Red-Basin River Forecast Center"},
                  {"name": "WGRFC", "description": "West Gulf River Forecast Center"},
                  {"name": "NCRFC", "description": "North Central River Forecast Center"},
                  {"name": "LMRFC", "description": "Lower Mississippi River Forecast Center"},
                  {"name": "OHRFC", "description": "Ohio River Forecast Center"},
                  {"name": "SERFC", "description": "Southeast River Forecast Center"},
                  {"name": "MARFC", "description": "Mid-Atlantic River Forecast Center"},
                  {"name": "NERFC", "description": "Northeast River Forecast Center"},
                  {"name": "ARFC", "description": "Alaska River Forecast Center"},
                  {"name": "APRFC", "description": "Alaska Pacific River Forecast Center"},
                  {"name": "Canada", "description": "Canada River Forecast Center"}
                  ]

        for v in values:
            Rfc.objects.update_or_create(name=v['name'], defaults={"is_active": v.get('is_active', True),
                                                                   "description": v['description'],
                                                                   "created_by": self.user})

    def define_forcing_source(self):
        if self.DELETE_FLAG:
            ForcingSource.objects.all().delete()

        values = [{"name": "AORC", "description": "Analysis of Record For Calibration", "is_active": False},
                  {"name": "Upload", "description": "Uploaded by the user from a local file"},
                  ]

        for v in values:
            ForcingSource.objects.update_or_create(name=v['name'], defaults={"is_active": v.get('is_active', True),
                                                                             "description": v['description'],
                                                                             "created_by": self.user})

    def define_observational_source(self):
        if self.DELETE_FLAG:
            ObservationalSource.objects.all().delete()

        values = [{"name": "USGS", "description": "US Geological Society", "is_active": False},
                  {"name": "USACE", "description": "US Army Corp of Engineers", "is_active": False},
                  {"name": "BOR", "description": "Bureau of Reclamation", "is_active": False},
                  {"name": "ENV", "description": "Environmental Canada", "is_active": False},
                  {"name": "CA DWR", "description": "California Department of Water Resources", "is_active": False},
                  {"name": "TX DoT", "description": "Texas Department of Transportation", "is_active": False},
                  {"name": "RFC", "description": "River Forecast Center", "is_active": False},
                  {"name": "SNOTEL", "description": "Snow Telemetry", "is_active": False},
                  {"name": "Agency", "description": "From the owning agency", "is_active": False},
                  {"name": "Upload", "description": "Upload by the user from a local file", "is_active": True},
                  ]

        for v in values:
            ObservationalSource.objects.update_or_create(name=v['name'],
                                                         defaults={"is_active": v.get('is_active', True),
                                                                   "description": v['description'],
                                                                   "created_by": self.user})

    def define_optimization(self):
        if self.DELETE_FLAG:
            Optimization.objects.all().delete()
            OptimizationInput.objects.all().delete()

        values = [{"name": "DDS", "description": "Dynamically Dimensioned Search",
                   "inputs": [{"name": "r", "description": "Sample region size", "data_type": DataTypeEnum.DOUBLE, "default_value": 0.2, "min": 0.2,
                               "max": 0.2}]},
                  {"name": "PSO", "description": "Particle Swarm Optimization",
                   "inputs": [{"name": "swarm_size", "description": "Swarm size", "data_type": DataTypeEnum.INTEGER, "default_value": 2, "min": 2},
                              {"name": "c1", "description": "Acceleration coefficient c1", "data_type": DataTypeEnum.DOUBLE, "default_value": 2.0,
                               "min": 1.0, "max": 3.0},
                              {"name": "c2", "description": "Acceleration coefficient c2 ", "data_type": DataTypeEnum.DOUBLE, "default_value": 2.0,
                               "min": 1.0, "max": 3.0},
                              {"name": "w", "description": "Inertia weight", "data_type": DataTypeEnum.DOUBLE, "default_value": 0.7, "min": 0.0,
                               "max": 1.0}]},
                  {"name": "GWO", "description": "Grey Wolf Optimization",
                   "inputs": [{"name": "swarm_size", "description": "Swarm size", "data_type": DataTypeEnum.INTEGER, "default_value": 4, "min": 4}]},
                  ]

        # stop_criteria_name and stop_criteria_data_type are not used at this time.  Setting to these values for now, but we never look at it
        for v in values:
            optimization, created = Optimization.objects.update_or_create(name=v['name'],
                                                                          defaults={"is_active": v.get('is_active', True),
                                                                                    "description": v['description'],
                                                                                    "stop_criteria_name": "iterations",
                                                                                    "stop_criteria_data_type": DataTypeEnum.INTEGER,
                                                                                    "created_by": self.user})

            for i in v['inputs']:
                OptimizationInput.objects.update_or_create(name=i['name'], optimization=optimization,
                                                           defaults={"is_active": i.get('is_active', True),
                                                                     "description": i['description'],
                                                                     "data_type": i['data_type'],
                                                                     "default_value": i['default_value'],
                                                                     "min": i.get('min', None),
                                                                     "max": i.get('max', None),
                                                                     "created_by": self.user})

    def define_metric(self):
        if self.DELETE_FLAG:
            Metric.objects.all().delete()

        values = [{"name": "Corr", "description": "Pearson Correlation"},
                  {"name": "MAE", "description": "Mean Absolute Error"},
                  {"name": "RMSE", "description": "Root Mean Square Error"},
                  {"name": "RSR", "description": "Ratio of RMSE to standard deviation of observation"},
                  {"name": "PBIAS", "description": "Percent Bias"},
                  {"name": "KGE", "description": "Kling-Gupta Efficiency"},
                  {"name": "NSE", "description": "Nash-Sutcliffe-Efficiency"},
                  {"name": "NSELog", "description": "NSE of Logarithmic values"},
                  {"name": "NNSE", "description": "Normalized NSE"},
                  {"name": "POD", "description": "Probability of Detection", "categorical": True},
                  {"name": "CSI", "description": "Critical Success Index", "categorical": True},
                  {"name": "FAR", "description": "False Alarm Ratio", "categorical": True},
                  {"name": "HSEG_FDC", "description": "Percent bias of high flow segment of flow duration curve"},
                  {"name": "LSEG_FDC", "description": "Percent bias of low flow segment of flow duration curve"},
                  {"name": "PKBIAS", "description": "Absolute Peak Flow Bias", "event_based": True},
                  {"name": "PKTE", "description": "Peak Flow Timing Error", "event_based": True},
                  {"name": "EVBIAS", "description": "Event Volume Bias", "event_based": True},
                  {"name": "FBIAS", "description": "Frequency Bias", "categorical": True},
                  {"name": "MSEG_FDC", "description": "Percent bias of middle flow segment of flow duration curve"},
                  {"name": "NSEWt", "description": "Weighted NSE and NSELog"},
                  ]

        for v in values:
            Metric.objects.update_or_create(name=v['name'], defaults={"is_active": v.get('is_active', True),
                                                                      "description": v['description'],
                                                                      "categorical": v.get('categorical', False),
                                                                      "event_based": v.get('event_based', False),
                                                                      "created_by": self.user})

    def define_status(self):
        if self.DELETE_FLAG:
            Status.objects.all().delete()

        values = [{"name": "Saved"},
                  {"name": "Ready"},
                  {"name": "Running"},
                  {"name": "Done"},
                  {"name": "Cancelled"},
                  {"name": "Failed"},
                  {"name": "Resumed"},
                  {"name": "Server error"}
                  ]

        for v in values:
            Status.objects.update_or_create(name=v['name'], defaults={"created_by": self.user})

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
            {"name": "cfe_xaj_noah_sft", "modules": json.dumps(["CFE-X", "Noah-OWP-Modular", "SFT", "SMP", "T-Route"]),
             "description": "CFE-X, Noah-OWP-Modular, SFT, SMP, T-Route"},
            {"name": "lasam_noah_sft", "modules": json.dumps(["LASAM", "Noah-OWP-Modular", "SFT", "SMP", "T-Route"]),
             "description": "LASAM, Noah-OWP-Modular, SFT, SMP, T-Route"},
            {"name": "topmodel_noah", "modules": json.dumps(["TopModel", "Noah-OWP-Modular", "T-Route"]),
             "description": "TopModel, Noah-OWP-Modular, T-Route"},
        ]

        for v in values:
            NgenCalFormulation.objects.update_or_create(name=v['name'], defaults={"modules": v['modules'],
                                                                                  "description": v['description'],
                                                                                  "created_by": self.user})

    def define_plot_definitions(self):
        if self.DELETE_FLAG:
            PlotDefinition.objects.all().delete()

        # Temporarily delete them, although this doesn't hurt, since this table is not a FK in any other table
        PlotDefinition.objects.all().delete()

        values = [
            {
                "name": "Hydrograph evolution",
                "description": "Time series plot comparing streamflow simulations from the control, the best iteration and the last iteration with the observed streamflow",
                "location": "plot_iteration",
                "valid_optimizations": "[\"GWO\", \"PSO\", \"DDS\"}",
                "validation": False,
                "filename_mask": "{gage_id}_hydrograph_iteration.png"
            },
            {
                "name": "Objective Function evolution",
                "description": "The evolution of objective function during all iterations with the best iteration highlighted in red",
                "location": "plot_iteration",
                "valid_optimizations": "[\"GWO\", \"PSO\", \"DDS\"}",
                "validation": False,
                "filename_mask": "{gage_id}_objfun_iteration.png"
            },
            {
                "name": "Metric evolution",
                "description": "The evolution of objective function and all other metrics during all iterations with the best iteration highlighted in red",
                "location": "plot_iteration",
                "valid_optimizations": "[\"GWO\", \"PSO\", \"DDS\"}",
                "validation": False,
                "filename_mask": "{gage_id}_metric_iteration.png"
            },
            {
                "name": "Parameter evolution",
                "description": "The evolution of each calibration parameter during all iterations with the best iteration highlighted in red",
                "location": "plot_iteration",
                "valid_optimizations": "[\"GWO\", \"PSO\", \"DDS\"}",
                "validation": False,
                "filename_mask": "{gage_id}_param_iteration.png"
            },
            {
                "name": "Scatterplot streamflow",
                "description": "Scatter plot of streamflow simulations from the control, the best iteration and the last iteration vs the observed streamflow",
                "location": "plot_iteration",
                "valid_optimizations": "[\"GWO\", \"PSO\", \"DDS\"}",
                "validation": False,
                "filename_mask": "{gage_id}_scatterplot_streamflow_iteration.png"
            },
            {
                "name": "Metrics vs Objective Functions",
                "description": "Scatter plot of objective function vs each of the other evaluation metrics from all iterations (to examine tradeoffs between the objective function and other metrics)",
                "location": "plot_iteration",
                "valid_optimizations": "[\"GWO\", \"PSO\", \"DDS\"}",
                "validation": False,
                "filename_mask": "{gage_id}_metric_objfun.png"
            },
            {
                "name": "Stream Flow Precipitation",
                "description": "Same as Hydrograph Evolution but with the precipitation time series added at the top using an inverted y-axis",
                "location": "plot_iteration",
                "valid_optimizations": "[\"GWO\", \"PSO\", \"DDS\"}",
                "validation": False,
                "filename_mask": "{gage_id}_streamflow_precip_iteration.png"
            },
            {
                "name": "Flow Duration Curves",
                "description": "Comparison of the flow duration curves for the streamflow simulations from the control, the best iteration, the last iteration and the observed streamflow",
                "location": "plot_iteration",
                "valid_optimizations": "[\"GWO\", \"PSO\", \"DDS\"}",
                "validation": False,
                "filename_mask": "{gage_id}_fdc_iteration.png"
            },
            {
                "name": "Cost History",
                "description": "Comparison of the best global, local and best cost values at each iteration",
                "location": "output_calibration",
                "valid_optimizations": "[\"GWO\", \"PSO\"}",
                "validation": False,
                "filename_mask": "{gage_id}_cost_hist.png"
            },
            {
                "name": "Bar Chart Metrics",
                "description": "Bar chart comparing metrics from best and control validation runs for each evaluation period of the best global, local and best cost values at each iteration",
                "location": "output_validation",
                "valid_optimizations": "[\"GWO\", \"PSO\",  \"DDS\"}",
                "validation": True,
                "filename_mask": "{gage_id}_barplot_metrics_valid_run.png"
            },
            {
                "name": "Flow Duration Curves Validation",
                "description": "Plot of flow duration curve comparing best and control validation runs with observation for each evaluation period",
                "location": "output_validation",
                "valid_optimizations": "[\"GWO\", \"PSO\",  \"DDS\"}",
                "validation": True,
                "filename_mask": "{gage_id}_fdc_valid_run.png"
            },
            {
                "name": "Hydrograph Validation",
                "description": "Plot comparing streamflow times series from best and control validation runs with observed streamflow",
                "location": "output_validation",
                "valid_optimizations": "[\"GWO\", \"PSO\",  \"DDS\"}",
                "validation": True,
                "filename_mask": "{gage_id}_hydrograph_valid_run.png"
            },
            {
                "name": "Streamflow Validation Precipitation",
                "description": "Same as Hydrograph Validation but with the precipitation time series added at the top using an inverted y-axi",
                "location": "output_validation",
                "valid_optimizations": "[\"GWO\", \"PSO\",  \"DDS\"}",
                "validation": True,
                "filename_mask": "{gage_id}streamflow_precip_valid_run.png"
            }
        ]

        for v in values:
            PlotDefinition.objects.update_or_create(name=v['name'], defaults={"is_active": v.get('is_active', True),
                                                                               "description": v['description'],
                                                                               "location": v['location'],
                                                                               "valid_optimizations": v['valid_optimizations'],
                                                                               "validation": v['validation'],
                                                                               "filename_mask": v['filename_mask'],
                                                                               "created_by": self.user})
