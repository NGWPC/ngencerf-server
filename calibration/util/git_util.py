import json
import logging
import os
import shutil
from functools import cache

from django.conf import settings 

from calibration.enums_vanilla import JobExecutionMode
from calibration.util.git_info_cache import get_cached_git_info, acquire_git_info_cache_lock, release_git_info_cache_lock, wait_for_cached_git_info, \
    set_cached_git_info
from calibration.util.container_util import copy_file_from_image, copy_file_from_docker_image, copy_files_from_image
from calibration.util.file_util import copy_file

logger = logging.getLogger(__name__)


def get_git_info_internal() -> dict[str, dict[str, str]]:
    """
    Retrieve merged and normalized Git metadata.

    The shared Redis cache is checked first. On a cache miss, one worker loads
    the Git-information files while other workers wait for the cached result.

    Empty results are not cached, allowing a later request to retry after a
    temporary image-access or extraction failure.

    :return: Merged and normalized Git metadata keyed by component name, or an
             empty dictionary if the metadata cannot be retrieved.
    """
    git_info = get_cached_git_info()
    if git_info is not None:
        return git_info

    if acquire_git_info_cache_lock():
        try:
            # Check again after acquiring the lock in case another worker
            # populated the cache immediately before this lock was acquired.
            git_info = get_cached_git_info()
            if git_info is not None:
                return git_info

            git_info = _load_git_info_internal()
            set_cached_git_info(git_info)
            return git_info

        finally:
            release_git_info_cache_lock()

    # Another worker is currently loading the metadata.
    git_info = wait_for_cached_git_info()
    if git_info is not None:
        return git_info

    # The loading worker released its lock without producing a cached result.
    # Retry so this worker can attempt to acquire the lock and load the data.
    return get_git_info_internal()


