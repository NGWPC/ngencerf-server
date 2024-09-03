import json
import logging
from urllib.parse import urljoin

import requests
import rest_framework
from django.db import transaction
from rest_framework import status

from calibration.models import CalibrationParameter, ModuleOutputVariable, CalibrationFormulation, CalibrationRun
from calibration.util.aws_util import convert_s3_uri_to_fs
from calibration.util.calibration_validators import ForcingHydrofabricSerializer, GeopackageSerializer, ObservationalHydrofabricSerializer, \
    ModuleDataHydrofabricListSerializer, ModuleHydrofabricListSerializer
from calibration.views.common import CerfException
from hydrofabric_test_data.hydrofabric_test_data import geopackage_sample_data, observational_sample_data, module_metadata_sample_data, \
    module_sample_data, forcing_sample_data

logger = logging.getLogger(__name__)


def get_geopackage_from_hydrofabric(run: CalibrationRun):
    # Get this from hydrofabric and store in standard location
    # modules_request = {"gage_id": gage_id
    # response = requests.post(settings.HYDROFABRIC_URL, json=modules_request)
    # module_data = response.json()
    geopackage_json = geopackage_sample_data

    hydrofabric_data = validate_response_data(ObservationalHydrofabricSerializer, geopackage_json,
                                                'Geopackage data from Hydrofabric is not in the expected format')
    # validator = GeopackageSerializer(data=geopackage_json)
    # if not validator.is_valid():
    #     logger.debug(validator.errors)
    #     raise CerfException(f'Geopackage data from Hydrofabric is not in the expected format - {validator.errors}')

    s3_uri = hydrofabric_data.get('uri')
    run.geopackage_hydrofabric_path = convert_s3_uri_to_fs(s3_uri)
    print('setting run.geopackage_hydrofabric_path to', run.geopackage_hydrofabric_path)
    # download_s3(s3_uri, get_geopackage_directory(run))


# TODO Throw exception for AWS errors and Hydrofabric errors
def get_observational_data_from_hydrofabric(run: CalibrationRun):
    print('Getting observational data from Hydrofabric')
    # Get this from hydrofabric
    request = {"source": run.observational_source.name}
    headers = {
        "Content-Type": "application/json"
    }
    base_url = 'https://jsonplaceholder.typicode.com'
    path = '/todos/1'
    url = urljoin(base_url, path)
    response = requests.get(url, json=request, headers=headers)

    observational_json = observational_sample_data

    # Check if the request was successful
    if response.status_code == rest_framework.status.HTTP_200_OK:
        # Parse and print the response JSON
        response_data = response.json()
        print("Success:", response_data)
    else:
        # Print the error
        logger.error(f"Call to hydrofabric {url} failed with {response.status_code}.  Will try again when before job is submitted")
        print("Response from Hydrofabric:", response.text)

    observational_data = validate_response_data(ObservationalHydrofabricSerializer, observational_json,
                                                'Observational data from Hydrofabric is not in the expected format')
    # validator = ObservationalHydrofabricSerializer(data=response)
    # if not validator.is_valid():
    #     logger.debug(validator.errors)
    #     raise CerfException(f'Observational data from Hydrofabric is not in the expected format - {validator.errors}')

    s3_uri = observational_data.get('uri')

    run.observational_hydrofabric_file_path = convert_s3_uri_to_fs(s3_uri)
    print('setting run.observational_hydrofabric_file_path to', run.observational_hydrofabric_file_path)
    # download_s3(s3_uri, get_observation_from_hydrofabric_dir(run))


def get_forcing_data_from_hydrofabric(run: CalibrationRun):
    print('Getting forcing data from Hydrofabric')
    # Get this from hydrofabric
    # request = {"source": forcing_source
    # forcing_json = requests.post(settings.HYDROFABRIC_URL, json=request)
    # forcing_json = forcing_json.json()
    forcing_json = forcing_sample_data

    forcing_data = validate_response_data(ForcingHydrofabricSerializer, forcing_json, 'Forcing data from Hydrofabric is not in the expected format')
    # validator = ForcingHydrofabricSerializer(data=forcing_json)
    # if not validator.is_valid():
    #     logger.debug(validator.errors)
    #     raise CerfException(f'Forcing data from Hydrofabric is not in the expected format - {validator.errors}')

    s3_uri = forcing_data.get('uri')

    # This is a path to a directory, so we want to download all files
    # bucket, key = parse_s3_uri(s3_uri)
    # subdir = key.split('/')[-1]

    run.forcing_hydrofabric_dir_path = convert_s3_uri_to_fs(s3_uri)
    print('setting run.forcing_hydrofabric_dir_path to', run.forcing_hydrofabric_dir_path)
    # download_all_s3(s3_uri, get_forcing_from_hydrofabric_dir(run))


def get_module_data_from_hydrofabric(run: CalibrationRun, modules):
    # Get this from hydrofabric
    # modules_request = {"modules":modules}
    # response = requests.post(settings.HYDROFABRIC_URL, json=modules_request)
    # module_json = response.json()

    module_json = module_metadata_sample_data.get("modules")

    module_data = validate_response_data(ModuleDataHydrofabricListSerializer, module_json,
                                         'Module metadata from Hydrofabric is not in the expected format')
    # validator = ModuleDataHydrofabricListSerializer(data=module_metadata_sample_data)
    # if not validator.is_valid():
    #     logger.error(validator.errors)
    #     raise CerfException(f'Module metadata from Hydrofabric is not in the expected format - {validator.errors}')

    # print('getting metadata from hydrofabric')

    # Save the output variables and parameters for each module
    # TODO We need to ensure that the data from Hydrofabric contains all the modules we asked for
    with transaction.atomic():
        for m in module_json:
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
                CalibrationParameter.objects.update_or_create(
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
    print('calling hydrofabric')

    # Get this from hydrofabric
    # modules_request = {}
    # response = requests.post(settings.HYDROFABRIC_URL, json=modules_request)
    # module_json = response.json()
    module_json = module_sample_data

    current_module_names = set(
        CalibrationFormulation.objects.filter(calibration_run=run)
        .values_list('name', flat=True)
    )

    print('current_module_names', current_module_names)

    module_data = validate_response_data(GeopackageSerializer, module_json, 'Module data from Hydrofabric is not in the expected format')

    # validator = ModuleHydrofabricListSerializer(data=module_sample_data)
    # if not validator.is_valid():
    #     logger.debug(validator.errors)
    #     raise CerfException(f'Module data from Hydrofabric is not in the expected format - {validator.errors}')

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


