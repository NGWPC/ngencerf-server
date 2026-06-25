import hashlib
import logging
import os
import re
import shutil
import subprocess
import tempfile
import uuid

from django.conf import settings
from django.core.cache import cache

from calibration.enums_vanilla import JobExecutionMode

logger = logging.getLogger(__name__)


def _indent_output(output: str, indent: int = 2) -> str:
    """Indent each line of output by `indent` spaces."""
    if not output:
        return ""
    prefix = " " * indent
    return "\n".join(prefix + line for line in output.splitlines())


# noinspection PyTypeChecker
def copy_file_from_docker_image(image_name: str, container_name: str, src_path: str, dest_path: str) -> bool:
    """
    Copies a file from a Docker image using a temporary container and ensures cleanup.
      - Automatically appends a unique suffix to avoid name collisions.
      - Best-effort stale container cleanup for the base prefix.
      - Preserves all existing logging and structure.

    :param image_name: Name of the Docker image.
    :param container_name: Temporary container name.
    :param src_path: Path to the file inside the container.
    :param dest_path: Destination path on the host system.
    :return: True if the copy succeeds, False otherwise.
    """
    success = False  # Default to failure

    # Add a guaranteed-unique suffix to avoid container name collisions
    unique_name = f"{container_name}_{uuid.uuid4().hex[:8]}"

    # Clean stale containers based on prefix (best effort)
    # IMPORTANT: match the UUID-suffixed names
    try:
        ps = subprocess.run(
            ["docker", "ps", "-a", "--filter", f"name={container_name}_", "-q"],
            capture_output=True, text=True
        )
        stale_ids = [c.strip() for c in ps.stdout.splitlines() if c.strip()]
        for cid in stale_ids:
            subprocess.run(["docker", "rm", "-f", cid], capture_output=True, text=True)
    except Exception as e:
        logger.warning(f"Failed to clean stale containers for prefix {container_name}: {e}")

    # Basic sanity checks
    if shutil.which("docker") is None:
        logger.error("Docker binary not found on PATH.")
        return False

    dest_parent = os.path.dirname(dest_path) or "."
    if not os.path.isdir(dest_parent):
        logger.error(f"Destination directory does not exist: {dest_parent}")
        return False

    # Step 1: Create a temporary container
    create_cmd = ["docker", "create", "--name", unique_name, image_name]
    logger.debug(create_cmd)
    try:
        create_response = subprocess.run(create_cmd, check=True, capture_output=True, text=True)
        if create_response.stdout:
            container_id = create_response.stdout.strip()
            logger.info(f"Created temporary container {unique_name} (ID={container_id[:12]})")
        if create_response.stderr:
            logger.debug(f"[docker create stderr]\n{_indent_output(create_response.stderr.strip())}")

    except subprocess.CalledProcessError as e:
        logger.error(
            "Failed to create temporary container "
            f"(exit={e.returncode}).\n"
            f"Command: {' '.join(create_cmd)}\n"
            f"STDOUT:\n{_indent_output((e.stdout or '').strip())}\n"
            f"STDERR:\n{_indent_output((e.stderr or '').strip())}"
        )
        # Attempt best-effort cleanup in case the name was already taken
        try:
            subprocess.run(["docker", "rm", "-f", unique_name], capture_output=True, text=True)
        except Exception:
            pass
        return False

    # Step 2: Copy the file from the container
    copy_cmd = ["docker", "cp", f"{unique_name}:{src_path}", dest_path]
    logger.debug(copy_cmd)
    try:
        copy_response = subprocess.run(copy_cmd, check=True, capture_output=True, text=True)
        if copy_response.stdout:
            logger.debug(f"[docker cp stdout]\n{_indent_output(copy_response.stdout.strip())}")
        if copy_response.stderr:
            # docker cp commonly prints nothing, but capture it if present
            logger.debug(f"[docker cp stderr]\n{_indent_output(copy_response.stderr.strip())}")

        logger.info(f"Successfully copied {src_path} to {dest_path}")
        success = True

    except subprocess.CalledProcessError as e:
        logger.error(
            "Error copying file from Docker container "
            f"(exit={e.returncode}).\n"
            f"Command: {' '.join(copy_cmd)}\n"
            f"STDOUT:\n{_indent_output((e.stdout or '').strip())}\n"
            f"STDERR:\n{_indent_output((e.stderr or '').strip())}"
        )

    finally:
        # Step 3: Remove the temporary container (always runs, even if copy fails)
        rm_cmd = ["docker", "rm", "-f", unique_name]
        rm_response = subprocess.run(rm_cmd, capture_output=True, text=True)
        if rm_response.returncode != 0:
            logger.warning(
                "Failed to remove temporary container "
                f"(exit={rm_response.returncode}).\n"
                f"Command: {' '.join(rm_cmd)}\n"
                f"STDOUT:\n{_indent_output((rm_response.stdout or '').strip())}\n"
                f"STDERR:\n{_indent_output((rm_response.stderr or '').strip())}"
            )
        else:
            logger.debug(f"Removed temporary container {unique_name}")

    return success


