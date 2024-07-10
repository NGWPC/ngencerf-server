import os

from django.apps import AppConfig
from django.dispatch import receiver
from django.db.backends.signals import connection_created


class CalibrationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'calibration'

    # Use this function to do any database clean-up, such
    # as identifying any CalibrationRun or ValidationRuns in Running status
    # https://stackoverflow.com/questions/33814615/how-to-avoid-appconfig-ready-method-running-twice-in-django
    def ready(self):
        # Put model imports here
        if os.environ.get('RUN_MAIN'):
            print('start up from ready')


@receiver(connection_created)
def start_up(connection, **kwargs):
    with connection.cursor() as cursor:
        # do something to the database
        print('from start-up from connection signal')
    connection_created.disconnect(start_up)


