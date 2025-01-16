import logging
import os
import time
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import QuerySet

from calibration.models import CalibrationParameter, ModuleOutputVariable, CalibrationFormulation, CalibrationRun
from calibration.util.aws_util import convert_s3_uri_to_fs
from calibration.util.caching import get_cached_module_by_name
from calibration.util.calibration_validators import ModuleDataListSerializer, S3FileValidator, \
    S3DirectoryValidator
from calibration.util.file_util import copy_directory
from calibration.util.ngen_locations import get_bmi_config_dir_for_module
from calibration.views.common import validate_response_data
from data_services_test_data import data_services_test_data

logger = logging.getLogger(__name__)

default_headers = {
    "Content-Type": "application/json"
}


def fetch_from_data_services(method: str, url: str, headers: dict = None, payload: dict = None) -> dict:
    """
    A generic function to handle HTTP requests to Data Services and handle exceptions.

    :param method: HTTP method (e.g., 'GET' or 'POST')
    :param url: The full URL to send the request to.
    :param headers: Optional HTTP headers to include.
    :param payload: Optional JSON payload for POST requests.
    :return: The response JSON data as a dictionary.
    :raises: DataServicesException for any HTTP or connection-related errors.
    """
    status_code = None
    response_text = None
    logger.info(f'Sending request to {url}')
    if payload:
        logger.info(f"Data Services payload: {payload}")

    try:
        start_time = time.time()  # Record the start time

        if method == 'GET':
            response = requests.get(url, headers=headers)
        elif method == 'POST':
            response = requests.post(url, headers=headers, json=payload)
        else:
            raise DataServicesException(f"Unsupported HTTP method: {method}")

        elapsed_time = time.time() - start_time  # Calculate the elapsed time
        minutes, seconds = divmod(elapsed_time, 60)  # Convert to minutes and seconds
        logger.info(f"Request to {url} took {int(minutes)}:{int(seconds):02} (minutes:seconds).")

        # Capture status code and response content before raising an exception
        status_code = response.status_code
        response_text = response.text

        # Log the response for debugging in case of errors
        if 400 <= status_code < 500:
            logger.error(f"Client error while accessing {url}: {status_code} - {response_text}")
        elif 500 <= status_code:
            logger.error(f"Server error while accessing {url}: {status_code} - {response_text}")

        # Check if the response is HTML (indicating an error page)
        content_type = response.headers.get('Content-Type', '')
        if 'text/html' in content_type:
            logger.warning(f"Received HTML response from {url} - truncating output")
            response_text = response_text[:500] + '... (truncated)'
            raise DataServicesException(f"Call to {url} returned HTML. Response text: {response_text}", status_code)

        response.raise_for_status()  # Raise HTTPError for bad responses

        # Parse and validate the response JSON
        response_data = response.json()

        # Ensure the response is a dictionary
        if not isinstance(response_data, dict):
            raise DataServicesException(
                f"Unexpected response format: Expected a dictionary but got {type(response_data).__name__}. Response: {response_data}"
            )

        return response_data

    except requests.exceptions.HTTPError as e:
        message = f"Call to {url} failed with {status_code}. Response text: {response_text if response_text else 'No response received'}"
        logger.error(message)
        raise DataServicesException(message, status_code) from e

    except requests.exceptions.RequestException as e:
        # Handle connection, timeout, or other request errors
        message = f"Call to {url} failed to connect or timed out"
        logger.error(message)
        raise DataServicesException(message) from e

    except ValueError as e:
        # Handle invalid JSON responses
        logger.error(f"Invalid JSON response from {url}: {response_text}")
        raise DataServicesException("Invalid JSON received from Data Services") from e


