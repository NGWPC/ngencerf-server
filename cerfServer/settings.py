"""
Django settings for cerfServer project.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/5.0/ref/settings/
"""
import codecs
import os
import re
from datetime import timedelta, datetime, timezone
from enum import StrEnum, auto

from datetimerange import DateTimeRange
from dotenv import load_dotenv

from calibration.enums_vanilla import JobExecutionMode, ScriptEnum, JobType

DJANGO_START_TIME = datetime.now(tz=timezone.utc)

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

BASE_DIR = str(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
print(f'Loading values from {dotenv_path}')
load_dotenv(dotenv_path)

version_path = os.path.join(BASE_DIR, 'version.env')
print(f'Loading values from {version_path}')
load_dotenv(version_path)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = str(os.getenv('DJANGO_DEBUG', 'true')).lower() == 'true'

NGENCERF_VERSION = os.getenv("NGENCERF_VERSION", "<unknown>")
NGENCERF_DATE = os.getenv("NGENCERF_DATE", "<unknown>")
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "<unknown>")
NGENCERF_COPYRIGHT = f"© 2024-{datetime.now().year}, RTX"

# used to find ngencerf-ui Docker image
NGENCERF_UI_TAG = os.getenv("NGENCERF_UI_TAG", "latest")

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv("CERF_SERVER_SECRET_KEY", "not-so-secret-key")

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django_dbconn_retry',
    'django.contrib.staticfiles',
    'drf_spectacular',
    'calibration.apps.CalibrationConfig',
    "rest_framework",
    "rest_framework.authtoken",
    "djoser",
    "rest_framework_simplejwt",
    'corsheaders',
]

# Points to which token model should be used for authentication. In case if only stateless
# tokens (e.g. JWT) are used in project it should be set to None.
TOKEN_MODEL = None

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.TokenAuthentication",
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'NgenCerf',
    'DESCRIPTION': 'Backend server for ngenCerf',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'calibration.util.middleware.TimingMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'calibration.util.middleware.LogUnmatchedCalibrationRequestsMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_currentuser.middleware.ThreadLocalUserMiddleware',
    'django.middleware.gzip.GZipMiddleware',
    'corsheaders.middleware.CorsMiddleware',
]

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3001",
]

ROOT_URLCONF = 'cerfServer.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.getenv('REDIS_URL', "redis://127.0.0.1:6379/1"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient"
        }
    }
}

AUTH_USER_MODEL = 'calibration.CustomUser'

DJOSER = {
    "SEND_CONFIRMATION_EMAIL": False,
    "SEND_ACTIVATION_EMAIL": False,
    "SET_PASSWORD_RETYPE": True,
    "UPDATE_LAST_LOGIN": True,
    "PASSWORD_RESET_CONFIRM_URL": "reset-password-confirm/{uid}/{token}",
    "SERIALIZERS": {
        "user_create": "calibration.user_serializers.CustomUserCreateSerializer",
        "user": "calibration.user_serializers.CustomUserSerializer",
        "current_user": "calibration.user_serializers.CustomUserSerializer",
    },
}

# https://django-rest-framework-simplejwt.readthedocs.io/en/latest/settings.html#settings
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'UPDATE_LAST_LOGIN': True,
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'TOKEN_OBTAIN_SERIALIZER': 'calibration.user_serializers.CustomTokenObtainPairSerializer',
}

WSGI_APPLICATION = 'cerfServer.wsgi.application'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'

# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ------------------------------------------------------------
# Messaging
# ------------------------------------------------------------
RABBITMQ_URL = os.getenv('RABBITMQ_URL')
RABBITMQ_JOBS_QUEUE = os.getenv("RABBITMQ_JOBS_QUEUE", "jobs_queue")
RABBITMQ_JOB_EVENTS_QUEUE = os.getenv("RABBITMQ_JOB_EVENTS_QUEUE", "job_events_queue")

# -----------------------------
# Enterprise Data
# -----------------------------
HYDROFABRIC_SOURCE = 'hf'
ENTERPRISE_DATA_MODULE_METADATA_ENDPOINT = 'api/v1/modules/parameter_metadata/'
ENTERPRISE_DATA_OBSERVATION_DATA_INFO_ENDPOINT = 'api/v1/streamflow_observations/{gage_id}/info'
ENTERPRISE_DATA_OBSERVATION_DATA_ENDPOINT = 'api/v1/streamflow_observations/{gage_id}/csv'

