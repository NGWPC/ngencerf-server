import os

from django.apps import AppConfig

from views.ngen_locations import libs, dirs


class CalibrationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'calibration'

    def ready(self):
        for l in libs:
            if not os.path.exists(l):
                print(l, 'does not exist')
        for d in dirs:
            if not os.path.exists(d):
                print(d, 'does not exist')

