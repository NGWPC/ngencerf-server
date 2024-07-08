from django.core.management.base import BaseCommand

from calibration.models import Domain, ObservationalSource, ModuleInputVariable, ModuleOutputVariable, \
    Optimization, Metric, Status, NgenCalFormulation


class Command(BaseCommand):
    help = "Drop static tables"

    def handle(self, *args, **options):
        self.stdout.write('Dropping status tables')

        Domain.objects.all().delete()
        ObservationalSource.objects.all().delete()
        # ModuleInputVariable.objects.all().delete()
        # ModuleOutputVariable.objects.all().delete()
        Optimization.objects.all().delete()
        Metric.objects.all().delete()
        Status.objects.all().delete()
        NgenCalFormulation.objects.all().delete()





