import logging
import os
import time
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import QuerySet

from calibration.enums import JobGenesis
from calibration.models import CalibrationParameter, ModuleOutputVariable, CalibrationFormulation, CalibrationRun
from calibration.util.aws_util import convert_s3_uri_to_fs
from calibration.util.caching import get_cached_module_by_name
from calibration.util.calibration_validators import ModuleDataListSerializer, S3FileValidator, S3DirectoryValidator
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
    Sends an HTTP request to Data Services and processes the response.

    :param method: HTTP method (e.g., 'GET' or 'POST')
    :param url: The full URL of the Data Services endpoint.
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
        start_time = time.time()  # Record the start time for performance tracking

        # Send the appropriate HTTP request based on the method
        if method == 'GET':
            response = requests.get(url, headers=headers)
        elif method == 'POST':
            response = requests.post(url, headers=headers, json=payload)
        else:
            raise DataServicesException(f"Unsupported HTTP method: {method}")

        # Log the time taken for the request
        elapsed_time = time.time() - start_time
        minutes, seconds = divmod(elapsed_time, 60)  # Convert to minutes and seconds
        logger.info(f"Request to {url} took {int(minutes)}:{int(seconds):02} (minutes:seconds).")

        # Capture status code and response content before raising an exception
        status_code = response.status_code
        response_text = response.text

        # Handle potential errors based on the status code
        if 400 <= status_code < 500:
            logger.error(f"Client error while accessing {url}: {status_code} - {response_text}")
        elif 500 <= status_code:
            logger.error(f"Server error while accessing {url}: {status_code} - {response_text[:1000] + '... (truncated)'}")

        # Check if the response is HTML instead of JSON (indicating an error page)
        content_type = response.headers.get('Content-Type', '')
        if 'text/html' in content_type:
            msg = f"Call to {url} returned HTML error from Data Services"
            logger.error(msg)
            raise DataServicesException(msg, status_code)

        response.raise_for_status()  # Raise HTTPError for bad responses

        # Parse the response JSON and validate its format
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
    """
    Custom exception for errors related to Data Services.
    """

    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def get_geopackage_from_data_services(run: CalibrationRun):
    """
    Retrieves GeoPackage data from Data Services and updates the CalibrationRun instance.

    :param run: A CalibrationRun object with associated gage information.
    """
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
        if run.geopackage_eds_file_path and not os.path.exists(run.geopackage_eds_file_path):
            logger.error(f"Geopackage from Data Services, {run.geopackage_eds_file_path} does not exist")
        logger.info(f'Setting run.geopackage_eds_file_path to {run.geopackage_eds_file_path}')


