import json
import logging
import os
import shutil

from django.conf import settings

from calibration.util.container_util import copy_file_from_image
from calibration.util.file_util import copy_file

logger = logging.getLogger(__name__)


def get_git_info_internal():
    """
    Gather Git information from multiple sources, merge the JSON files, and transform each component
    so that only the desired fields are retained. The transformation rules are:
      - Always include 'commit_hash' and 'build_date'.
      - If 'tags' is non-empty, include it (renamed to 'release').
      - If 'tags' is empty, include 'branch', 'author', 'message', and 'commit_date'.
      - Recursively process any nested 'modules'.

    The function performs the following steps:
      1. Clears and recreates a temporary directory (git_info) in BASE_DIR.
      2. Copies the local 'git_info.json' (generated externally) into this directory.
      3. For each defined image (ngen, ngen-cal, ngen-bmi-forcing, ngen-fcst), it copies its
         'git_info.json' from Docker (or Singularity) into the directory.
      4. Iterates over all JSON files in the directory and merges their contents into a single dict.
      5. Transforms each component in the merged data using transform_component().

    :return: A dictionary containing the merged and transformed Git information with the same
             top-level keys as the original merged data.
    """
    git_info_directory = os.path.join(settings.BASE_DIR, 'git_info')
    if os.path.exists(git_info_directory):
        shutil.rmtree(git_info_directory)

    os.mkdir(git_info_directory)

    # Copy our local git_info.json into the shared directory.
    src_git_info = os.path.join(settings.BASE_DIR, 'git_info.json')
    dest_git_info = os.path.join(git_info_directory, 'cerfserver_git_info.json')
    if os.path.exists(src_git_info):
        copy_file(src_git_info, dest_git_info)

    # For each image, copy its git_info.json into the shared directory.

    # Get both ngen and ngen-cal git_info files from ngen-cal container
    image_name = 'ngen-cal'
    container_name = f'{image_name}_temp_container'
    container_file_name = os.path.join(settings.REPO_ROOT, 'ngen_git_info.json')
    local_file_name = os.path.join(git_info_directory, 'ngen_git_info.json')
    copy_file_from_image(container_name, container_file_name, image_name, local_file_name)

    container_file_name = os.path.join(settings.REPO_ROOT, 'ngen-cal_git_info.json')
    local_file_name = os.path.join(git_info_directory, 'ngen-cal_git_info.json')
    copy_file_from_image(container_name, container_file_name, image_name, local_file_name)

    image_name = 'ngen-fcst'
    container_name = f'{image_name}_temp_container'
    container_file_name = os.path.join(settings.REPO_ROOT, f"{image_name}_git_info.json")
    local_file_name = os.path.join(git_info_directory, f"{image_name}_git_info.json")
    copy_file_from_image(container_name, container_file_name, image_name, local_file_name)

    image_name = 'ngen-bmi-forcing'
    container_name = f'{image_name}_temp_container'
    container_file_name = os.path.join(settings.REPO_ROOT, f"{image_name}_git_info.json")
    local_file_name = os.path.join(git_info_directory, f"{image_name}_git_info.json")
    copy_file_from_image(container_name, container_file_name, image_name, local_file_name)

    merged_data = {}
    # Iterate over all JSON files in the directory and merge them.
    for filename in os.listdir(git_info_directory):
        if filename.endswith('.json'):
            filepath = os.path.join(git_info_directory, filename)
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    # Merge data; top-level keys should be unique.
                    merged_data.update(data)
            except FileNotFoundError:
                logger.warning(f'File "{filepath}" not found')
                return {}
            except json.decoder.JSONDecodeError as e:
                logger.warning(f"Error reading {filepath}: {e}")
                return {}

    # Transform each component in merged_data so that only the desired fields are retained.
    transformed_data = {key: transform_component(value) for key, value in merged_data.items()}

    return transformed_data


def transform_component(comp):
    """
    Transform a single component dictionary to include only selected Git fields.

    The transformation rules are:
      - Always include 'commit_hash' and 'build_date'.
      - If 'tags' is non-empty, include the 'tags' field (renamed to 'release').
      - If 'tags' is empty, include 'branch', 'author', 'message', and 'commit_date'.
      - Recursively transform nested 'modules' (if present).

    :param comp: A dictionary containing Git information for a component.
    :return: A new dictionary with only the desired fields.
    """
    new_comp = {
        "commit_hash": comp.get("commit_hash", ""),
        "build_date": comp.get("build_date", "")
    }
    if comp.get("tags", "").strip() == "":
        # If tags is empty, include branch, author, message, and commit_date.
        new_comp["branch"] = comp.get("branch", "")
        new_comp["author"] = comp.get("author", "")
        new_comp["message"] = comp.get("message", "")
        new_comp["commit_date"] = comp.get("commit_date", "")
    else:
        # If tags is non-empty, include tags.
        new_comp["release"] = comp.get("tags", "")

    # Process nested modules recursively, if present
    if "modules" in comp and isinstance(comp["modules"], list):
        new_modules = []
        for module_obj in comp["modules"]:
            # Each module is an object with one key-value pair.
            for mod_name, mod_data in module_obj.items():
                new_modules.append({mod_name: transform_component(mod_data)})
        new_comp["modules"] = new_modules

    return new_comp


def recursive_print(d: dict, indent: int = 0) -> None:
    """
    Recursively print all key/value pairs from a dictionary.

    For each key-value pair:
      - If the value is a dictionary, print the key on one line and then recurse into that dictionary.
      - If the value is a list, print the key on one line and then iterate through the list;
        for each element that is a dictionary, recurse into it; otherwise print the element on a separate line.
      - Otherwise (if the value is a string or other non-dict, non-list), print the key and value on one line.

    :param d: The dictionary to print.
    :param indent: The current indentation level (number of spaces).
    """
    for key, value in d.items():
        if isinstance(value, dict):
            logger.info(" " * indent + f"{key}:")
            recursive_print(value, indent + 2)
        elif isinstance(value, list):
            logger.info(" " * indent + f"{key}:")
            for item in value:
                if isinstance(item, dict):
                    recursive_print(item, indent + 2)
                else:
                    logger.info(" " * (indent + 2) + str(item))
        else:
            logger.info(" " * indent + f"{key}: {value}")


def print_git_info(git_info_file: str):
    """
    Read the specified git_info JSON file, transform its contents, and log all key/value pairs recursively.

    The output will print top-level keys (such as 'ngen') as well as keys for nested modules (such as 'LASAM').

    :param git_info_file: Path to the JSON file containing Git information.
    """
    try:
        with open(git_info_file, 'r') as f:
            git_info = json.load(f)
    except FileNotFoundError:
        logger.warning(f'{git_info_file} not found')
        return
    except json.decoder.JSONDecodeError as e:
        logger.warning(f"Error reading {git_info_file}: {e}")
        return

    if not git_info:
        logger.error(f"Failed to retrieve git information from {git_info_file}.")
        return

    # Transform each top-level component without removing the keys.
    transformed_git_info = {key: transform_component(value) for key, value in git_info.items()}

    recursive_print(transformed_git_info)


def print_git_info_all():
    """
    Convenience function to print Git information from multiple JSON files.
    """
    print_git_info('git_info.json')
    logger.info(' ')
