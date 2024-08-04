import logging
import os

from django.apps import AppConfig

from calibration.util.ngen_locations import libs, dirs

logger = logging.getLogger(__name__)


class CalibrationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'calibration'

    def ready(self):
        for lib in libs:
            if not os.path.exists(lib):
                logger.warning(f'{lib} does not exist')
        for directory in dirs:
            if not os.path.exists(directory):
                logger.warning(f'{directory} does not exist')
