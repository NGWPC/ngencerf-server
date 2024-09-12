import logging
import os

from cerfServer import settings

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

    return os.path.join(settings.S3_MOUNT_POINT, bucket, key)
