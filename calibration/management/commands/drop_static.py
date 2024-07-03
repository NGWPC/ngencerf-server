import json
from pprint import pprint

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from calibration.models import Module, ModuleGroup, Domain, ObservationalSource, ModuleInputVariable, ModuleOutputVariable, \
    Optimization, Metric, Status, NgenCalFormulation


class Command(BaseCommand):
    help = "Drop static tables"

    def handle(self, *args, **options):
        self.stdout.write('Dropping status tables')

        Module.objects.all().delete()
        ModuleGroup.objects.all().delete()
        Domain.objects.all().delete()
        ObservationalSource.objects.all().delete()
        ModuleInputVariable.objects.all().delete()
        ModuleOutputVariable.objects.all().delete()
        Optimization.objects.all().delete()
        Metric.objects.all().delete()
        Status.objects.all().delete()
        NgenCalFormulation.objects.all().delete()