ENTERPRISE_DATA_URL = os.getenv('ENTERPRISE_DATA_URL')
ENTERPRISE_DATA_ENV = os.getenv('ENTERPRISE_DATA_ENV')

# Due to circular imports, can't use the enums as keys. But the values must match exactly
FORCING_DATA_DIRS_AORC = {
    "AORC": 's3://ngwpc-forcing/aorc_2.2',
    "NWM Retrospective": 's3://ngwpc-forcing/retrospective_2.2'
}
FORCING_DATA_DIRS_RETRO = {
    "NWM Retrospective": 's3://ngwpc-forcing/retrospective_2.2'
}

# Default time range for BMI forcing data
FORCING_BMI_DATE_RANGE = DateTimeRange("1980-01-01T00:00:00+0000", "2024-12-31T23:59:59+0000")
USE_BMI_FORCING = str(os.getenv('USE_BMI_FORCING', 'true')).lower() == 'true'

# Location of archive files
NGENCERF_ARCHIVE_S3_PATH = os.getenv('NGENCERF_ARCHIVE_S3_PATH')

# Location of download zip files on S3
NGENCERF_ZIPS_S3_PATH = os.getenv('NGENCERF_ZIPS_S3_PATH')

# AWS Profile to use for r/w buckets (.e.g, for archives and zips)
# Use None for AWS Dev (uses default profile)
NGENCERF_RW_PROFILE = os.getenv('NGENCERF_RW_PROFILE') or None

# Local temp directory for building ZIPs before upload (and for CLI zips)
ZIP_TEMP_DIR = os.path.join('/tmp', 'ngencerf-zips')
os.makedirs(ZIP_TEMP_DIR, exist_ok=True)

# How long a presigned download URL is valid
ZIP_DOWNLOAD_URL_TTL_SECONDS = 300

# How long the ZIP object is kept in S3 (and how long status is cached) before cleanup may delete it
ZIP_RETENTION_SECONDS = 3600

# -----------------------------
# Data / working directories
# -----------------------------
# Must match the repo root used in the docker container.
# It is not necessary for you to have local copies of the ngen and nwm-cal-mgr repos if you are using Docker
# But these directories still need to be set to reflect the directory of the repos in the docker container.
REPO_ROOT = '/ngen-app'
NGEN_REPO_ROOT = os.path.join(REPO_ROOT, 'ngen')

# This must match the data location in the ngen/nwm-cal-mgr docker
# Do not change this location.  You can put your data wherever you want, but you should then create a symbolic link to /ngencerf/data
# sudo mkdir /ngencerf
# sudo ln -s ~/your/data/dir /ngencerf/data
NGEN_CAL_MOUNT_POINT = '/ngencerf/data'
NGEN_CAL_DATA_PATH = os.getenv('NGEN_CAL_DATA_PATH', NGEN_CAL_MOUNT_POINT)

NGEN_LOGGING_DIR = os.path.join(BASE_DIR, 'logs')
print(f"Logging files will be created in {NGEN_LOGGING_DIR}")
os.makedirs(NGEN_LOGGING_DIR, exist_ok=True)

# Static and working directories
NGEN_STATIC_DIR = os.path.join(NGEN_CAL_MOUNT_POINT, 'ngen-static-files')
NGEN_CAL_WORK_DIR = os.path.join(NGEN_CAL_MOUNT_POINT, 'ngen-cal-work')
NGEN_VERIFICATION_WORK_DIR = os.path.join(NGEN_CAL_MOUNT_POINT, 'verification_work')

# The NGEN_BMI_FORCING_WORK_DIR directory is owned by ngen-forcing.  It will be responsible for creating it
NGEN_BMI_FORCING_WORK_DIR = os.path.join(NGEN_CAL_MOUNT_POINT, 'bmi_forcing_work')


# Directory where all the output runs are stored
NGEN_CAL_RUN_DIR = os.path.join(NGEN_CAL_WORK_DIR, 'run_calib')


