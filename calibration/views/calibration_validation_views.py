import io
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from datetime import timezone
from time import time
from urllib.parse import urlparse

import boto3
import pandas as pd
import pyarrow
import pyarrow.csv as pacsv
from botocore.exceptions import ClientError
from django.conf import settings

from calibration.util.aws_util import list_s3_csv_files, s3_prefix_exists
from calibration.util.caching import get_cached_gages

logger = logging.getLogger(__name__)


def data_validation_job(
        gages: list[str] | None,
        forcing_dir: str | None,
        start: int | None = None,
        limit: int | None = None
) -> None:
    """
    Entry point for initiating a data validation job across multiple gages.

    Accepts either local or S3 forcing directories, verifies they exist, and
    runs file validation for selected gages or ranges.

    Determines the output file path, validates the list of gage IDs (if provided),
    resolves the list of forcing directories, and writes a log file summarizing
    errors found during validation.

    :param gages: Optional list of gage IDs to restrict validation to.
    :param forcing_dir: Optional root directory containing forcing data.
    :param start: Optional index for slicing the list of gages.
    :param limit: Optional number of gages to validate, starting from `start`.
    """
    # Determine suffix and description for output file
    if gages:
        suffix = "selected_gages"
        # Break the gage list into lines of 10
        gage_lines = [', '.join(gages[i:i + 10]) for i in range(0, len(gages), 10)]
        filter_description = "selected gages:\n" + '\n'.join(f"    {line}" for line in gage_lines)
    elif start is not None and limit is not None:
        headwater_gages = get_headwater_gages()
        sliced = headwater_gages[start:start + limit]
        gage_ids = [g['gage_id'] for g in sliced]
        suffix = f"range_{start}_{start + limit - 1}"
        gage_lines = [', '.join(gage_ids[i:i + 10]) for i in range(0, len(gage_ids), 10)]
        filter_description = f"range {start} to {start + limit - 1}, gages:\n" + '\n'.join(f"    {line}" for line in gage_lines)
    else:
        suffix = "all"
        filter_description = "all"

    now = datetime.now(timezone.utc).strftime('%Y_%m_%d_%H_%M_%S')
    output_txt_path = os.path.join(settings.BASE_DIR, 'logs', f"validation_output_{suffix}_{now}.txt")

    # Write header immediately
    header = [
        f"Validation run started: {now} UTC",
        f"Gage filter: {filter_description}",
        f"Forcing directory: {forcing_dir if forcing_dir else 'default from settings'}",
        "-" * 80
    ]

    try:
        with open(output_txt_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(header) + '\n')
    except Exception as e:
        logger.warning(f"Could not initialize validation output file '{output_txt_path}': {e}")

    msg = f"Writing validation output to: {output_txt_path}"
    logger.info(msg)
    # flush_log_handlers()
    append_to_validation_output(msg, output_txt_path)
    append_to_validation_output(' ', output_txt_path)

    forcing_directories = []
    raw_dirs = [forcing_dir] if forcing_dir else settings.FORCING_DATA_DIRS

    for d in raw_dirs:
        if d.startswith("s3://"):
            if not s3_prefix_exists(d):
                raise ValueError(f"Invalid forcing_dir: '{d}' is not a valid S3 prefix")
        else:
            if not os.path.isdir(d):
                raise ValueError(f"Invalid forcing_dir: '{d}' is not a valid directory")
        forcing_directories.append(d)

    # Validate gage_ids before proceeding
    cached_gage_map = get_cached_gages()
    gage_ids_filter = set(gages) if gages else None

    if gage_ids_filter:
        gage_errors = [gage_id for gage_id in gage_ids_filter if gage_id not in cached_gage_map]
        if gage_errors:
            raise ValueError(f'These gages do not exist: {gage_errors}')

    logger.info(f"Using forcing directories: {forcing_directories}")
    # flush_log_handlers()

    validate_files(forcing_directories, gages, start, limit, output_txt_path)


