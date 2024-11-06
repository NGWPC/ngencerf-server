import logging
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import QuerySet

from calibration.models import CalibrationParameter, ModuleOutputVariable, CalibrationFormulation, CalibrationRun, Gage
from calibration.util.aws_util import convert_s3_uri_to_fs
from calibration.util.calibration_validators import ModuleDataHydrofabricListSerializer, S3FileValidator, \
    S3DirectoryValidator
from calibration.views.common import validate_response_data
from calibration.util.caching import get_cached_module_by_name
from hydrofabric_test_data import hydrofabric_test_data

logger = logging.getLogger(__name__)

default_headers = {
    "Content-Type": "application/json"
}


def fetch_from_hydrofabric(method, url, headers=None, payload=None):
    """
    A generic function to handle HTTP requests to the Hydrofabric and handle exceptions.

    :param method: HTTP method (e.g., 'GET' or 'POST')
    :param url: The full URL to send the request to
    :param headers: Optional HTTP headers to include
    :param payload: Optional JSON payload for POST requests
    :return: The response JSON data
    :raises: HydrofabricException for any HTTP or connection-related errors
    """
    # response = None
    status_code = None
    response_text = None
    if payload:
        logger.info(f"Hydrofabric payload: {payload}")
    try:
        if method == 'GET':
            response = requests.get(url, headers=headers)
        elif method == 'POST':
            response = requests.post(url, headers=headers, json=payload)
        else:
            raise HydrofabricException(f"Unsupported HTTP method: {method}")

        # Capture status code and response content before raising an exception
        status_code = response.status_code
        response_text = response.text

        # Check if the response is HTML (indicating an error page)
        content_type = response.headers.get('Content-Type', '')
        if 'text/html' in content_type:
            logger.warning(f"Received HTML response from {url} - truncating output")
            response_text = response_text[:500] + '... (truncated)'
            raise HydrofabricException(f"Call to {url} returned HTML. Response text: {response_text}", status_code)

        response.raise_for_status()  # Raise HTTPError for bad responses
        return response.json()

    except requests.exceptions.HTTPError as e:
        message = f"Call to {url} failed with {status_code}. Response text: {response_text if response_text else 'No response received'}"
        logger.error(message)
        raise HydrofabricException(message, status_code) from e

    except requests.exceptions.RequestException as e:
        # Handle connection, timeout, or other request errors
        message = f"Call to {url} failed to connect or timed out"
        logger.error(message)
        raise HydrofabricException(message) from e


