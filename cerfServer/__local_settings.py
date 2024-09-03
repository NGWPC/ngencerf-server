# This is a template for local_settings.py.
# It should be copied to local_settings.py and add your custom local settings for your environment (e.g., staging, production, etc.)
# local_settings.py should not be checked into git.  Only this template.
# The values in this template are suitable for use in Development.
# Any Django or other properties can be added to this file.  For secure values, such as passwords,
# you can reference os.getenv and store the value in the .env file or in the environment

import os

from pathlib import Path

from cerfServer.settings import LOGGING


print('Loading local settings from', __name__)

ALLOWED_HOSTS = ['.localhost', '127.0.0.1']

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# SQL logging
LOGGING['loggers']['django.db.backends']['level'] = 'INFO'

# Calibration logging
LOGGING['loggers']['calibration']['level'] = 'INFO'

# Regular logging
LOGGING['root']['level'] = 'INFO'

VERSION = 0.0
CONTACT_EMAIL = 'support@ngencerf.com'

HYDROFABRIC_URL = 'http://localhost:8888'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('CERF_SERVER_DATABASE_NAME', 'postgres'),
        'USER': os.getenv('CERF_SERVER_DATABASE_USER', 'postgres'),
        'PASSWORD': os.getenv('CERF_SERVER_DATABASE_PASSWORD', 'postgres'),
        'HOST': os.getenv('CERF_SERVER_DATABASE_HOST', 'localhost'),
        'PORT': 5432,
        'OPTIONS': {
            'connect_timeout': 10,
            'options': '-c statement_timeout=10000ms'
        }
    }
}

# url of the front-end
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
]

## FIXME: Do we still need the 3 settings below??? 
#  we should be using the ngen-cal container but are these path useful for other reasons???
## FIXME FIXME
# Locations for running ngen-cal
REPO_ROOT = os.getenv('REPO_ROOT', os.path.join(Path.home(), 'noaa-owp'))
# Directory that Ngen is cloned into
NGEN_REPO_ROOT = os.path.join(REPO_ROOT, 'ngen')
# directory that Ngen-cal is cloned into
NGEN_CAL_REPO_ROOT = os.path.join(REPO_ROOT, 'ngen-cal')

# This is the mount point for docker containers
NGEN_CAL_MOUNT_POINT = os.getenv('NGEN_CAL_MOUNT_POINT', os.path.join(Path.home(), 'ngwpc/data'))

NGEN_CAL_WORK_DIR = os.path.join(NGEN_CAL_MOUNT_POINT, 'ngen-cal-work')
# Directory where all the output runs are stored
NGEN_CAL_RUN_DIR = os.path.join(NGEN_CAL_WORK_DIR, 'run_calib')

## FIXME: Can we remove this setting???
# We should be using the ngen-cal container to run ngen-cal...
# is there another reason we would need this???
## FIXME FIXME
# Directory containing the ngen-cal virtual environment
NGEN_CAL_VENV = os.getenv('NGEN_CAL_VENV', None)