def _load_git_info_internal() -> dict[str, dict[str, str]]:
    """
    Load Git information from local files and application images, merge the
    JSON documents, and normalize each component's metadata.

    This function performs the underlying file extraction and merge operation.
    It does not interact directly with the shared cache; caching and
    cross-worker coordination are handled by ``get_git_info_internal()``.

    The transformation rules are:
      - Always include 'release', 'build_date', and 'commit_hash'.
      - If 'tags' is non-empty, use it as 'release'.
      - If 'tags' is empty, construct 'release' as ``dev (<branch>)`` and include
        'commit_date', 'author', and 'message' when available.

    The function performs the following steps:
      1. Clears and recreates the temporary ``git_info`` directory under
         ``BASE_DIR``.
      2. Copies the local server and nwm-msw-mgr Git-information files into it.
      3. Copies Git-information files from:
           - nwm-cal-mgr, including ngen and ngen-bmi-forcing metadata
           - nwm-fcst-mgr
           - nwm-verf
           - ngencerf-ui
      4. Merges all successfully retrieved JSON files found in the temporary
         directory.
      5. Normalizes each component using ``transform_component()``.

    Required image-copy failures are logged and cause an empty result to be
    returned. Failure to retrieve the UI metadata is logged but does not
    prevent the remaining metadata from being returned.

    :return: Merged and normalized Git metadata keyed by component name, or an
             empty dictionary if a required image file cannot be retrieved.
    """
    base_dir = str(settings.BASE_DIR)
    repo_root = str(settings.REPO_ROOT)

    git_info_directory = os.path.join(base_dir, "git_info")
    if os.path.exists(git_info_directory):
        shutil.rmtree(git_info_directory)

    os.mkdir(git_info_directory)

    # Copy the server Git-information file into the temporary merge directory.
    src_git_info = os.path.join(
        base_dir,
        "ngencerf-server_git_info.json",
    )
    dest_git_info = os.path.join(
        git_info_directory,
        "ngencerf-server_git_info.json",
    )
    if os.path.exists(src_git_info):
        copy_file(src_git_info, dest_git_info)

    # Copy the nwm-msw-mgr Git-information file into the temporary merge directory.
    src_git_info = os.path.join(
        base_dir,
        "nwm-msw-mgr_git_info.json",
    )
    dest_git_info = os.path.join(
        git_info_directory,
        "nwm-msw-mgr_git_info.json",
    )
    if os.path.exists(src_git_info):
        copy_file(src_git_info, dest_git_info)

    # Track failures while retrieving metadata from required application images.
    required_images_success = True

    # Extract ngen-bmi-forcing, ngen, and nwm-cal-mgr metadata from one
    # nwm-cal-mgr SIF filesystem dump.
    image_name = "nwm-cal-mgr"
    container_name = f"{image_name}_temp_container"

    git_info_files = {
        os.path.join(repo_root, git_info_file):
            os.path.join(git_info_directory, git_info_file)
        for git_info_file in (
            "ngen-bmi-forcing_git_info.json",
            "ngen_git_info.json",
            "nwm-cal-mgr_git_info.json",
        )
    }

    if not copy_files_from_image(
            image_name,
            container_name,
            git_info_files,
    ):
        logger.error(
            "Failed to retrieve one or more Git-information files "
            f"from image {image_name}."
        )
        required_images_success = False

    # Extract nwm-fcst-mgr metadata.
    image_name = "nwm-fcst-mgr"
    container_name = f"{image_name}_temp_container"
    container_file_name = os.path.join(
        repo_root,
        f"{image_name}_git_info.json",
    )
    local_file_name = os.path.join(
        git_info_directory,
        f"{image_name}_git_info.json",
    )

    if not copy_file_from_image(
            image_name,
            container_name,
            container_file_name,
            local_file_name,
    ):
        logger.error(
            f"Failed to retrieve Git-information file from image {image_name}."
        )
        required_images_success = False

    # Extract nwm-verf metadata.
    image_name = "nwm-verf"
    container_name = f"{image_name}_temp_container"
    container_file_name = os.path.join(
        repo_root,
        f"{image_name}_git_info.json",
    )
    local_file_name = os.path.join(
        git_info_directory,
        f"{image_name}_git_info.json",
    )

    if not copy_file_from_image(
            image_name,
            container_name,
            container_file_name,
            local_file_name,
    ):
        logger.error(
            f"Failed to retrieve Git-information file from image {image_name}."
        )
        required_images_success = False

    if settings.JOB_EXECUTION_MODE == JobExecutionMode.SLURM:
        image_name = (
            f"ghcr.io/ngwpc/ngencerf-ui:{settings.NGENCERF_UI_TAG}"
        )
        container_name = "ngencerf-ui_temp_container"
        container_file_name = (
            "/var/www/ngencerf/nuxt-app/"
            "ngencerf-ui_git_info.json"
        )
        local_file_name = os.path.join(
            git_info_directory,
            "ngencerf-ui_git_info.json",
        )

        # The UI remains a Docker image even when compute jobs use SLURM/SIF
        # images. This currently requires a Docker daemon, which is not
        # available in the AWS ECS server container.
        if not copy_file_from_docker_image(
                image_name,
                container_name,
                container_file_name,
                local_file_name,
        ):
            logger.error(
                "Failed to retrieve the ngencerf-ui Git-information file "
                "from its Docker image."
            )
    else:
        ui_directory = os.path.join(
            os.path.dirname(base_dir),
            "ngencerf-ui",
        )
        git_info = os.path.join(
            ui_directory,
            "ngencerf-ui_git_info.json",
        )

        try:
            copy_file(
                git_info,
                os.path.join(
                    git_info_directory,
                    os.path.basename(git_info),
                ),
            )
        except FileNotFoundError:
            logger.warning(f"File {git_info} not found.")

    # Do not return incomplete metadata when a required image could not be read.
    if not required_images_success:
        return {}

    merged_data: dict[str, dict[str, str]] = {}

    # Merge every Git-information file that was retrieved successfully.
    for filename in os.listdir(git_info_directory):
        if not filename.endswith(".json"):
            continue

        filepath = os.path.join(git_info_directory, filename)
        logger.info(f"Merging {filepath}")

        try:
            with open(filepath, "r") as file:
                data = json.load(file)

            # Top-level component keys are expected to be unique.
            merged_data.update(data)

        except FileNotFoundError:
            logger.warning(f'File "{filepath}" not found')
            return {}

        except json.decoder.JSONDecodeError as e:
            logger.warning(f"Error reading {filepath}: {e}")
            return {}

    return {
        key: transform_component(value)
        for key, value in merged_data.items()
    }


