import logging
import os
import subprocess

logger = logging.getLogger(__name__)


def copy_file_from_docker_image(image_name: str, container_name: str, src_path: str, dest_path: str) -> bool:
    """
    Copies a file from a Docker image using a temporary container and ensures cleanup.

    :param image_name: Name of the Docker image
    :param container_name: Temporary container name
    :param src_path: Path to the file inside the container
    :param dest_path: Destination path on the host system
    :return: True if the copy succeeds, False otherwise
    """
    success = False  # Default to failure

    try:
        # Step 1: Create a temporary container
        create_cmd = ["docker", "create", "--name", container_name, image_name]
        subprocess.run(create_cmd, check=True, capture_output=True, text=True)

        # Step 2: Copy the file from the container
        copy_cmd = ["docker", "cp", f"{container_name}:{src_path}", dest_path]
        subprocess.run(copy_cmd, check=True)

        logger.info(f"Successfully copied {src_path} to {dest_path}")
        success = True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error copying file: {e.stderr or str(e)}")  # Print error message
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

    logger.info(f'copy_file_from_singularity_image: {image_path}')

    if os.path.exists(image_path):
        try:
            # Step 1: Execute the Singularity command to copy the file
            copy_cmd = ["singularity", "exec", image_path, "cp", src_path, dest_path]
            subprocess.run(copy_cmd, check=True)

            logger.info(f"Successfully copied {src_path} from {image_path} to {dest_path}")
            success = True
        except subprocess.CalledProcessError as e:
            logger.error(f"Error copying file: {e.stderr or str(e)}")
    else:
        logger.error(f"Image {image_path} does not exist")

    return success
