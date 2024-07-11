import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from calibration.enums import StatusEnum
from calibration.models import Domain, ObservationalSource, Optimization, Metric, NgenCalFormulation


class Command(BaseCommand):
    help = "Initializes static tables"

    # need to get a user that is guaranteed to be there, such as admin
    user = get_user_model().objects.get(username='peter')
    print('user:', user)

    def handle(self, *args, **options):
        self.stdout.write('Initializing status tables')

        # self.define_modules_and_groups()
        self.define_domains()
        self.define_observational_source()
        self.define_optimization()
        self.define_metric()
        self.define_ngen_formulations()

    def define_domains(self):
        Domain.objects.all().delete()

        Domain(name="Alaska", is_active=True, description='Need description', created_by=self.user, updated_by=self.user).save()
        Domain(name="Hawaii", is_active=True, description='Need description', created_by=self.user, updated_by=self.user).save()
        Domain(name="CONUS", is_active=True, description='Need description', created_by=self.user, updated_by=self.user).save()
        Domain(name="Puerto Rico, including US Virgin Island", is_active=True, description='Need description',
               created_by=self.user, updated_by=self.user).save()

    def define_observational_source(self):
        ObservationalSource.objects.all().delete()

        ObservationalSource(name="USGS", is_active=True, description='Need description', created_by=self.user,
                            updated_by=self.user).save()
        ObservationalSource(name="USACE", is_active=True, description='Need description', created_by=self.user,
                            updated_by=self.user).save()
        ObservationalSource(name="BOR", is_active=True, description='Need description', created_by=self.user,
                            updated_by=self.user).save()
        ObservationalSource(name="ENV", is_active=True, description='Need description', created_by=self.user,
                            updated_by=self.user).save()
        ObservationalSource(name="State Agency", is_active=True, description='Need description', created_by=self.user,
                            updated_by=self.user).save()
        ObservationalSource(name="RFC", is_active=True, description='Need description', created_by=self.user,
                            updated_by=self.user).save()

    def define_optimization(self):
        Optimization.objects.all().delete()

        Optimization(name="DDS", is_active=True, description='Need description', created_by=self.user,
                     updated_by=self.user).save()
        Optimization(name="PWO", is_active=True, description='Need description', created_by=self.user,
                     updated_by=self.user).save()
        Optimization(name="Grey Wolf", is_active=True, description='Need description', created_by=self.user,
                     updated_by=self.user).save()

    def define_metric(self):
        Metric.objects.all().delete()

        Metric(name="Cor", is_active=True, description='Pearson Correlation', created_by=self.user, updated_by=self.user).save()
        Metric(name="MAE", is_active=True, description='Mean Absolute Error', created_by=self.user, updated_by=self.user).save()
        Metric(name="RMSE", is_active=True, description='Root Mean Square Error', created_by=self.user,
               updated_by=self.user).save()
        Metric(name="RSR", is_active=True, description='Ratio of RMSE to standard deviation of observation', created_by=self.user,
               updated_by=self.user).save()
        Metric(name="PBIAS", is_active=True, description='Percent Bias', created_by=self.user, updated_by=self.user).save()
        Metric(name="KGE", is_active=True, description='Kling-Gupta Efficiency', created_by=self.user,
               updated_by=self.user).save()
        Metric(name="NSE", is_active=True, description='Nash-Sutcliffe-Efficiency', created_by=self.user,
               updated_by=self.user).save()
        Metric(name="LogNSE", is_active=True, description='NSE of Logarithmic values', created_by=self.user,
               updated_by=self.user).save()
        Metric(name="PoD", is_active=True, description='Probability of Detection', created_by=self.user,
               updated_by=self.user).save()
        Metric(name="CSI", is_active=True, description='Critical Success Index', created_by=self.user,
               updated_by=self.user).save()
        Metric(name="FAR", is_active=True, description='False Alarm Ratio', created_by=self.user, updated_by=self.user).save()
        Metric(name="HFDC", is_active=True, description='Percent bias of high flow segment of flow duration curve',
               created_by=self.user, updated_by=self.user).save()
        Metric(name="LFDC", is_active=True, description='Percent bias of low flow segment of flow duration curve',
               created_by=self.user, updated_by=self.user).save()
        Metric(name="PKBIAS", is_active=True, description='Absolute Peak Flow Bias', created_by=self.user,
               updated_by=self.user).save()
        Metric(name="pPKBIAS", is_active=True, description='Percent Peak Flow Bias', created_by=self.user,
               updated_by=self.user).save()
        Metric(name="PKTE", is_active=True, description='Peak Flow Timing Error', created_by=self.user,
               updated_by=self.user).save()
        Metric(name="EVBIAS", is_active=True, description='Event Volume Bias', created_by=self.user, updated_by=self.user).save()

    def define_ngen_formulations(self):
        NgenCalFormulation.objects.all().delete()

        NgenCalFormulation(name="cfe_noah", modules=json.dumps(["CFE-S", "Noah-OWP-Modular"]),
                           description='Need description', created_by=self.user, updated_by=self.user).save()
        NgenCalFormulation(name="cfe_noah_sft", modules=json.dumps(["CFE-S", "Noah-OWP-Modular", "SFT", "SMP"]),
                           description='Need description', created_by=self.user, updated_by=self.user).save()
        NgenCalFormulation(name="cfe_xaj_noah", modules=json.dumps(["CFE-X", "Noah-OWP-Modular"]),
                           description='Need description', created_by=self.user, updated_by=self.user).save()
        NgenCalFormulation(name="cfe_xaj_noah_sft", modules=json.dumps(["CFE-X", "Noah-OWP-Modular", "SFT", "SMP"]),
                           description='Need description', created_by=self.user, updated_by=self.user).save()
        NgenCalFormulation(name="lasam_noah_sft", modules=json.dumps(["LASAM", "Noah-OWP-Modular", "SFT", "SMP"]),
                           description='Need description', created_by=self.user, updated_by=self.user).save()
        NgenCalFormulation(name="topmodel_noah", modules=json.dumps(["TopModel", "Noah-OWP-Modular"]),
                           description='Need description', created_by=self.user, updated_by=self.user).save()
