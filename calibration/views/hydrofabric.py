import json
import logging
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import QuerySet

from calibration.models import CalibrationParameter, ModuleOutputVariable, CalibrationFormulation, CalibrationRun
from calibration.util.aws_util import convert_s3_uri_to_fs
from calibration.util.calibration_validators import ModuleDataHydrofabricListSerializer, ModuleHydrofabricListSerializer, S3FileValidator, \
    S3DirectoryValidator
from calibration.views.common import CerfException
from hydrofabric_test_data.hydrofabric_test_data import geopackage_sample_data, observational_sample_data, hydrofabric_module_metadata_real_data, \
    module_sample_data

logger = logging.getLogger(__name__)

headers = {
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
    if settings.HYDROFABRIC_GEOPACKAGE_ENDPOINT[0]:
        logger.info('Getting geopackage from Hydrofabric')
        url = urljoin(settings.HYDROFABRIC_URL, settings.HYDROFABRIC_GEOPACKAGE_ENDPOINT[1].format(gage_id=run.gage.gage_id, agency=run.gage.agency,
                                                                                                   domain=run.gage.domain.name))
        geopackage_json = fetch_from_hydrofabric('GET', url, headers=headers)
    else:
        logger.info('Getting dummy geopackage data')
        geopackage_json = geopackage_sample_data

    hydrofabric_data = validate_response_data(S3FileValidator, geopackage_json,
                                              'Geopackage data from Hydrofabric is not in the expected format')

    s3_uri = hydrofabric_data.get('uri')
    run.geopackage_hydrofabric_file_path = convert_s3_uri_to_fs(s3_uri)
    logger.info(f'Setting run.geopackage_hydrofabric_path to {run.geopackage_hydrofabric_file_path}')


def get_observational_data_from_hydrofabric(run: CalibrationRun):
    if settings.HYDROFABRIC_OBSERVATION_DATA_ENDPOINT[0]:
        logger.info('Getting observational data from Hydrofabric')
        url = urljoin(settings.HYDROFABRIC_URL,
                      settings.HYDROFABRIC_OBSERVATION_DATA_ENDPOINT[1].format(gage_id=run.gage.gage_id, agency=run.gage.agency,
                                                                               domain=run.gage.domain.name))
        observational_json = fetch_from_hydrofabric('GET', url, headers=headers)
    else:
        logger.info('Getting dummy observational data')
        observational_json = observational_sample_data

    observational_data = validate_response_data(S3FileValidator, observational_json,
                                                'Observational data from Hydrofabric is not in the expected format')

    s3_uri = observational_data.get('uri')

    run.observational_hydrofabric_file_path = convert_s3_uri_to_fs(s3_uri)
    logger.info(f'Setting run.observational_hydrofabric_file_path to {run.observational_hydrofabric_file_path}')


def get_forcing_data_from_hydrofabric(run: CalibrationRun):
    if settings.HYDROFABRIC_FORCING_DATA_ENDPOINT[0]:
        logger.info('Getting forcing data from Hydrofabric')
        url = urljoin(settings.HYDROFABRIC_URL, settings.HYDROFABRIC_FORCING_DATA_ENDPOINT[1].format(gage_id=run.gage.gage_id))
        forcing_json = fetch_from_hydrofabric('GET', url, headers=headers)
    else:
        logger.info('Getting dummy module metadata data')
        forcing_json = hydrofabric_module_metadata_real_data

    forcing_data = validate_response_data(S3DirectoryValidator, forcing_json, 'Forcing data from Hydrofabric is not in the expected format')

    s3_uri = forcing_data.get('uri')

    run.forcing_hydrofabric_dir_path = convert_s3_uri_to_fs(s3_uri)
    logger.info(f'Setting run.forcing_hydrofabric_dir_path to {run.forcing_hydrofabric_dir_path}')


def get_module_metadata_from_hydrofabric(run: CalibrationRun, modules: QuerySet[CalibrationFormulation]):
    module_names = list(modules.values_list('name', flat=True))

    if settings.HYDROFABRIC_MODULE_METADATA_ENDPOINT[0]:
        logger.info('Getting module metadata from Hydrofabric')
        url = urljoin(settings.HYDROFABRIC_URL, settings.HYDROFABRIC_MODULE_METADATA_ENDPOINT[1])
        # TODO need them to return an object

        module_json = {'modules': fetch_from_hydrofabric('POST', url, headers=headers, payload={'modules': module_names, 'gage_id': run.gage.gage_id})}
    else:
        logger.info('Getting dummy module metadata data')
        module_json = hydrofabric_module_metadata_real_data

    module_data = validate_response_data(ModuleDataHydrofabricListSerializer, module_json,
                                         'Module metadata from Hydrofabric is not in the expected format')

    hydrofabric_module_names = set([module['module_name'] for module in module_data['modules']])
    # print('hydrofabric_module_names:', hydrofabric_module_names)

    module_names = set(module_names)
    missing_names = module_names - hydrofabric_module_names
    if missing_names:
        # TODO Needs to be an exception
        # raise CerfException(f'Response from Hydrofabric is missing entries for {missing_names}')
        pass
    extra_names = hydrofabric_module_names - module_names
    if extra_names:
        logger.error(f'Response from Hyrofabric has extra entries for {extra_names}')

    # Save the output variables and parameters for each module
    with transaction.atomic():
        for m in module_data.get('modules'):
            if m['module_name'] in extra_names:
                # Ignore any extra names that Hydrofabric sent us
                continue
            # Get the modules object from our list
            module = modules.filter(name=m['module_name']).first()

            # Save the config
            # print('parameter url', convert_s3_uri_to_fs(m['parameter_file']['url']))
            module.bmi_config_path = convert_s3_uri_to_fs(m['parameter_file']['uri'])
            module.save(update_fields=['bmi_config_path'])

            # Save output variables
            outputs = m['output_variables']
            o: dict
            for o in outputs:
                ModuleOutputVariable.objects.update_or_create(
                    name=o['variable'],
                    calibration_formulation=module,
                    # TODO Fix this.  Description is required
                    defaults={'description': o['description'] if o['description'] else 'placeholder description'}
                )
            # Save parameters
            parameters = m['calibrate_parameters']
            # print('parameters from Hydro', parameters)
            for p in parameters:
                # Hydrofabric gives us initial_value, min and max as Strings because sometimes crap appears in them.

                # Using get_or_create because we don't want to override any values the user has already entered
                CalibrationParameter.objects.get_or_create(
                    name=p['name'],
                    calibration_formulation=module,
                    defaults={'data_type': p['data_type'],
                              'description': p['description'],
                              'initial_value': str_to_float(p['initial_value']),
                              'minimum': str_to_float(p['minimum']),
                              'maximum': str_to_float(p['maximum']),
                              'units': p['units']
                              }
                )

        # run.got_module_data_from_hydrofabric = True
        run.save()

    return


def get_modules_from_hydrofabric(run: CalibrationRun):
    if settings.HYDROFABRIC_MODULES_ENDPOINT[0]:
        logger.info('Getting module data from Hydrofabric')
        url = urljoin(settings.HYDROFABRIC_URL, settings.HYDROFABRIC_MODULES_ENDPOINT[1])
        module_json = fetch_from_hydrofabric('GET', url, headers=headers)
    else:
        logger.info('Getting dummy module data')
        module_json = module_sample_data

    current_module_names = set(
        CalibrationFormulation.objects.filter(calibration_run=run)
        .values_list('name', flat=True)
    )

    print('current_module_names', current_module_names)

    module_data = validate_response_data(ModuleHydrofabricListSerializer, module_json, 'Module data from Hydrofabric is not in the expected format')

    module_data = module_data.get('modules')
    new_modules_names = set(map(lambda mod: mod['module_name'], module_data))
    print('new_modules_names', new_modules_names)

    with transaction.atomic():
        if current_module_names != new_modules_names:
            # Delete only if the modules names have changed
            to_be_deleted = current_module_names - new_modules_names

            if to_be_deleted:
                CalibrationFormulation.objects.filter(calibration_run=run, name__in=to_be_deleted).delete()

            # Create the new ones, if they don't already exist
            new_modules = []
            for m in module_data:
                if m['module_name'] not in current_module_names:
                    new_modules.append(CalibrationFormulation(
                        name=m['module_name'],
                        calibration_run=run,
                        groups=json.dumps(m['groups']),
                        description=m['description']
                    ))
            # Use bulk_create to minimize the number of insert queries
            if new_modules:
                CalibrationFormulation.objects.bulk_create(new_modules)

    return


def validate_response_data(serializer_class, data, error_message):
    validator = serializer_class(data=data)
    if not validator.is_valid():
        logger.debug(validator.errors)
        raise CerfException(f'{error_message} - {validator.errors}')
    return validator.data


def str_to_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None