def _find_sif_squashfs_id(image_path: str) -> int:
    """
    Find the descriptor ID of the SquashFS root filesystem inside a SIF image.

    :param image_path: Path to the Singularity image file.
    :return: SIF descriptor ID containing the SquashFS filesystem.
    :raises RuntimeError: If the SIF cannot be inspected or no SquashFS
                          filesystem descriptor is found.
    """
    list_cmd = ["singularity", "sif", "list", image_path]
    logger.debug(list_cmd)

    try:
        result = subprocess.run(
            list_cmd,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            "Unable to inspect Singularity image.\n"
            f"Command: {' '.join(list_cmd)}\n"
            f"STDOUT:\n{_indent_output((e.stdout or '').strip())}\n"
            f"STDERR:\n{_indent_output((e.stderr or '').strip())}"
        ) from e

    logger.debug(
        f"[singularity sif list stdout]\n"
        f"{_indent_output(result.stdout.strip())}"
    )

    if result.stderr:
        logger.debug(
            f"[singularity sif list stderr]\n"
            f"{_indent_output(result.stderr.strip())}"
        )

    # Typical output contains a row similar to:
    #
    # 4    |1     |NONE |... |FS (Squashfs/*System/amd64)
    #
    # Match the descriptor ID at the beginning of a row containing a
    # SquashFS filesystem object.
    match = re.search(
        r"^\s*(\d+)\s*\|[^\n]*\bFS\s*\(\s*Squashfs\b",
        result.stdout,
        flags=re.MULTILINE | re.IGNORECASE,
    )

    if not match:
        raise RuntimeError(
            f"No SquashFS filesystem descriptor was found in SIF image {image_path}.\n"
            f"singularity sif list output:\n"
            f"{_indent_output(result.stdout.strip())}"
        )

    return int(match.group(1))


