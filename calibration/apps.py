import logging
from pathlib import Path

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class CalibrationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'calibration'

    def ready(self):
        from calibration.util.file_util import copy_directory
        from calibration.util.ngen_locations import files, dirs, PARQUET_DIR, NOAH_PARAMETER_DIR
        from cerfServer.settings import BASE_DIR

        for file in files:
            if not Path(file).is_file():
                logger.warning(f'{file} does not exist')
        for directory in dirs:
            if not Path(directory).is_dir():
                logger.warning(f'{directory} does not exist')

        # Copy the static files
        copy_directory(Path(BASE_DIR) / 'ngen_static_files' / 'parquet', PARQUET_DIR)
        copy_directory(Path(BASE_DIR, ) / 'ngen_static_files' / 'bmi_config' / 'Noah-OWP', NOAH_PARAMETER_DIR)
