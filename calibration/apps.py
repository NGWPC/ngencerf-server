import logging
import sys

from django.apps import AppConfig
from django.conf import settings

from cerfServer.settings import NGEN_LOGGING_DIR

logger = logging.getLogger(__name__)


def print_db_info():
    db_info = settings.DATABASES['default']
    print(f"Database Engine: {db_info['ENGINE']}")
    print(f"Database Name: {db_info['NAME']}")
    print(f"Database URL: {db_info['HOST']}:{db_info['PORT']}")
    print(f"Database User: {db_info['USER']}")


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
██║╚██╗██║██║   ██║██╔══╝  ██║╚██╗██║██║     ██╔══╝  ██╔══██╗██╔══╝  
██║ ╚████║╚██████╔╝███████╗██║ ╚████║╚██████╗███████╗██║  ██║██║     
╚═╝  ╚═══╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝ ╚═════╝╚══════╝╚═╝  ╚═╝╚═╝     
                                                                     
███████╗███████╗██████╗ ██╗   ██╗███████╗██████╗                     
██╔════╝██╔════╝██╔══██╗██║   ██║██╔════╝██╔══██╗                    
███████╗█████╗  ██████╔╝██║   ██║█████╗  ██████╔╝                    
╚════██║██╔══╝  ██╔══██╗╚██╗ ██╔╝██╔══╝  ██╔══██╗                    
███████║███████╗██║  ██║ ╚████╔╝ ███████╗██║  ██║                    
╚══════╝╚══════╝╚═╝  ╚═╝  ╚═══╝  ╚══════╝╚═╝  ╚═╝ {END}"""

    print(banner)


class CalibrationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'calibration'

    def ready(self):
        # Check if the server is being started with 'runserver' or 'runsslserver'
        if 'runserver' in sys.argv or 'runsslserver' in sys.argv:
            print_banner()

        print(f'Version: {settings.VERSION}')

        print(f'Environment: {settings.NGEN_ENVIRONMENT_STR}')
        print()

        print_db_info()
        print()

        # Make sure the logging directory exists
        NGEN_LOGGING_DIR.mkdir(exist_ok=True)

        from calibration.util.ngen_locations import check_files

        check_files()