def validate_files(
        forcing_directories: list[str],
        gages: list[str] | None,
        start: int | None,
        limit: int | None,
        output_txt_path: str
) -> None:
    """
    Validates forcing files for a set of gages using threads.

    If `gages` is provided, only those are validated. Otherwise, headwater
    calibration gages are used, possibly sliced with `start` and `limit`.

    Each gage is validated in a separate thread (limited to one at a time), and
    errors are appended to a shared validation output file.

    :param forcing_directories: List of root paths to search for forcing data.
    :param gages: Optional list of gage IDs to validate.
    :param start: Optional start index for slicing the headwater gage list.
    :param limit: Optional number of gages to validate starting at `start`.
    :param output_txt_path: Path to write error messages.
    """
    logger.info("Starting validation...")
    # flush_log_handlers()

    try:
        gage_ids_filter = set(gages) if gages else None

        # Filter and sort gages
        gage_list = [{
            'gage_id': gage.get('gage_id'),
            'domain': gage.get('domain').replace('_', ' '),
        } for gage in get_headwater_gages()
            if (gage_ids_filter and gage.get('gage_id') in gage_ids_filter)
               or (gage_ids_filter is None)]

        # Slice if start and limit are provided
        if start is not None and limit is not None:
            gage_list = gage_list[start:start + limit]
            actual_gage_ids = [g['gage_id'] for g in gage_list]
            header_msg = f"Validating gages {start} through {start + limit - 1} (IDs: {actual_gage_ids})"

        elif gage_ids_filter:
            header_msg = f"Validating specific gages: {sorted(gage_ids_filter)}"
        else:
            header_msg = "Validating all headwater calibration gages"

        logger.info(header_msg)

        total = len(gage_list)

        # Limit the number of gages processed in parallel to avoid excessive thread usage
        # Just doing 1 gage at a time.  We are still processing multiple files at a time
        max_parallel_gages = 2

        with ThreadPoolExecutor(max_workers=max_parallel_gages) as executor:
            futures = []
            for i, g in enumerate(gage_list, start=1):
                logger.info(f"Queuing gage {g['gage_id']} ({i} of {total})")
                # flush_log_handlers()
                futures.append(executor.submit(validate_gage_data, g, forcing_directories, i, total, output_txt_path))

            completed = 0
            for future in as_completed(futures):
                try:
                    future.result()
                    completed += 1
                except Exception as e:
                    logger.exception(f"Exception in gage thread: {e}")
                    msg = f"validate_files: Unhandled exception in gage thread: {e}"
                    logger.warning(msg)
                    append_to_validation_output(msg, output_txt_path)
                # flush_log_handlers()

        final_msg = f"Finished validating {completed} of {total} gages"
        logger.info(final_msg)
        append_to_validation_output(final_msg, output_txt_path)
        logger.info(f"Output is in {output_txt_path}")
        # flush_log_handlers()
        append_to_validation_output(final_msg, output_txt_path)

    except Exception as e:
        msg = f"validate_files: Unhandled exception during validation: {e}"
        logger.exception("Unhandled exception during validation")
        logger.warning(msg)
        append_to_validation_output(msg, output_txt_path)
        # flush_log_handlers()


def parse_timestamp(dir_name: str) -> datetime | None:
    try:
        return datetime.strptime(dir_name, "%Y_%b_%d_%H_%M_%S")
    except ValueError:
        return None


def get_latest_timestamp_directory(dir_name: str) -> str:
    # Get full paths to valid timestamped subdirectories
    dated_dirs = []
    for d in os.listdir(dir_name):
        full_path = os.path.join(dir_name, d)
        if os.path.isdir(full_path):
            dt = parse_timestamp(d)
            if dt:
                dated_dirs.append((dt, full_path))

    if not dated_dirs:
        raise RuntimeError("No valid timestamped directories found.")

    # Get the latest one
    latest_dt, latest_dir = max(dated_dirs, key=lambda pair: pair[0])

    return latest_dir


