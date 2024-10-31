import logging

from django.apps import AppConfig

from cerfServer.settings import NGEN_LOGGING_DIR

logger = logging.getLogger(__name__)


class CalibrationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'calibration'

    def ready(self):

        # Make sure the logging directory exists
        NGEN_LOGGING_DIR.mkdir(exist_ok=True)

        from calibration.util.ngen_locations import check_files

        check_files()
