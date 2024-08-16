# This is a template for local_settings.py.
# It should be copied to local_settings.py and add your custom local settings for your environment (e.g., staging, production, etc.)
# local_settings.py should not be checked into git.  Only this template.
# The values in this template are suitable for use in Development.
# Any Django or other properties can be added to this file.  For secure values, such as passwords,
# you can reference os.getenv and store the value in the .env file or in the environment

import os

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
        'NAME': 'postgres',
        'USER': 'postgres',
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
