import logging
import os

from django.apps import AppConfig

from calibration.util.file_util import copy_directory
from calibration.util.ngen_locations import files, dirs, PARQUET_DIR, NOAH_PARAMETER_DIR
from cerfServer.settings import BASE_DIR

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

        # Copy the static files
        copy_directory(os.path.join(BASE_DIR, 'ngen_static_files', 'parquet'), PARQUET_DIR)
        copy_directory(os.path.join(BASE_DIR, 'ngen_static_files', 'bmi_config', 'Noah-OWP'), NOAH_PARAMETER_DIR)


