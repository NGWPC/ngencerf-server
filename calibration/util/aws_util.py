import logging
import os

from django.conf import settings

from calibration.views.common import CerfException

logger = logging.getLogger(__name__)
logging.getLogger('boto').setLevel(logging.INFO)


def parse_s3_uri(s3_uri: str) -> list[str]:
    """
    Parse an S3 URI into bucket and key components.

    :param s3_uri: A string representing the S3 URI (e.g., 's3://bucket-name/key')
    :return: A list containing the bucket name and key as strings
    """
    return s3_uri.replace("s3://", "").split("/", 1)


def convert_s3_uri_to_fs(s3_uri: str) -> str:
    """
    Until Data Services gives us a file path, convert the S3 URI to a local file path.

    :param s3_uri: A string representing the S3 URI (e.g., 's3://bucket-name/key')
    :return: File path corresponding to the locally mounted bucket
    """
    if not s3_uri:
        raise CerfException('S3 URI cannot be empty')

    bucket, key = parse_s3_uri(s3_uri)

    bucket_path = os.path.join(settings.S3_MOUNT_POINT, bucket)
    if os.path.isdir(bucket_path):
        return os.path.join(bucket_path, key)
    else:
        raise CerfException(f"Cannot find mapping for bucket '{bucket}' at '{bucket_path}'")