def get_observational_data_from_data_services(run: CalibrationRun):
    """
    Retrieves observational data from Data Services and updates the CalibrationRun instance.

    :param run: A CalibrationRun object with associated gage information.
    """
    if settings.ENTERPRISE_DATA_OBSERVATION_DATA_ENDPOINT[0]:
        logger.info('Getting observational data from Data Services')
        url = urljoin(settings.ENTERPRISE_DATA_URL,
                      settings.ENTERPRISE_DATA_OBSERVATION_DATA_ENDPOINT[1].format(
                          gage_id=run.gage.gage_id,
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
    if run.observational_eds_file_path and not os.path.exists(run.observational_eds_file_path):
        logger.error(f"Observational file from Data Services, {run.observational_eds_file_path} does not exist")
    clear_times(run)
    logger.info(f'Setting run.observational_eds_file_path to {run.observational_eds_file_path}')


def clear_times(run: CalibrationRun):
    # Invalidate the dates, since we'll have to compute the intersection again
    # Only do this when running through the GUI.  If CLI, we assume the user knows what he is doing
    if run.job_genesis == JobGenesis.GUI.value:
        run.time_range_start = None
        run.time_range_end = None
        run.calibration_start_period = None
        run.calibration_end_period = None
        run.validation_start_period = None
        run.validation_end_period = None
        run.calibration_eval_start_period = None
        run.calibration_eval_end_period = None
        run.validation_eval_start_period = None
        run.validation_eval_end_period = None


def get_forcing_data_from_data_services(run: CalibrationRun):
    """
    Retrieves forcing data from Data Services and updates the CalibrationRun instance.

    :param run: A CalibrationRun object with associated gage information.
    """
    if settings.ENTERPRISE_DATA_FORCING_DATA_ENDPOINT[0]:
        logger.info('Getting forcing data from Data Services')
        url = urljoin(settings.ENTERPRISE_DATA_URL, settings.ENTERPRISE_DATA_FORCING_DATA_ENDPOINT[1].format(gage_id=run.gage.gage_id))
        forcing_json = fetch_from_data_services('GET', url, headers=default_headers)
    else:
        get_forcing_data_from_s3(run)
        return

    forcing_data = validate_response_data(S3DirectoryValidator, forcing_json, 'Forcing data from Data Services is not in the expected format')

    s3_uri = forcing_data.get('uri')

    run.forcing_eds_dir_path = convert_s3_uri_to_fs(s3_uri)
    clear_times(run)
    logger.info(f'Setting run.forcing_eds_dir_path to {run.forcing_eds_dir_path}')


def get_forcing_data_from_s3(run: CalibrationRun):
    """
    Attempts to retrieve forcing data from local S3 directories.

    :param run: A CalibrationRun object with associated gage information.
    :raises DataServicesException: If the forcing data cannot be found in the local S3 directories.
    """
    for s3_uri in settings.FORCING_DATA_DIRS:
        dir_path = convert_s3_uri_to_fs(s3_uri)
        gage_dir = os.path.join(dir_path, run.gage.domain.name, f"Gage_{run.gage.gage_id}")
        if os.path.isdir(gage_dir):
            logger.info(f"Found forcing directory {gage_dir}")
            run.forcing_eds_dir_path = gage_dir
            clear_times(run)
            logger.info(f'Setting run.forcing_eds_dir_path to {run.forcing_eds_dir_path}')
            return
        else:
            logger.info(f"Forcing directory doesn't exist for {gage_dir}")

    raise DataServicesException(f"Could not find forcing data for gage {run.gage.gage_id}")


def get_module_metadata_from_data_services(run: CalibrationRun, calibration_formulations: QuerySet[CalibrationFormulation],
                                           gage_changed: bool = False):
    """
    Retrieves module metadata from Data Services and updates the database with module parameters and output variables.

    :param run: A CalibrationRun object with associated gage information.
    :param calibration_formulations: QuerySet of CalibrationFormulations for the run.
    :param gage_changed: Boolean indicating whether the gage has changed:
                         - If False: Indicates the modules have changed.
                         - If True: Indicates the gage has changed, and we want to retain the min/max values
                           for existing parameters while updating their initial values.
    :raises DataServicesException: If required module metadata is missing.
    """
    gage = run.gage

    # Collect module names from calibration formulations
    my_module_names_set = list(calibration_formulations.values_list('module__name', flat=True))

    # Fetch module metadata from Data Services or use test data
    if settings.ENTERPRISE_DATA_MODULE_METADATA_ENDPOINT[0]:
        logger.info('Fetching module metadata from Data Services')
        url = urljoin(settings.ENTERPRISE_DATA_URL, settings.ENTERPRISE_DATA_MODULE_METADATA_ENDPOINT[1])

        module_json = fetch_from_data_services(
            'POST',
            url,
            headers=default_headers,
            payload={'modules': my_module_names_set,
                     'gage_id': gage.gage_id,
                     'domain': gage.domain.name,
                     'source': gage.agency,
                     'version': settings.ENTERPRISE_DATA_VERSION})
    else:
        logger.info('Using dummy module metadata')
        module_json = data_services_test_data.eds_module_metadata_real_data

    module_metadata = validate_response_data(
        ModuleDataListSerializer, module_json,
        'Module metadata from Data Services is not in the expected format')

    fix_module_metadata(module_metadata)

    # Extract module names from the response for comparison
    eds_module_names = set([module['module_name'] for module in module_metadata['modules']])
    my_module_names_set = set(my_module_names_set)

    # Determine discrepancies between requested and returned modules
    missing_names = my_module_names_set - eds_module_names
    extra_names = eds_module_names - my_module_names_set

    # Save module parameters and output variables to the database
    with transaction.atomic():
        for module in module_metadata.get('modules'):
            module_name = module['module_name']

            if module_name in extra_names:
                # Ignore any extra names that Data Services sent us
                logger.warning(f'Ignoring extra module from Data Services - {module["module_name"]}')
                continue

            # Fetch the corresponding module instance
            module_instance = get_cached_module_by_name(module['module_name'])
            calibration_formulation = calibration_formulations.get(module=module_instance)

            # Copy the BMI configuration file to the appropriate directory
            bmi_config = convert_s3_uri_to_fs(module['parameter_file']['uri'])
            copy_directory(bmi_config, get_bmi_config_dir_for_module(run, module_name))

            # Save output variables for the module
            if not module['output_variables']:
                logger.warning(f"Module '{module_name}' has no output variables.")
            else:
                for output in module['output_variables']:
                    ModuleOutputVariable.objects.update_or_create(
                        name=output['variable'],
                        calibration_formulation=calibration_formulation,
                        # TODO Fix this.  Description is required
                        defaults={'description': output['description'] if output['description'] else 'placeholder description'}
                    )

            # Save or update parameters for the module
            if not module['calibrate_parameters']:
                logger.warning(f"Module '{module_name}' has no calibratable parameters.")
            else:
                for param in module['calibrate_parameters']:
                    # Data Services gives us initial_value, min and max as Strings because sometimes crap appears.

                    # Using get_or_create because we don't want to override any values the user has already entered
                    calibration_parameter, created = CalibrationParameter.objects.get_or_create(
                        name=param['name'],
                        calibration_formulation=calibration_formulation,
                        defaults={'data_type': param['data_type'],
                                  'description': param['description'],
                                  'initial_value': str_to_float(param['initial_value']),
                                  'minimum': str_to_float(param['min']),
                                  'maximum': str_to_float(param['max']),
                                  'units': param['units']
                                  }
                    )

                    # Update initial value if the gage changed and the parameter already exists
                    if gage_changed and not created:
                        logger.info(
                            f"Updating initial value for parameter {param['name']} for module {calibration_formulation.module.name}")
                        # We want to overwrite the initial_value from Data Services
                        calibration_parameter.initial_value = str_to_float(param['initial_value'])
                        calibration_parameter.save(update_fields=['initial_value'])

    # Raise an exception if any requested modules are missing in the response
    if missing_names:
        raise DataServicesException(f'Response from Data Services is missing entries for: {missing_names}')

    return


translation_map = {
    ("CFE-S", "soil_params.smcmax"): "maxsmc",
    ("CFE-S", "soil_params.satdk"): "satdk",
    ("CFE-S", "soil_params.slop"): "slope",
    ("CFE-S", "soil_params.b"): "b",
    ("CFE-S", "K_lf"): "Klf",
    ("CFE-S", "K_nash"): "Kn",
    ("CFE-S", "soil_params.satpsi"): "satpsi",
    ("CFE-S", "soil_params.wlt"): "wltsmc",

    ("CFE-X", "soil_params.smcmax"): "maxsmc",
    ("CFE-X", "soil_params.satdk"): "satdk",
    ("CFE-X", "soil_params.slop"): "slope",
    ("CFE-X", "soil_params.b"): "b",
    ("CFE-X", "K_lf"): "Klf",
    ("CFE-X", "K_nash"): "Kn",
    ("CFE-X", "soil_params.satpsi"): "satpsi",
    ("CFE-X", "soil_params.wlt"): "wltsmc",

    ("Noah-OWP-Modular", "MAXSMC"): "SMCMAX",
    ("Noah-OWP-Modular", "CWPVT"): "CWP",
    ("Noah-OWP-Modular", "SATDK"): "DKSAT",

    ("LASAM", "theta_e"): "smcmax",
    ("LASAM", "theta_r"): "smcmin",
    ("LASAM", "n"): "van_genuchten_n",
    ("LASAM", "alpha"): "van_genuchten_alpha",
    ("LASAM", "Ks"): "hydraulic_conductivity",
    ("LASAM", "field_capacity_psi"): "field_capacity",

    ("SFT", "soil_params.smcmax"): "smcmax",
    ("SFT", "soil_params.b"): "b",
    ("SFT", "soil_params.satpsi"): "satpsi",
    ("SFT", "soil_params.quartz"): "quartz",
    ("SFT", "soil_temperature"): "soil_temperature_profile",

    ("SMP", "soil_params.smcmax"): "smcmax",
    ("SMP", "soil_params.b"): "b",
    ("SMP", "soil_params.satpsi"): "satpsi",
}


def fix_module_metadata(metadata):
    """
    Translates parameter names in module metadata based on a translation map.

    :param metadata: Dictionary containing module metadata.
                     Example structure:
                     {
                         "modules": [
                             {
                                 "name": "module_name",
                                 "calibrate_parameters": [
                                     {"name": "full_param_name", "value": 123}
                                 ]
                             }
                         ]
                     }
    """
    for module in metadata["modules"]:
        module_name = module["module_name"]  # Extract the module name
        for param in module["calibrate_parameters"]:
            param_name = param["name"]  # Extract the parameter name
            key = (module_name, param_name)  # Create a tuple key
            # Check if the key exists in the translation_map
            if key in translation_map:
                logger.info(f"Translating {key} to {translation_map[key]}")
                param["name"] = translation_map[key]


def str_to_float(value):
    """
    Converts a value to a float, returning None if conversion fails.

    :param value: The value to convert.
    :return: The converted float or None if the value is invalid.
    """
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None
