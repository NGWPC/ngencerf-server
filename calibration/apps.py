import logging
import os

from django.apps import AppConfig

from calibration.util.ngen_locations import files, dirs, PARQUET_DIR, NOAH_PARAMETER_DIR

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

        # Make sure we have files in these directories
        if os.path.exists(PARQUET_DIR):
            if len(os.listdir(PARQUET_DIR)) == 0:
                logger.warning('No parquet files found')

        if os.path.exists(NOAH_PARAMETER_DIR):
            if len(os.listdir(NOAH_PARAMETER_DIR)) == 0:
                logger.warning('No Noah Parameter files found')