def transform_component(component_git_info) -> dict[str, str]:
    """
    Transform a single component dictionary to include only selected Git fields in a specific order:
      - Always include 'release', 'build_date', and 'commit_hash' (in that order).
      - If 'tags' is empty, also include 'commit_date', 'author', and 'message' (in that order) if they exist.

    :param component_git_info: A dictionary containing Git information for a component.
    :return: A new dictionary with only the desired fields.
    """
    new_comp: dict[str, str] = {}

    tags = component_git_info.get("tags", "").strip()
    if tags == "":
        # If tags is empty, represent the development branch in the release field.
        branch = f"dev ({component_git_info.get('branch', '<unknown>')})"
        new_comp["release"] = branch
    else:
        new_comp["release"] = tags

    # Add build_date and commit_hash after the release field.
    new_comp["build_date"] = component_git_info.get("build_date", "")
    new_comp["commit_hash"] = component_git_info.get("commit_hash", "")

    # If tags is empty, add commit_date, author, and message in order, if they exist.
    if tags == "":
        if "commit_date" in component_git_info:
            new_comp["commit_date"] = component_git_info.get("commit_date", "")
        if "author" in component_git_info:
            new_comp["author"] = component_git_info.get("author", "")
        if "message" in component_git_info:
            new_comp["message"] = component_git_info.get("message", "")

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


GIT_INFO_FILE = 'ngencerf-server_git_info.json'


@cache
def load_git_info(git_info_file: str) -> dict[str, dict[str, str]] | None:
    """
    Load and transform Git information from a JSON file.

    This function reads Git metadata from the specified JSON file and applies a transformation
    to each top-level component to retain only relevant fields.

    Steps performed:
      1. Attempt to open and parse the JSON file.
      2. If the file does not exist, log a warning and return None.
      3. If the JSON content is malformed, log an error and return None.
      4. If the parsed content is empty, log an error and return None.
      5. Transform each component in the parsed JSON using `transform_component()`.
      6. Return the transformed Git information as a dictionary, or None on failure.

    :param git_info_file: Path to the JSON file containing Git information.
    :return: A dictionary with transformed Git metadata, or None if an error occurs.
    """
    try:
        with open(git_info_file, 'r') as f:
            git_info = json.load(f)
    except FileNotFoundError:
        logger.warning(f'{git_info_file} not found')
        return None
    except json.decoder.JSONDecodeError as e:
        logger.warning(f"Error reading {git_info_file}: {e}")
        return None

    if not git_info:
        logger.error(f"Failed to retrieve git information from {git_info_file}.")
        return None

    # Transform each top-level component without removing the keys.
    transformed_git_info = {key: transform_component(value) for key, value in git_info.items()}

    return transformed_git_info


def print_git_info(git_info_file: str) -> None:
    """
    Read the specified git_info JSON file, transform its contents, and log all key/value pairs recursively.

    The output will print top-level keys.

    :param git_info_file: Path to the JSON file containing Git information.
    """
    git_info = load_git_info(git_info_file)

    if git_info:
        recursive_print(git_info)


def print_git_info_all() -> None:
    """
    Print Git information from the server Git-information file.
    """

    print_git_info(GIT_INFO_FILE)
    logger.info(' ')
