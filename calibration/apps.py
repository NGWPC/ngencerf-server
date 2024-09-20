import logging
from pathlib import Path

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class CalibrationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'calibration'

    def ready(self):
        from calibration.util.ngen_locations import files, dirs

        for file in files:
            if not Path(file).is_file():
                logger.warning(f'{file} does not exist')
        for directory in dirs:
            if not Path(directory).is_dir():
                logger.warning(f'{directory} does not exist')
