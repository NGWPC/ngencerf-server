import hashlib
import logging
import os
import subprocess

from django.conf import settings
from django.core.cache import cache

from calibration.enums_vanilla import NgenEnvironmentEnum

logger = logging.getLogger(__name__)


# noinspection PyTypeChecker
def copy_file_from_docker_image(image_name: str, container_name: str, src_path: str, dest_path: str) -> bool:
    """
    Copies a file from a Docker image using a temporary container and ensures cleanup.

    :param image_name: Name of the Docker image.
    :param container_name: Temporary container name.
    :param src_path: Path to the file inside the container.
    :param dest_path: Destination path on the host system.
    :return: True if the copy succeeds, False otherwise.
    """
    success = False  # Default to failure

    try:
        # Step 1: Create a temporary container
        create_cmd = ["docker", "create", "--name", container_name, image_name]
        logger.debug(create_cmd)
        subprocess.run(create_cmd, check=True, capture_output=True, text=True)

        # Step 2: Copy the file from the container
        copy_cmd = ["docker", "cp", f"{container_name}:{src_path}", dest_path]
        logger.debug(copy_cmd)
        subprocess.run(copy_cmd, check=True)

        logger.info(f"Successfully copied {src_path} to {dest_path}")
        success = True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error copying file: {e.stderr or str(e)}")
    finally:
        # Step 3: Remove the temporary container (always runs, even if copy fails)
        rm_cmd = ["docker", "rm", "-f", container_name]
        subprocess.run(rm_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # Suppress output

    return success


def copy_file_from_singularity_image(image_path: str, src_path: str, dest_path: str) -> bool:
    """
    Copies a file from a Singularity image (.sif) using `singularity exec`.

    :param image_path: Path to the Singularity image file (.sif)
    :param src_path: Path to the file inside the container
    :param dest_path: Destination path on the host system
    :return: True if the copy succeeds, False otherwise
    """
    success = False  # Default to failure

    logger.info(f'Copy file {src_path} from image {image_path}')

    # Check if the path exists
    if not os.path.exists(image_path):
        # If it's a symlink, check whether it's broken
        if os.path.islink(image_path):
            target = os.readlink(image_path)
            logger.error(f"Image path {image_path} is a symlink to {target}, but the target does not exist.")
        else:
            logger.error(f"Image {image_path} does not exist.")
        return False

    try:
        copy_cmd = ["singularity", "exec", image_path, "cp", src_path, dest_path]
        subprocess.run(copy_cmd, check=True)

        logger.info(f"Successfully copied {src_path} from {image_path} to {dest_path}")
        success = True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error copying file: {e.stderr or str(e)}")

    return success


def generate_cache_key(image_name: str, container_name: str, container_file_name: str, local_file_name: str) -> str:
    """
    Generates a unique cache key for the file copy operation based on input parameters.

    :param image_name: Name of the image.
    :param container_name: Name of the container.
    :param container_file_name: Path to the file inside the container.
    :param local_file_name: Local destination file name.
    :return: A unique cache key string.
    """
    key_string = f"{container_name}:{container_file_name}:{image_name}:{local_file_name}"
    return "copy_file:" + hashlib.md5(key_string.encode()).hexdigest()


def copy_file_from_image(image_name: str, container_name: str, container_file_name: str, local_file_name: str) -> bool:
    """
    Copies a file from an image (Docker or Singularity) based on the current environment,
    with caching for successful operations.

    The function first checks if the copy operation was successfully cached.
    If not cached, it performs the copy operation and caches the success result.

    :param image_name: Name of the image.
    :param container_name: Name of the container (used for Docker).
    :param container_file_name: Path to the file inside the container.
    :param local_file_name: Local destination file name.
    :return: True if the file copy was successful, False otherwise.
    """
    cache_key = generate_cache_key(image_name, container_name, container_file_name, local_file_name)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached  # Return cached success status

    # Perform the copy operation based on the environment.
    if settings.NGEN_ENVIRONMENT == NgenEnvironmentEnum.PARALLEL_WORKS:
        success = copy_file_from_singularity_image(
            os.path.join(settings.SINGULARITY_DIR, f'{image_name}.sif'),
            container_file_name,
            local_file_name
        )
    else:
        success = copy_file_from_docker_image(
            image_name,
            container_name,
            container_file_name,
            local_file_name
        )
    # Only cache if the operation was successful
    if success:
        cache.set(cache_key, success, timeout=0)

    return success
