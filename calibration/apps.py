import logging
import sys

from django.apps import AppConfig
from django.conf import settings

from calibration.util.git_util import print_git_info

logger = logging.getLogger(__name__)


def print_db_info():
    db_info = settings.DATABASES['default']
    logger.info(f"Database Engine: {db_info['ENGINE']}")
    logger.info(f"Database Name: {db_info['NAME']}")
    logger.info(f"Database URL: {db_info['HOST']}:{db_info['PORT']}")
    logger.info(f"Database User: {db_info['USER']}")


def print_banner():
    RED = "\33[91m"
    BLUE = "\33[94m"
    GREEN = "\033[32m"
    YELLOW = "\033[93m"
    PURPLE = '\033[0;35m'
    CYAN = "\033[36m"
    END = "\033[0m"

    banner = f"""
    {CYAN}
███╗   ██╗ ██████╗ ███████╗███╗   ██╗ ██████╗███████╗██████╗ ███████╗
████╗  ██║██╔════╝ ██╔════╝████╗  ██║██╔════╝██╔════╝██╔══██╗██╔════╝
██╔██╗ ██║██║  ███╗█████╗  ██╔██╗ ██║██║     █████╗  ██████╔╝█████╗  
██║╚██╗██║██║   ██║██╔══╝  ██║╚██╗██║██║     ██╔══╝  ██╔══██╗██╔══╝ta  
██║ ╚████║╚██████╔╝███████╗██║ ╚████║╚██████╗███████╗██║  ██║██║     
╚═╝  ╚═══╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝ ╚═════╝╚══════╝╚═╝  ╚═╝╚═╝     
                                                                     
███████╗███████╗██████╗ ██╗   ██╗███████╗██████╗                     
██╔════╝██╔════╝██╔══██╗██║   ██║██╔════╝██╔══██╗                    
███████╗█████╗  ██████╔╝██║   ██║█████╗  ██████╔╝                    
╚════██║██╔══╝  ██╔══██╗╚██╗ ██╔╝██╔══╝  ██╔══██╗                    
███████║███████╗██║  ██║ ╚████╔╝ ███████╗██║  ██║                    
╚══════╝╚══════╝╚═╝  ╚═╝  ╚═══╝  ╚══════╝╚═╝  ╚═╝ {END}"""

    logger.info(banner)


class CalibrationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'calibration'

    def ready(self):
        # Check if we're running the server or a management command
        running_server = 'runserver' in sys.argv or 'runsslserver' in sys.argv
        if running_server:
            print_banner()
        else:
            logger.info(f'*** Running {sys.argv[1]}')

        logger.info(f'Version: {settings.VERSION}, {settings.DATE}')

        logger.info(f'Environment: {settings.NGEN_ENVIRONMENT_STR}')
        logger.info('')

        print_db_info()
        logger.info('')
        logger.info(f'NGWPC Enterprise Data Server url: {settings.ENTERPRISE_DATA_URL}\n')
        logger.info(f'NGEN_CAL_MOUNT_POINT - {settings.NGEN_CAL_MOUNT_POINT}')
        logger.info(f'NGEN_STATIC_DIR - {settings.NGEN_STATIC_DIR}')
        if running_server:
            logger.info('')
            print_git_info()

        from calibration.util.ngen_locations import check_files

        check_files()
