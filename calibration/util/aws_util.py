import logging
import os

import boto3

logger = logging.getLogger(__name__)
logging.getLogger('boto').setLevel(logging.INFO)


def parse_s3_uri(s3_uri):
    return s3_uri.replace("s3://", "").split("/", 1)


def download_s3(uri, save_dir):
    # uri must refer to an s3 file
    # save_dir is a local directory
    if not os.path.exists(save_dir):
        os.mkdir(save_dir)

    bucket, key = parse_s3_uri(uri)
    logger.info(f'download_s3: downloading {bucket} {key} to {save_dir}')
    filename = key.split('/')[-1]
    local_file_path = os.path.join(save_dir, filename)
    if os.path.exists(local_file_path):
        logger.info(f'download_s3: {uri} already downloaded to {local_file_path}')
    else:
        s3_client = boto3.client('s3')
        s3_client.download_file(bucket, key, local_file_path)
        logger.info(f'download_s3: {uri} downloaded to {local_file_path}')

    return local_file_path


def download_all_s3(uri, save_dir):
    # uri must refer to an s3 directory
    # save_dir is a local directory

    # Make sure uri has a trailing slash
    if not uri.endswith('/'):
        raise Exception('uri must be a directory and end with a slash (/)')

    bucket, key = parse_s3_uri(uri)
    logger.info(f'download_all_s3: downloading {bucket} {key} to {save_dir}')

    # Get the directory name portion of the url
    subdir = key.split('/')[-2]
    save_dir = str(os.path.join(save_dir, subdir))

    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    s3_client = boto3.client('s3')
    response = s3_client.list_objects_v2(Bucket=bucket, Prefix=key)
    s3_objects = [obj["Key"] for obj in response["Contents"]]
    for s3_file in s3_objects:
        filename = s3_file.split('/')[-1]
        local_file_path = os.path.join(save_dir, filename)
        if os.path.exists(local_file_path):
            logger.info(f'download_all_s3: {local_file_path} already downloaded to {local_file_path}')
        else:
            logger.info(f'download_all_s3: {uri} downloaded to {local_file_path}')
            s3_client.download_file(bucket, s3_file, local_file_path)
    logger.info(f"Downloaded files to {save_dir}: {', '.join(os.listdir(save_dir))}")
