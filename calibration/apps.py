import logging
import os

from django.apps import AppConfig

from calibration.util.ngen_locations import files, dirs

logger = logging.getLogger(__name__)


class CalibrationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'calibration'

    def ready(self):
        for file in files:
            if not os.path.exists(file):
                logger.warning(f'{file} does not exist')
        for directory in dirs:
            if not os.path.exists(directory):
                logger.warning(f'{directory} does not exist')