class DataServicesException(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def get_geopackage_from_data_services(run: CalibrationRun):
    if run.gage:
        if settings.ENTERPRISE_DATA_GEOPACKAGE_ENDPOINT[0]:
            logger.info('Getting geopackage from Data Services')
            url = urljoin(settings.ENTERPRISE_DATA_URL, settings.ENTERPRISE_DATA_GEOPACKAGE_ENDPOINT[1].format(
                gage_id=run.gage.gage_id,
                source=run.gage.agency,
                domain=run.gage.domain.name,
                version=settings.ENTERPRISE_DATA_VERSION
            ))
            geopackage_json = fetch_from_data_services('GET', url, headers=default_headers)
        else:
            logger.info('Getting dummy geopackage data')
            geopackage_json = data_services_test_data.geopackage_sample_data

        eds_data = validate_response_data(S3FileValidator, geopackage_json, 'Geopackage data from Data Services is not in the expected format')

        s3_uri = eds_data.get('uri')
        run.geopackage_eds_file_path = convert_s3_uri_to_fs(s3_uri)
        logger.info(f'Setting run.geopackage_eds_file_path to {run.geopackage_eds_file_path}')


def get_observational_data_from_data_services(run: CalibrationRun):
    if settings.ENTERPRISE_DATA_OBSERVATION_DATA_ENDPOINT[0]:
        logger.info('Getting observational data from Data Services')
        url = urljoin(settings.ENTERPRISE_DATA_URL,
                      settings.ENTERPRISE_DATA_OBSERVATION_DATA_ENDPOINT[1].format(gage_id=run.gage.gage_id,
                                                                                   agency=run.gage.agency,
                                                                                   domain=run.gage.domain.name))
        observational_json = fetch_from_data_services('GET', url, headers=default_headers)
    else:
        logger.info('Getting dummy observational data')
        observational_json = data_services_test_data.observational_sample_data

    observational_data = validate_response_data(S3FileValidator, observational_json,
                                                'Observational data from Data Services is not in the expected format')

    s3_uri = observational_data.get('uri')

    run.observational_eds_file_path = convert_s3_uri_to_fs(s3_uri)
    # Invalidate the dates, since we'll have to compute the intersection again
    run.time_range_start = None
    run.time_range_end = None
    logger.info(f'Setting run.observational_eds_file_path to {run.observational_eds_file_path}')


def get_forcing_data_from_data_services(run: CalibrationRun):
    if settings.ENTERPRISE_DATA_FORCING_DATA_ENDPOINT[0]:
        logger.info('Getting forcing data from Data Services')
        url = urljoin(settings.ENTERPRISE_DATA_URL, settings.ENTERPRISE_DATA_FORCING_DATA_ENDPOINT[1].format(gage_id=run.gage.gage_id))
        forcing_json = fetch_from_data_services('GET', url, headers=default_headers)
    else:
        get_forcing_data_from_s3(run)
        return
        # logger.info('Getting dummy forcing data')
        # forcing_json = data_services_test_data.forcing_sample_data

    forcing_data = validate_response_data(S3DirectoryValidator, forcing_json, 'Forcing data from Data Services is not in the expected format')

    s3_uri = forcing_data.get('uri')

    run.forcing_eds_dir_path = convert_s3_uri_to_fs(s3_uri)
    # Invalidate the dates, since we'll have to compute the intersection again
    run.time_range_start = None
    run.time_range_end = None
    logger.info(f'Setting run.forcing_eds_dir_path to {run.forcing_eds_dir_path}')


def get_forcing_data_from_s3(run: CalibrationRun):
    for s3_uri in settings.FORCING_DATA_DIRS:
        dir_path = convert_s3_uri_to_fs(s3_uri)
        gage_dir = os.path.join(dir_path, run.gage.domain.name, f"Gage_{run.gage.gage_id}")
        if os.path.isdir(gage_dir):
            logger.info(f"Found forcing directory {gage_dir}")
            run.forcing_eds_dir_path = gage_dir
            # Invalidate the dates, since we'll have to compute the intersection again
            run.time_range_start = None
            run.time_range_end = None
            logger.info(f'Setting run.forcing_eds_dir_path to {run.forcing_eds_dir_path}')
            return
        else:
            logger.info(f"Forcing directory doesn't exist {gage_dir}")

    raise DataServicesException(f"Could not find forcing data for {run.gage.gage_id}")


def get_module_metadata_from_data_services(run: CalibrationRun, calibration_formulations: QuerySet[CalibrationFormulation],
                                           gage_changed: bool = False):
    gage = run.gage
    # gage_changed = False means that the modules changed.  If true, then the gage changed and we want to retain min/max

    my_module_names = list(calibration_formulations.values_list('module__name', flat=True))

    if settings.ENTERPRISE_DATA_MODULE_METADATA_ENDPOINT[0]:
        logger.info('Getting module metadata from Data Services')
        url = urljoin(settings.ENTERPRISE_DATA_URL, settings.ENTERPRISE_DATA_MODULE_METADATA_ENDPOINT[1])

        module_json = fetch_from_data_services('POST', url, headers=default_headers,
                                               payload={'modules': my_module_names,
                                                        'gage_id': gage.gage_id,
                                                        'domain': gage.domain.name,
                                                        'source': gage.agency,
                                                        'version': settings.ENTERPRISE_DATA_VERSION})
    else:
        logger.info('Getting dummy module metadata')
        module_json = data_services_test_data.eds_module_metadata_real_data

    module_metadata = validate_response_data(ModuleDataListSerializer, module_json,
                                             'Module metadata from Data Services is not in the expected format')

    fix_module_metadata(module_metadata)

    eds_module_names = set([module['module_name'] for module in module_metadata['modules']])

    my_module_names = set(my_module_names)
    missing_names = my_module_names - eds_module_names

    extra_names = eds_module_names - my_module_names

    # Save the output variables and parameters for each module
    with transaction.atomic():
        for module in module_metadata.get('modules'):
            if module['module_name'] in extra_names:
                # Ignore any extra names that Data Services sent us
                logger.warning(f'Ignore extra module from Data Services - {module["module_name"]}')
                continue

            module_instance = get_cached_module_by_name(module['module_name'])

            # Get the modules object from our list
            calibration_formulation = calibration_formulations.get(module=module_instance)

            # Copy bmi-config to our directory
            bmi_config = convert_s3_uri_to_fs(module['parameter_file']['uri'])
            copy_directory(bmi_config, get_bmi_config_dir_for_module(run, module['module_name']))

            # Save output variables
            outputs = module['output_variables']
            o: dict
            for o in outputs:
                ModuleOutputVariable.objects.update_or_create(
                    name=o['variable'],
                    calibration_formulation=calibration_formulation,
                    # TODO Fix this.  Description is required
                    defaults={'description': o['description'] if o['description'] else 'placeholder description'}
                )
            # Save parameters
            parameters = module['calibrate_parameters']
            for p in parameters:
                # Data Services gives us initial_value, min and max as Strings because sometimes crap appears in them.

                # Using get_or_create because we don't want to override any values the user has already entered
                calibration_parameter, created = CalibrationParameter.objects.get_or_create(
                    name=p['name'],
                    calibration_formulation=calibration_formulation,
                    defaults={'data_type': p['data_type'],
                              'description': p['description'],
                              'initial_value': str_to_float(p['initial_value']),
                              'minimum': str_to_float(p['min']),
                              'maximum': str_to_float(p['max']),
                              'units': p['units']
                              }
                )
                if gage_changed and not created:
                    logger.info(
                        f"Changing initial value for parameter {p['name']} for module {calibration_formulation.module.name}")
                    # We want to over-write the initial_value from Data Services
                    calibration_parameter.initial_value = str_to_float(p['initial_value'])
                    calibration_parameter.save(update_fields=['initial_value'])

    if missing_names:
        raise DataServicesException(f'Response from Data Services is missing entries for {missing_names}')

    return


translation_map = {
    "soil_params.b": "b",
    "soil_params.satdk": "satdk",
    "soil_params.satpsi": "satpsi",
    "soil_params.slop": "slope",
    "soil_params.smcmax": "smcmax",
    "CWPVT": "CWP",
    "K_lf": "Klf",
    "K_nash": "Kn"
}


def fix_module_metadata(metadata):
    # Apply translations
    for module in metadata['modules']:
        for param in module["calibrate_parameters"]:
            old_name = param["name"]
            # Check if the old_name needs translation
            if old_name in translation_map:
                param["name"] = translation_map[old_name]


def str_to_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None
