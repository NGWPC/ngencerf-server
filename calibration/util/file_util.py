import logging
import os
import shutil

logger = logging.getLogger(__name__)


def copy_directory(source_dir, destination_dir):
    """
    Copy the contents of source_dir to destination_dir. If destination_dir
    does not exist, it will be created.

    :param source_dir: Path to the source directory to be copied
    :param destination_dir: Path to the destination directory
    """
    # Check if the source directory exists
    if not os.path.exists(source_dir):
        raise FileNotFoundError(f"Source directory {source_dir} does not exist.")

    # Check if the destination directory exists, if not, create it
    if not os.path.exists(destination_dir):
        os.makedirs(destination_dir)

    # Copy the contents of the source directory to the destination directory
    shutil.copytree(source_dir, destination_dir, dirs_exist_ok=True)

    return f"Directory successfully copied from {source_dir} to {destination_dir}."


def copy_file_to_directory(source_file: str, destination_dir: str):
    """
    Copy a file to a directory. The file will be copied with the same name
    into the destination directory.

    :param source_file: Path to the source file to be copied
    :param destination_dir: Path to the destination directory
    """
    # Check if the source file exists
    if not os.path.exists(source_file):
        raise FileNotFoundError(f"Source file {source_file} does not exist.")

    # Ensure the destination directory exists, if not, create it
    if not os.path.exists(destination_dir):
        os.makedirs(destination_dir)

    # Construct the full path for the destination file
    destination_file = os.path.join(destination_dir, os.path.basename(source_file))

    # Copy the source file to the destination directory
    shutil.copy2(source_file, destination_file)

    return f"File successfully copied from {source_file} to {destination_dir}."
