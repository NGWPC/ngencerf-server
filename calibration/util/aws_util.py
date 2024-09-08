import logging
import os

from calibration.views.common import CerfException
from cerfServer.local_settings import HYDROFABRIC_BUCKET, HYDROFABRIC_BUCKET_MOUNT_POINT

logger = logging.getLogger(__name__)
logging.getLogger('boto').setLevel(logging.INFO)


def parse_s3_uri(s3_uri):
    """
      Parse an S3 URI into bucket and key components.

      :param s3_uri: A string representing the S3 URI (e.g., 's3://bucket-name/key')
      :return: A tuple containing the bucket name and key as strings
      """
    return s3_uri.replace("s3://", "").split("/", 1)


def convert_s3_uri_to_fs(uri):
    """
    Until Hydrofabric gives ua a file path, convert the S3 uri to filepath
    :param uri:
    :return:file spec of the locally mounted bucket
    """
    bucket, key = parse_s3_uri(uri)
    if bucket != HYDROFABRIC_BUCKET:
        raise CerfException(f'Unexpected bucket {bucket}')

    return os.path.join(HYDROFABRIC_BUCKET_MOUNT_POINT, key)
