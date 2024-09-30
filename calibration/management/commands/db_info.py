from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'Displays the database in use'

    def handle(self, *args, **kwargs):
        db_info = settings.DATABASES['default']
        self.stdout.write(f"Database Engine: {db_info['ENGINE']}")
        self.stdout.write(f"Database Name: {db_info['NAME']}")