JOB_EXECUTION_MODE_STR = os.getenv('JOB_EXECUTION_MODE', JobExecutionMode.DOCKER.name)
try:
    # noinspection PyTypeHints
    JOB_EXECUTION_MODE = JobExecutionMode[JOB_EXECUTION_MODE_STR]
except KeyError:
    # noinspection PyUnresolvedReferences
    raise SystemExit(
        f"Invalid environment value for JOB_EXECUTION_MODE: {JOB_EXECUTION_MODE_STR}.  Must be one of {', '.join([e.name for e in JobExecutionMode])}")

# -----------------------------
# Slurm
# -----------------------------
# These remain in Django because the server still performs
# status reconciliation and cancel operations against Slurm.
SLURM_URL = os.getenv("SLURM_URL")
SLURM_JOB_STATUS_ENDPOINT = 'job-status'
SLURM_CANCEL_JOB_ENDPOINT = 'cancel-job'

# -----------------------------
# Logging
# -----------------------------
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,

    # Root Logger: Sends everything to the console and file
    'root': {
        'handlers': ['console', 'file_dev'],
        'level': 'DEBUG'
    },

    'formatters': {
        'dev_format': {
            'format': '{asctime}.{msecs:03.0f} {module:15s} {levelname:8s} {funcName} {message}',
            'datefmt': '%Y-%m-%dT%H:%M:%S',
            'style': '{',
        },
        'simple': {
            'format': '{asctime}.{msecs:03.0f} {module:15s} {levelname:8s} {funcName} {message}',
            'datefmt': '%Y-%m-%dT%H:%M:%S',
            'style': '{',
        },
    },

    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file_dev': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': os.path.join(NGEN_LOGGING_DIR, 'ngencerf.log'),
            'formatter': 'dev_format',
            'encoding': 'utf-8',
        },
        'file_db': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': os.path.join(NGEN_LOGGING_DIR, 'ngencerf_db.log'),
            'formatter': 'dev_format',
            'encoding': 'utf-8',
        },
    },

    'loggers': {
        'django.db.backends': {
            'handlers': ['file_db'],
            'level': 'DEBUG',
            'propagate': False,  # Prevents these logs from reaching the root logger (avoids duplication)
        },
        'django': {
            'handlers': ['console', 'file_dev'],
            'level': 'INFO',
            'propagate': False,  # Prevents these logs from reaching the root logger (avoids duplication)
        },
        'djoser': {
            'handlers': ['console', 'file_dev'],
            'level': 'INFO',
            'propagate': False,  # Prevents these logs from reaching the root logger (avoids duplication)
        },
        'rest_framework_simplejwt': {
            'handlers': ['console', 'file_dev'],
            'level': 'DEBUG',
            'propagate': False,  # Prevents these logs from reaching the root logger (avoids duplication)

        },
        'django.request': {
            'handlers': ['console', 'file_dev'],
            'level': 'INFO',
            'propagate': False,  # Prevents these logs from reaching the root logger (avoids duplication)
        },
        'django_dbconn_retry': {
            'handlers': ['console', 'file_dev'],
            'level': 'DEBUG',
            'propagate': False,
        },
        # Add these loggers for 'requests' and 'urllib3'
        'requests': {
            'handlers': ['console', 'file_dev'],
            'level': 'INFO',
            'propagate': False,  # Prevents these logs from reaching the root logger (avoids duplication)
        },
        'urllib3': {
            'handlers': ['console', 'file_dev'],
            'level': 'INFO',
            'propagate': False,  # Prevents these logs from reaching the root logger (avoids duplication)
        },
        'calibration': {
            'handlers': ['console', 'file_dev'],
            'level': 'DEBUG',
            'propagate': False,  # Prevents these logs from reaching the root logger (avoids duplication)
        },
        'cerfServer': {
            'handlers': ['console', 'file_dev'],
            'level': 'DEBUG',
            'propagate': False,  # Prevents these logs from reaching the root logger (avoids duplication)
        }
    }
}

# This needs to be at the end of settings.py
try:
    from .local_settings import *

    print("Loaded local_settings.py successfully.")
except ImportError as e:
    print('local_settings.py not found or could not be imported:', e)