def validate_csv_directory(dir_path: str, output_file_path: str | None = None) -> None:
    """
    Validates all .csv files in a local or S3 directory using concurrent threads.
    """
    is_s3 = dir_path.startswith("s3://")

    try:
        if is_s3:
            if not s3_prefix_exists(dir_path):
                logger.warning(f"{dir_path}: S3 prefix does not exist or is empty")
                # flush_log_handlers()
                return
            csv_files = list_s3_csv_files(dir_path)
        else:
            if not os.path.isdir(dir_path):
                logger.warning(f"{dir_path}: Provided path is not a directory")
                # flush_log_handlers()
                return
            csv_files = sorted([
                os.path.join(dir_path, f)
                for f in os.listdir(dir_path)
                if f.lower().endswith(".csv")
            ])
    except Exception as e:
        logger.warning(f"{dir_path}: Failed to list files: {e}")
        # flush_log_handlers()
        return

    total_files = len(csv_files)
    msg = f"Validating forcing directory {dir_path} ({total_files} files)"
    logger.info(msg)
    # flush_log_handlers()
    append_to_validation_output(msg, output_file_path)

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {}
        for i, path in enumerate(csv_files, start=1):
            try:
                future = executor.submit(
                    validate_csv_file,
                    path,
                    file_index=i,
                    total_files=total_files,
                    output_file_path=output_file_path
                )
                futures[future] = path
                logger.info(f"Submitted {path} to executor ({i} of {total_files})")
                # flush_log_handlers()
            except Exception as e:
                logger.warning(f"{path}: Exception during executor.submit: {e}")
        # flush_log_handlers()

        for future in as_completed(futures):
            path = futures[future]
            try:
                future.result()
            except Exception as e:
                logger.warning(f"{path}: Unhandled exception during validation: {e}")
            # flush_log_handlers()


def open_csv_file(path: str) -> tuple[io.IOBase, int]:
    """
    Opens a CSV file for reading, supporting both local files and S3 URIs.

    Uses fsspec to abstract access to local or cloud storage. Automatically checks
    for file existence and raises an error if the file cannot be opened.

    :param path: Local file path or S3 URI (e.g., s3://bucket/key.csv).
    :return: Tuple containing:
        - A readable file-like stream object.
        - File size in bytes.
    :raises FileNotFoundError: If the file cannot be opened.
    """
    parsed = urlparse(path)

    if parsed.scheme == 's3':
        bucket = parsed.netloc
        key = parsed.path.lstrip('/')
        s3 = boto3.client('s3')
        try:
            response = s3.get_object(Bucket=bucket, Key=key)
            stream = response['Body']
            size = response.get('ContentLength', 0)
            return stream, size
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                raise FileNotFoundError(f"S3 file not found: s3://{bucket}/{key}")
            else:
                raise

    else:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Local file not found: {path}")
        size = os.path.getsize(path)
        stream = open(path, 'rb')
        return stream, size


def validate_csv_file(path: str, file_index: int, total_files: int, output_file_path: str) -> None:
    """
    Validates a single CSV file (either local or S3) containing forcing data.
    Ensures that the file:
      - Has 9 columns.
      - The first column is a timestamp.
      - Timestamps are strictly increasing.
      - All remaining columns are valid floats.

    :param path: Path to the CSV file (local or S3).
    :param file_index: Index of this file in the validation batch (1-based).
    :param total_files: Total number of files in the batch.
    :param output_file_path: Path to write validation error messages.
    """
    start_time = time()

    try:
        stream, file_size = open_csv_file(path)
        file_size_mb = file_size / (1024 * 1024)
        msg = f"Validating forcing file {path} ({file_index} of {total_files}) ({file_size_mb:.2f} MB)"
        logger.info(msg)
        # flush_log_handlers()
        append_to_validation_output(msg, output_file_path)

        read_options = pacsv.ReadOptions(block_size=1_000_000)
        table = pacsv.read_csv(stream, read_options=read_options)

        errors = validate_chunk(table, path, chunk_index=1)
        for error in errors:
            append_to_validation_output(error, output_file_path)

    except Exception as e:
        error_text = f"Error while validating {path}: {type(e).__name__}: {e}"
        logger.warning(error_text)
        append_to_validation_output(error_text, output_file_path)

    elapsed = time() - start_time
    minutes, seconds = divmod(int(elapsed), 60)
    msg = f"    Finished validating forcing file {path} ({file_index} of {total_files}) in {minutes}:{seconds:02d}"
    logger.info(msg)
    append_to_validation_output(msg, output_file_path)