def copy_file_from_singularity_image(
        image_path: str,
        src_path: str,
        dest_path: str
) -> bool:
    """
    Copy a file from a Singularity image without executing the image.

    The SquashFS root filesystem object is dumped from the SIF into a
    temporary file. The requested file is then streamed directly from the
    SquashFS filesystem using ``unsquashfs -cat``.

    This approach does not require Singularity to create a user namespace,
    mount the image, create a sandbox, or execute a command inside the image.

    :param image_path: Path to the Singularity image file (.sif).
    :param src_path: Absolute or relative path to the file inside the image.
    :param dest_path: Destination path on the host system.
    :return: True if the file is copied successfully; otherwise False.
    """
    logger.info(f"Copy file {src_path} from image {image_path}")

    # Quick checks that commonly cause exit=1
    if shutil.which("singularity") is None:
        logger.error("singularity binary not found on PATH.")
        return False

    if shutil.which("unsquashfs") is None:
        logger.error(
            "unsquashfs binary not found on PATH. "
            "Install the squashfs-tools operating-system package."
        )
        return False

    # Check if the path exists
    if not os.path.exists(image_path):
        # If it's a symlink, check whether it's broken
        if os.path.islink(image_path):
            target = os.readlink(image_path)
            logger.error(
                f"Image path {image_path} is a symlink to {target}, "
                "but the target does not exist."
            )
        else:
            logger.error(f"Image {image_path} does not exist.")

        return False

    if not os.path.isfile(image_path):
        logger.error(f"Image path is not a regular file: {image_path}")
        return False

    dest_parent = os.path.dirname(dest_path) or "."

    if not os.path.isdir(dest_parent):
        logger.error(
            f"Destination directory does not exist on host: {dest_parent}"
        )
        return False

    # unsquashfs expects the path relative to the root of the SquashFS
    # filesystem rather than an absolute path.
    normalized_src_path = src_path.lstrip("/")

    if not normalized_src_path:
        logger.error("Source path cannot refer to the image root directory.")
        return False

    temporary_dest_path: str | None = None

    try:
        filesystem_id = _find_sif_squashfs_id(image_path)

        logger.debug(
            f"Using SIF SquashFS descriptor ID {filesystem_id} "
            f"from image {image_path}"
        )

        with tempfile.TemporaryDirectory(prefix="ngencerf-sif-") as temp_dir:
            squashfs_path = os.path.join(temp_dir, "rootfs.squashfs")

            dump_cmd = [
                "singularity",
                "sif",
                "dump",
                str(filesystem_id),
                image_path,
            ]
            logger.debug(dump_cmd)

            with open(squashfs_path, "wb") as squashfs_file:
                dump_result = subprocess.run(
                    dump_cmd,
                    check=True,
                    stdout=squashfs_file,
                    stderr=subprocess.PIPE,
                )

            if dump_result.stderr:
                logger.debug(
                    "[singularity sif dump stderr]\n"
                    + _indent_output(
                        dump_result.stderr.decode(
                            errors="replace"
                        ).strip()
                    )
                )

            # Write to a temporary file in the destination directory first.
            # os.replace() then makes the final update atomic and avoids
            # leaving a partial destination file when extraction fails.
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{os.path.basename(dest_path)}.",
                suffix=".tmp",
                dir=dest_parent,
                delete=False,
            ) as temporary_dest:
                temporary_dest_path = temporary_dest.name

                extract_cmd = [
                    "unsquashfs",
                    "-cat",
                    squashfs_path,
                    normalized_src_path,
                ]
                logger.debug(extract_cmd)

                extract_result = subprocess.run(
                    extract_cmd,
                    check=True,
                    stdout=temporary_dest,
                    stderr=subprocess.PIPE,
                )

            if extract_result.stderr:
                logger.debug(
                    "[unsquashfs -cat stderr]\n"
                    + _indent_output(
                        extract_result.stderr.decode(
                            errors="replace"
                        ).strip()
                    )
                )

            assert temporary_dest_path is not None

            if os.path.getsize(temporary_dest_path) == 0:
                raise RuntimeError(
                    f"Extracted file {src_path} from {image_path} is empty."
                )

            os.replace(temporary_dest_path, dest_path)
            temporary_dest_path = None

        logger.info(
            f"Successfully copied {src_path} from {image_path} to {dest_path}"
        )
        return True

    except RuntimeError as e:
        logger.error(str(e))

    except subprocess.CalledProcessError as e:
        stdout = e.stdout
        stderr = e.stderr

        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")

        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")

        logger.error(
            "Error copying file from Singularity image "
            f"(exit={e.returncode}).\n"
            f"Command: {' '.join(str(arg) for arg in e.cmd)}\n"
            f"STDOUT:\n{_indent_output((stdout or '').strip())}\n"
            f"STDERR:\n{_indent_output((stderr or '').strip())}"
        )

    except OSError as e:
        logger.error(
            f"Operating-system error while copying {src_path} "
            f"from {image_path} to {dest_path}: {e}"
        )

    finally:
        if temporary_dest_path is not None:
            try:
                os.remove(temporary_dest_path)
            except FileNotFoundError:
                pass
            except OSError as e:
                logger.warning(
                    f"Unable to remove temporary file "
                    f"{temporary_dest_path}: {e}"
                )

    return False


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
    if settings.JOB_EXECUTION_MODE == JobExecutionMode.SLURM:
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
