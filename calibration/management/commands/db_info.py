from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'Displays the database in use'

    def handle(self, *args, **kwargs):
        db_info = settings.DATABASES['default']
        self.stdout.write(f"Database Engine: {db_info['ENGINE']}")
        self.stdout.write(f"Database Name: {db_info['NAME']}")

        if db_info['ENGINE'] == 'django.db.backends.sqlite3':
            self.stdout.write(f"Database File: {db_info['NAME']}")
        else:
            self.stdout.write(
                f"Database URL: "
                f"{db_info.get('HOST', '')}:{db_info.get('PORT', '')}"
            )
            self.stdout.write(f"Database User: {db_info.get('USER', '')}")
