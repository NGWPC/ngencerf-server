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
    if not os.path.isdir(source_dir):
        raise FileNotFoundError(f"Source directory {source_dir} does not exist or is not a directory.")

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
    if not os.path.isfile(source_file):
        raise FileNotFoundError(f"Source file {source_file} does not exist or is not a file.")

    # Ensure the destination directory exists, if not, create it
    if not os.path.exists(destination_dir):
        os.makedirs(destination_dir)

    # Construct the full path for the destination file
    destination_file = os.path.join(destination_dir, os.path.basename(source_file))

    # Copy the source file to the destination directory
    shutil.copy2(source_file, destination_file)

    return f"File successfully copied from {source_file} to {destination_dir}."


def delete_all_files_in_directory(source_dir):
    if os.path.isdir(source_dir):
        for filename in os.listdir(source_dir):
            file_path = os.path.join(source_dir, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)


def get_single_file(source_dir):
    """
    Retrieves the first file found in the given directory.
    If the directory is empty, it returns None. If more than one file exists,
    it issues a warning but still returns the first file.

    :param source_dir: Path to the directory where the file is located.
    :return: The file name (string) of the first file found, or None if no file exists.
    """
    if not os.path.isdir(source_dir):
        return None

    # Get all files in the directory (excluding directories)
    files = [f for f in os.listdir(source_dir) if os.path.isfile(os.path.join(source_dir, f))]

    # If there are no files in the directory, return None.
    if not files:
        return None

    if len(files) > 1:
        logger.warning(f"Multiple files found in directory '{source_dir}'. Returning the first file: {files[0]}")

    return os.path.join(source_dir, files[0])