class HydrofabricException(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def get_geopackage_from_hydrofabric(run: CalibrationRun):
    if run.gage:
        if settings.HYDROFABRIC_GEOPACKAGE_ENDPOINT[0]:
            logger.info('Getting geopackage from Hydrofabric')
            url = urljoin(settings.HYDROFABRIC_URL, settings.HYDROFABRIC_GEOPACKAGE_ENDPOINT[1].format(gage_id=run.gage.gage_id,
                                                                                                       source=run.gage.agency,
                                                                                                       domain=run.gage.domain.name))
            geopackage_json = fetch_from_hydrofabric('GET', url, headers=default_headers)
        else:
            logger.info('Getting dummy geopackage data')
            geopackage_json = hydrofabric_test_data.geopackage_sample_data

        hydrofabric_data = validate_response_data(S3FileValidator, geopackage_json,
                                                  'Geopackage data from Hydrofabric is not in the expected format')

        s3_uri = hydrofabric_data.get('uri')
        run.geopackage_hydrofabric_file_path = convert_s3_uri_to_fs(s3_uri)
        logger.info(f'Setting run.geopackage_hydrofabric_path to {run.geopackage_hydrofabric_file_path}')


def get_observational_data_from_hydrofabric(run: CalibrationRun):
    if settings.HYDROFABRIC_OBSERVATION_DATA_ENDPOINT[0]:
        logger.info('Getting observational data from Hydrofabric')
        url = urljoin(settings.HYDROFABRIC_URL,
                      settings.HYDROFABRIC_OBSERVATION_DATA_ENDPOINT[1].format(gage_id=run.gage.gage_id,
                                                                               agency=run.gage.agency,
                                                                               domain=run.gage.domain.name))
        observational_json = fetch_from_hydrofabric('GET', url, headers=default_headers)
    else:
        logger.info('Getting dummy observational data')
        observational_json = hydrofabric_test_data.observational_sample_data

    observational_data = validate_response_data(S3FileValidator, observational_json,
                                                'Observational data from Hydrofabric is not in the expected format')

    s3_uri = observational_data.get('uri')

    run.observational_hydrofabric_file_path = convert_s3_uri_to_fs(s3_uri)
    logger.info(f'Setting run.observational_hydrofabric_file_path to {run.observational_hydrofabric_file_path}')


def get_forcing_data_from_hydrofabric(run: CalibrationRun):
    if settings.HYDROFABRIC_FORCING_DATA_ENDPOINT[0]:
        logger.info('Getting forcing data from Hydrofabric')
        url = urljoin(settings.HYDROFABRIC_URL, settings.HYDROFABRIC_FORCING_DATA_ENDPOINT[1].format(gage_id=run.gage.gage_id))
        forcing_json = fetch_from_hydrofabric('GET', url, headers=default_headers)
    else:
        logger.info('Getting dummy forcing data')
        forcing_json = hydrofabric_test_data.forcing_sample_data

    forcing_data = validate_response_data(S3DirectoryValidator, forcing_json, 'Forcing data from Hydrofabric is not in the expected format')

    s3_uri = forcing_data.get('uri')

    run.forcing_hydrofabric_dir_path = convert_s3_uri_to_fs(s3_uri)
    logger.info(f'Setting run.forcing_hydrofabric_dir_path to {run.forcing_hydrofabric_dir_path}')


def get_module_metadata_from_hydrofabric(gage: Gage, calibration_formulations: QuerySet[CalibrationFormulation], gage_changed: bool = False):
    # gage_changed = False means that the modules changed.  If true, then the gage changed and we want to retain min/max

    my_module_names = list(calibration_formulations.values_list('module__name', flat=True))

    if settings.HYDROFABRIC_MODULE_METADATA_ENDPOINT[0]:
        logger.info('Getting module metadata from Hydrofabric')
        url = urljoin(settings.HYDROFABRIC_URL, settings.HYDROFABRIC_MODULE_METADATA_ENDPOINT[1])

        module_json = fetch_from_hydrofabric('POST', url, headers=default_headers,
                                             payload={'modules': my_module_names,
                                                      'gage_id': gage.gage_id,
                                                      'domain': gage.domain.name,
                                                      'source': gage.agency})
    else:
        logger.info('Getting dummy module metadata')
        module_json = hydrofabric_test_data.hydrofabric_module_metadata_real_data

    module_metadata = validate_response_data(ModuleDataHydrofabricListSerializer, module_json,
                                             'Module metadata from Hydrofabric is not in the expected format')

    m = module_metadata['modules'][0]
    p = m['calibrate_parameters']
    print('before', p)
    fix_module_metadata(module_metadata)
    m = module_metadata['modules'][0]
    p = m['calibrate_parameters']
    print('after', p)

    hydrofabric_module_names = set([module['module_name'] for module in module_metadata['modules']])

    my_module_names = set(my_module_names)
    missing_names = my_module_names - hydrofabric_module_names

    extra_names = hydrofabric_module_names - my_module_names

    # Save the output variables and parameters for each module
    with transaction.atomic():
        for module in module_metadata.get('modules'):
            if module['module_name'] in extra_names:
                # Ignore any extra names that Hydrofabric sent us
                logger.warning(f'Ignore extra module from Hydrofabric - {module["module_name"]}')
                continue

            module_instance = get_cached_module_by_name(module['module_name'])

            # Get the modules object from our list
            calibration_formulation = calibration_formulations.get(module=module_instance)

            # Save the config
            calibration_formulation.bmi_config_path = convert_s3_uri_to_fs(module['parameter_file']['uri'])
            calibration_formulation.save(update_fields=['bmi_config_path'])

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
                # Hydrofabric gives us initial_value, min and max as Strings because sometimes crap appears in them.

                # Using get_or_create because we don't want to override any values the user has already entered
                calibration_parameter, created = CalibrationParameter.objects.get_or_create(
                    name=p['name'],
                    calibration_formulation=calibration_formulation,
                    defaults={'data_type': p['data_type'],
                              'description': p['description'],
                              'initial_value': str_to_float(p['initial_value']),
                              'minimum': str_to_float(p['minimum']),
                              'maximum': str_to_float(p['maximum']),
                              'units': p['units']
                              }
                )
                if gage_changed and not created:
                    logger.info(
                        f"Changing initial value for parameter {p['name']} for module {calibration_formulation.module.name}")
                    # We want to over-write the initial_value from Hydrofabric
                    calibration_parameter.initial_value = str_to_float(p['initial_value'])
                    calibration_parameter.save(update_fields=['initial_value'])

    if missing_names:
        raise HydrofabricException(f'Response from Hydrofabric is missing entries for {missing_names}')

    return


translation_map = {
    "soil_params.b": "b",
    "soil_params.satdk": "satdk",
    "soil_params.satpsi": "satpsi",
    "soil_params.slop": "slop",
    "soil_params.smcmax": "smcmax"
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
