import os

from django.apps import AppConfig

from views.ngen_locations import libs, dirs


class CalibrationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'calibration'

    def ready(self):
        for lib in libs:
            if not os.path.exists(lib):
                print(lib, 'does not exist')
        for dir in dirs:
            if not os.path.exists(dir):
                print(dir, 'does not exist')
