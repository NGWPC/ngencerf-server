import logging
import os

import boto3

logger = logging.getLogger(__name__)
logging.getLogger('boto').setLevel(logging.INFO)


def parse_s3_uri(s3_uri):
    """
      Parse an S3 URI into bucket and key components.

      :param s3_uri: A string representing the S3 URI (e.g., 's3://bucket-name/key')
      :return: A tuple containing the bucket name and key as strings
      """
    return s3_uri.replace("s3://", "").split("/", 1)


def download_s3(uri, save_dir):
    """
     Download a single file from S3 to a specified local directory.

     :param uri: A string representing the S3 URI of the file to download
     :param save_dir: A string representing the local directory where the file will be saved
     :return: The local file path where the file was saved
     """
    # Ensure the save directory exists; create it if it doesn't
    if not os.path.exists(save_dir):
        os.mkdir(save_dir)

    # Parse the S3 URI to extract the bucket and key
    bucket, key = parse_s3_uri(uri)
    logger.info(f'download_s3: downloading {uri} to {save_dir}')

    filename = key.split('/')[-1]
    local_file_path = os.path.join(save_dir, filename)

    # Check if the file already exists locally
    if os.path.exists(local_file_path):
        logger.info(f'download_s3: {uri} already downloaded to {local_file_path}')
    else:
        s3_client = boto3.client('s3')
        s3_client.download_file(bucket, key, local_file_path)
        logger.info(f'download_s3: {uri} downloaded to {local_file_path}')

    return local_file_path


def download_all_s3(uri, save_dir):
    """
    Download all files from an S3 directory to a specified local directory.

    :param uri: A string representing the S3 URI of the directory to download
    :param save_dir: A string representing the local directory where files will be saved
    """
    # Ensure the URI ends with a slash, indicating it's a directory
    if not uri.endswith('/'):
        raise Exception('uri must be a directory and end with a slash (/)')

    # Parse the S3 URI to extract the bucket and key
    bucket, key = parse_s3_uri(uri)
    logger.info(f'download_all_s3: downloading {uri} to {save_dir}')

    # Extract the subdirectory name from the key and update save_dir
    subdir = key.split('/')[-2]
    save_dir = str(os.path.join(save_dir, subdir))

    # Ensure the save directory exists; create it if it doesn't
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    # List all objects in the specified S3 directory
    s3_client = boto3.client('s3')
    response = s3_client.list_objects_v2(Bucket=bucket, Prefix=key)
    s3_objects = [obj["Key"] for obj in response["Contents"]]

    # Download each file in the directory
    for s3_file in s3_objects:
        filename = s3_file.split('/')[-1]
        local_file_path = os.path.join(save_dir, filename)

        # Check if the file already exists locally
        if os.path.exists(local_file_path):
            logger.info(f'download_all_s3: {local_file_path} already downloaded to {local_file_path}')
        else:
            logger.info(f'download_all_s3: {uri} downloaded to {local_file_path}')
            s3_client.download_file(bucket, s3_file, local_file_path)
    logger.info(f"Downloaded files to {save_dir}: {', '.join(os.listdir(save_dir))}")
