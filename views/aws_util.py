import logging
import os
import tempfile
from urllib.parse import urlparse

import boto3

logger = logging.getLogger(__name__)
logging.getLogger('boto').setLevel(logging.INFO)


def parse_s3_uri(s3_uri):
    return s3_uri.replace("s3://", "").split("/", 1)


def download_s3(bucket, key, save_as):
    print('downloading', bucket, key, 'to', save_as)
    s3_client = boto3.client('s3')
    s3_client.download_file(bucket, key, save_as)