def validate_chunk(table: pyarrow.Table, path: str, chunk_index: int) -> list[str]:
    """
    Validates a chunk of data from a forcing CSV file.
    Ensures 9 columns: timestamp + 8 float values.
    Timestamps must be strictly increasing and parsable.

    :param table: PyArrow Table to validate.
    :param path: File path (used in error messages).
    :param chunk_index: Index of the chunk being validated.
    :return: List of error messages.
    """
    errors = []
    chunk = table.to_pandas()

    # Validate column count
    if chunk.shape[1] != 9:
        errors.append(f"{path} (chunk {chunk_index}): Expected 9 columns, found {chunk.shape[1]}")
        return errors  # skip row-level validation if structure is wrong

    # Validate timestamp parsing and order
    previous_timestamp = None
    for i, row in chunk.iterrows():
        try:
            timestamp = pd.to_datetime(row.iloc[0])
            if pd.isnull(timestamp):
                raise ValueError("Unparsable timestamp")
        except Exception:
            errors.append(f"{path}, line {i + 2}: Invalid timestamp '{row.iloc[0]}'")
            continue

        if previous_timestamp and timestamp <= previous_timestamp:
            errors.append(f"{path}, line {i + 2}: Timestamps not strictly increasing ({timestamp} <= {previous_timestamp})")
        previous_timestamp = timestamp

        # Validate remaining columns are floats
        for j in range(1, 9):
            value = row.iloc[j]
            if pd.isnull(value):
                errors.append(f"{path}, line {i + 2}, column {j + 1}: Missing value")
            else:
                try:
                    float(value)
                except Exception:
                    errors.append(f"{path}, line {i + 2}, column {j + 1}: Invalid float value '{value}'")

    return errors


def validate_gage_data(gage: dict, forcing_directories: list[str], gage_index: int, total_gages: int, output_file_path: str) -> None:
    """
    Validates forcing data for a single gage across multiple forcing directories.

    Supports both local paths and S3 URLs. Only the first matching directory is validated.
    Errors are written to the provided output file.

    :param gage: Dictionary with 'gage_id' and 'domain'.
    :param forcing_directories: Root paths to look for gage data (local or s3://...).
    :param gage_index: Index of this gage in the validation batch (1-based).
    :param total_gages: Total number of gages in the batch.
    :param output_file_path: Path to write validation error messages.
    """
    start_time = time()
    gage_id = gage['gage_id']
    domain = gage['domain']

    msg = f"Starting validation for gage {gage_id} ({gage_index} of {total_gages})"
    logger.info(msg)
    append_to_validation_output(msg, output_file_path)
    # flush_log_handlers()

    logger.info(f"Checking forcing data for gage {gage_id} ({gage_index} of {total_gages})")
    # flush_log_handlers()

    validated_path = None

    for dir_path in forcing_directories:
        if dir_path.startswith("s3://"):
            full_path = f"{dir_path.rstrip('/')}/{domain}/Gage_{gage_id}"
            logger.info(f"Looking for forcing directory {full_path}")
            if s3_prefix_exists(full_path):
                validated_path = full_path
                break
        else:
            full_path = os.path.join(dir_path, domain, f"Gage_{gage_id}")
            logger.info(f"Looking for forcing directory {full_path}")
            if os.path.isdir(full_path):
                validated_path = full_path
                break

    if validated_path:
        validate_csv_directory(validated_path, output_file_path)
    else:
        msg = f"Gage_{gage_id}: Forcing directory not found"
        logger.warning(msg)
        append_to_validation_output(msg, output_file_path)

    elapsed = time() - start_time
    minutes, seconds = divmod(int(elapsed), 60)
    msg = f"Finished processing gage {gage_id} ({gage_index} of {total_gages}) in {minutes}:{seconds:02d}"
    logger.info(msg)
    append_to_validation_output(msg, output_file_path)
    # flush_log_handlers()


# def flush_log_handlers():
#     """
#     Flush all configured log handlers.
#
#     Ensures that log output is immediately written, especially important
#     in multithreaded or long-running processes.
#     """
#     for handler in logging.getLogger().handlers:
#         if hasattr(handler, 'flush'):
#             handler.flush()


def append_to_validation_output(message: str, output_path: str) -> None:
    """
    Appends a single message to the specified validation output file.

    Each message is written as its own line. Used for logging errors or status updates.

    :param message: Message text to write.
    :param output_path: Path to the output .txt file.
    """
    try:
        with open(output_path, 'a', encoding='utf-8') as f:
            f.write(f"{message}\n")
    except Exception as e:
        logger.warning(f"Could not write to validation output file '{output_path}': {e}")


def get_headwater_gages() -> list[dict]:
    """
    Returns a sorted list of gage dicts that have the 'headwater_calibration' flag set.
    """
    cached_gage_map = get_cached_gages()
    return sorted(
        [gage for gage in cached_gage_map.values() if gage.get('headwater_calibration')],
        key=lambda g: g.get('gage_id')
    )
