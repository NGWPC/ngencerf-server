import logging
from urllib.parse import urljoin

import requests
import rest_framework
from rest_framework import status

from calibration.util.aws_util import download_s3, download_all_s3
from calibration.util.calibration_validators import ForcingHydrofabricSerializer, GeopackageSerializer, ObservationalHydrofabricSerializer
from calibration.util.ngen_locations import observation_dir, forcing_dir, geopackage_dir
from calibration.views.common import CerfException

logger = logging.getLogger(__name__)

geopackage_sample_data = {
    "uri": "s3://ngwpc-dev/Yuqiong.Liu/data/gauge_01073000.gpkg",
    "creation_date": "2024-07-30T12:33:00.001Z"
}

forcing_sample_data = {
    "uri": "s3://ngwpc-dev/Yuqiong.Liu/data/aorc_nwm/csv_basin_group1/Gage_01123000/"
}

observational_sample_data = {
    "uri": "s3://ngwpc-dev/Yuqiong.Liu/data/streamflow_obs/01123000_hourly_discharge.csv"
}


def get_geopackage_from_hydrofabric(gage_id):
    # Get this from hydrofabric
    # modules_request = {"gage_id": gage_id
    # response = requests.post(settings.HYDROFABRIC_URL, json=modules_request)
    # module_data = response.json()
    geopackage_data = geopackage_sample_data

    validator = GeopackageSerializer(data=geopackage_data)
    if not validator.is_valid():
        logger.debug(validator.errors)
        raise CerfException(f'Geopackage data from Hydrofabric is not in the expected format - {validator.errors}')

    uri = geopackage_data['uri']
    file_path = download_s3(uri, geopackage_dir)

    return file_path


def get_observational_data_from_hydrofabric(observational_source):
    print('Getting observational data from Hydrofabric')
    # Get this from hydrofabric
    request = {"source": observational_source}
    headers = {
        "Content-Type": "application/json"
    }
    base_url = 'https://jsonplaceholder.typicode.com'
    path = '/foo/1'
    url = urljoin(base_url, path)
    response = requests.get(url, json=request, headers=headers)
    # Check if the request was successful
    if response.status_code == rest_framework.status.HTTP_200_OK:
        # Parse and print the response JSON
        response_data = response.json()
        print("Success:", response_data)
    else:
        # Print the error
        logger.error(f"Call to hydrofabric {url} failed with {response.status_code}.  Will try again when before job is submitted")
        print("Response:", response.text)

    response = observational_sample_data
    validator = ObservationalHydrofabricSerializer(data=response)
    if not validator.is_valid():
        logger.debug(validator.errors)
        raise CerfException(f'Observational data from Hydrofabric is not in the expected format - {validator.errors}')

    s3_uri = validator.data.get('uri')

    # This is a path to a single file, which we just need to download
    # bucket, key = parse_s3_uri(s3_uri)
    # filename = key.split('/')[-1]
    download_s3(s3_uri, observation_dir)


def get_forcing_data_from_hydrofabric(forcing_source):
    print('Getting forcing data from Hydrofabric')
    # Get this from hydrofabric
    # request = {"source": forcing_source
    # response = requests.post(settings.HYDROFABRIC_URL, json=request)
    # response = response.json()
    response = forcing_sample_data
    validator = ForcingHydrofabricSerializer(data=response)
    if not validator.is_valid():
        logger.debug(validator.errors)
        raise CerfException(f'Forcing data from Hydrofabric is not in the expected format - {validator.errors}')

    s3_uri = validator.data.get('uri')

    # This is a path to a directory, so we want to download all files
    # bucket, key = parse_s3_uri(s3_uri)
    # subdir = key.split('/')[-1]

    download_all_s3(s3_uri, forcing_dir)
