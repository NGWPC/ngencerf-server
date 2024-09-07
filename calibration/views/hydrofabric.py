import json
import logging
from urllib.parse import urljoin

import requests
from django.db import transaction

from calibration.models import CalibrationParameter, ModuleOutputVariable, CalibrationFormulation, CalibrationRun
from calibration.util.aws_util import convert_s3_uri_to_fs
from calibration.util.calibration_validators import ForcingHydrofabricSerializer, ObservationalHydrofabricSerializer, \
    ModuleDataHydrofabricListSerializer, GeopackageHydrofabricSerializer, ModuleHydrofabricListSerializer
from calibration.views.common import CerfException
from cerfServer import settings
from hydrofabric_test_data.hydrofabric_test_data import geopackage_sample_data, observational_sample_data, module_sample_data, forcing_sample_data, \
    module_metadata_sample_data

logger = logging.getLogger(__name__)

headers = {
    "Content-Type": "application/json"
}


def get_geopackage_from_hydrofabric(run: CalibrationRun):
    print('Getting geopackage from Hydrofabric')

    if settings.HYDROFABRIC:
        url = urljoin(settings.HYDROFABRIC_URL, settings.HYDROFABRIC_GEOPACKAGE_ENDPOINT.format(gage_id=run.gage.gage_id))
        response = requests.get(url, headers=headers)
        try:
            response.raise_for_status()
            geopackage_json = response.json()
        except requests.exceptions.HTTPError:
            logger.error(f"Call to hydrofabric {url} failed with {response.status_code}.")
            print("Response from Hydrofabric:", response.text)
            return
    else:
        geopackage_json = geopackage_sample_data

    hydrofabric_data = validate_response_data(GeopackageHydrofabricSerializer, geopackage_json,
                                              'Geopackage data from Hydrofabric is not in the expected format')

    s3_uri = hydrofabric_data.get('uri')
    run.geopackage_hydrofabric_path = convert_s3_uri_to_fs(s3_uri)
    logger.info(f'Setting run.geopackage_hydrofabric_path to {run.geopackage_hydrofabric_path}')


# TODO Throw exception for AWS errors and Hydrofabric errors
def get_observational_data_from_hydrofabric(run: CalibrationRun):
    print('Getting observational data from Hydrofabric')
    if settings.HYDROFABRIC:
        url = urljoin(settings.HYDROFABRIC_URL, settings.HYDROFABRIC_OBSERVATION_DATA_ENDPOINT.format(gage_id=run.gage.gage_id))
        # Need to send source
        response = requests.get(url, headers=headers)
        try:
            response.raise_for_status()
            observational_json = response.json()
        except requests.exceptions.HTTPError:
            logger.error(f"Call to hydrofabric {url} failed with {response.status_code}.")
            print("Response from Hydrofabric:", response.text)
            return
    else:
        observational_json = observational_sample_data

    observational_data = validate_response_data(ObservationalHydrofabricSerializer, observational_json,
                                                'Observational data from Hydrofabric is not in the expected format')

    s3_uri = observational_data.get('uri')

    run.observational_hydrofabric_file_path = convert_s3_uri_to_fs(s3_uri)
    logger.info(f'Setting run.observational_hydrofabric_file_path to {run.observational_hydrofabric_file_path}')


def get_forcing_data_from_hydrofabric(run: CalibrationRun):
    print('Getting forcing data from Hydrofabric')
    if settings.HYDROFABRIC:
        url = urljoin(settings.HYDROFABRIC_URL, settings.HYDROFABRIC_FORCING_DATA_ENDPOINT.format(gage_id=run.gage.gage_id))
        # Need to send source
        response = requests.get(url, headers=headers)
        try:
            response.raise_for_status()
            forcing_json = response.json()
        except requests.exceptions.HTTPError:
            logger.error(f"Call to hydrofabric {url} failed with {response.status_code}.")
            print("Response from Hydrofabric:", response.text)
            return
    else:
        forcing_json = forcing_sample_data

    forcing_data = validate_response_data(ForcingHydrofabricSerializer, forcing_json, 'Forcing data from Hydrofabric is not in the expected format')

    s3_uri = forcing_data.get('uri')

    run.forcing_hydrofabric_dir_path = convert_s3_uri_to_fs(s3_uri)
    logger.info(f'Setting run.forcing_hydrofabric_dir_path to {run.forcing_hydrofabric_dir_path}')


def get_module_data_from_hydrofabric(run, modules):
    print('Getting module metadata from Hydrofabric')
    if settings.HYDROFABRIC:
        url = urljoin(settings.HYDROFABRIC_URL, settings.HYDROFABRIC_MODULE_METADATA_ENDPOINT.format(gage_id=run.gage.gage_id))
        # Need to send list of modules
        response = requests.get(url, headers=headers)
        try:
            response.raise_for_status()
            module_json = response.json()
        except requests.exceptions.HTTPError:
            logger.error(f"Call to hydrofabric {url} failed with {response.status_code}.")
            print("Response from Hydrofabric:", response.text)
            return
    else:
        module_json = module_metadata_sample_data

    module_data = validate_response_data(ModuleDataHydrofabricListSerializer, module_json,
                                         'Module metadata from Hydrofabric is not in the expected format')

    # print('getting metadata from hydrofabric')

    # Save the output variables and parameters for each module
    # TODO We need to ensure that the data from Hydrofabric contains all the modules we asked for
    with transaction.atomic():
        for m in module_data.get('modules'):
            # Get the modules object from our list
            module = modules.filter(name=m['module_name']).first()
            # print('module', module)

            # Save output variables
            outputs = m['module_output_variables']
            o: dict
            for o in outputs:
                ModuleOutputVariable.objects.update_or_create(
                    name=o['name'],
                    calibration_formulation=module,
                    defaults={'description': o['description']}
                )
            # Save parameters
            # print('getting parameters for', m)
            parameters = m['module_parameters']
            # print('parameters from Hydro', parameters)
            for p in parameters:
                # Using get_or_create because we don't want to override any values the user has already entered
                CalibrationParameter.objects.get_or_create(
                    name=p['name'],
                    calibration_formulation=module,
                    defaults={'data_type': p['data_type'],
                              'description': p['description'], 'minimum': p['minimum'],
                              'maximum': p['maximum']}
                )

        # run.got_module_data_from_hydrofabric = True
        run.save()

    return


def get_modules_from_hydrofabric(run: CalibrationRun):
    print('Getting module data from Hydrofabric')
    if settings.HYDROFABRIC:
        url = urljoin(settings.HYDROFABRIC_URL, settings.HYDROFABRIC_MODULES_ENDPOINT.format(gage_id=run.gage.gage_id))
        response = requests.get(url, headers=headers)
        try:
            response.raise_for_status()
            module_json = response.json()
        except requests.exceptions.HTTPError:
            logger.error(f"Call to hydrofabric {url} failed with {response.status_code}.")
            print("Response from Hydrofabric:", response.text)
            return
    else:
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
