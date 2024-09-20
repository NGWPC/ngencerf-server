#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import atexit
import logging
import os
import sys
import traceback

# Set up logging
logger = logging.getLogger(__name__)


### Some debugging for a weird error that Miguel is having
def on_exit():
    exc_type, exc_value, exc_traceback = sys.exc_info()
    if exc_type:
        # Log the error message and stack trace if the application crashed
        logger.error(f"Application crashed due to: {exc_type.__name__} - {exc_value}")
        logger.error(''.join(traceback.format_exception(exc_type, exc_value, exc_traceback)))
    else:
        # Log a normal shutdown message
        logger.debug("The application is exiting normally.")

# Register the on_exit function to be called on application exit
atexit.register(on_exit)
#####


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cerfServer.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
