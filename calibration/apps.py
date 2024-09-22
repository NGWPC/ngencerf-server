import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class CalibrationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'calibration'

    def ready(self):
        from calibration.util.ngen_locations import check_files

        check_files()
