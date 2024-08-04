import os

from django.apps import AppConfig

from calibration.views.ngen_locations import libs, dirs


class CalibrationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'calibration'

    def ready(self):
        for lib in libs:
            if not os.path.exists(lib):
                print(lib, 'does not exist')
        for directory in dirs:
            if not os.path.exists(directory):
                print(directory, 'does not exist')
