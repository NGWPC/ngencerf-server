import json
import logging
import os
import shutil

from django.conf import settings

from calibration.enums_vanilla import NgenEnvironmentEnum
from calibration.util.container_util import copy_file_from_docker_image, copy_file_from_singularity_image
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
    for image_name in ['ngen', 'ngen-cal', 'ngen-bmi-forcing', 'ngen-fcst']:
        container_name = f'{image_name}_temp_container'
        container_properties = os.path.join(settings.REPO_ROOT, 'git_info.json')
        local_properties = os.path.join(git_info_directory, f"{image_name}_git_info.json")
        if settings.NGEN_ENVIRONMENT == NgenEnvironmentEnum.PARALLEL_WORKS:
            copy_file_from_singularity_image(
                os.path.join(settings.SINGULARITY_DIR, f'{image_name}.sif'),
                container_properties,
                local_properties
            )
        else:
            copy_file_from_docker_image(
                image_name,
                container_name,
                container_properties,
                local_properties
            )

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
      - If 'tags' is non-empty, include the 'tags' field.
      - If 'tags' is empty, include 'branch', 'author', 'message', and 'commit_date'.
      - Recursively transform nested 'modules' (if present) with the same rules.

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


def print_git_info():
    """
    Read the combined git_info.json file, transform its contents,
    and log each key-value pair.

    If the file is not found or contains invalid JSON, logs a warning.
    """
    GIT_INFO = 'git_info.json'
    try:
        with open(GIT_INFO, 'r') as f:
            git_info = json.load(f)
    except FileNotFoundError:
        logger.warning(f'{GIT_INFO} not found')
        return
    except json.decoder.JSONDecodeError as e:
        logger.warning(f"Error reading {GIT_INFO}: {e}")
        return

    if not git_info:
        logger.error(f"Failed to retrieve git information from {GIT_INFO}.")
        return

    # Assuming there is only one top-level key in the file.
    name, git_info_content = git_info.popitem()

    transformed_git_info = transform_component(git_info_content)
    for key, value in transformed_git_info.items():
        logger.info(f'{key}: {value}')
