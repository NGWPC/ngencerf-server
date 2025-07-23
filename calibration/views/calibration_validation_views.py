import csv
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from time import time
from datetime import timezone

import pandas as pd
from django.conf import settings

from calibration.util.aws_util import convert_s3_uri_to_fs
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
    flush_log_handlers()
    append_to_validation_output(msg, output_txt_path)
    append_to_validation_output(' ', output_txt_path)

    forcing_directories = []
    if forcing_dir:
        if not os.path.exists(forcing_dir) or not os.path.isdir(forcing_dir):
            raise ValueError(f"Invalid forcing_dir: '{forcing_dir}' is not a valid directory")
        forcing_directories.append(forcing_dir)
    else:
        # Use default directories from settings
        for f in settings.FORCING_DATA_DIRS:
            forcing_directories.append(convert_s3_uri_to_fs(f))

    # Validate gage_ids before proceeding
    cached_gage_map = get_cached_gages()
    gage_ids_filter = set(gages) if gages else None

    if gage_ids_filter:
        gage_errors = [gage_id for gage_id in gage_ids_filter if gage_id not in cached_gage_map]
        if gage_errors:
            raise ValueError(f'These gages do not exist: {gage_errors}')

    logger.info(f"Using forcing directories: {forcing_directories}")
    flush_log_handlers()

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
    flush_log_handlers()

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
        max_parallel_gages = 1

        with ThreadPoolExecutor(max_workers=max_parallel_gages) as executor:
            futures = []
            for i, g in enumerate(gage_list, start=1):
                logger.info(f"Queuing gage {g['gage_id']} ({i} of {total})")
                flush_log_handlers()
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
                flush_log_handlers()

        final_msg = f"Finished validating {completed} of {total} gages"
        logger.info(final_msg)
        logger.info(f"Output is in {output_txt_path}")
        flush_log_handlers()
        append_to_validation_output(final_msg, output_txt_path)

    except Exception as e:
        msg = f"validate_files: Unhandled exception during validation: {e}"
        logger.exception("Unhandled exception during validation")
        logger.warning(msg)
        append_to_validation_output(msg, output_txt_path)
        flush_log_handlers()


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


def validate_csv_directory(dir_path: str, output_txt_path: str | None = None) -> None:

    """
    Validates all .csv files in the specified directory using concurrent threads.

    Performs structure checks, column count validation, and per-file type validation.
    Submits files to a thread pool that runs `validate_csv_file()`.

    :param dir_path: Directory containing forcing CSV files.
    :param output_txt_path: Path to the output .txt file.
    """
    if not dir_path or not os.path.isdir(dir_path):
        logger.warning(f"{dir_path}: Provided path is not a directory")
        flush_log_handlers()
        return

    csv_files = sorted([f for f in os.listdir(dir_path) if f.lower().endswith(".csv")])
    total_files = len(csv_files)
    msg = f"Validating forcing directory {dir_path} ({total_files} files)"
    logger.info(msg)
    flush_log_handlers()
    append_to_validation_output(msg, output_txt_path)

    # Don't use too many workers.  Creates S3 bottlenecks.  This will process 4 files at a time
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {}
        for i, f in enumerate(csv_files, start=1):
            path = os.path.join(dir_path, f)
            try:
                future = executor.submit(validate_csv_file, path, file_index=i, total_files=total_files, output_txt_path=output_txt_path)
                futures[future] = path
                logger.info(f"Submitted {path} to executor ({i} of {total_files})")
                flush_log_handlers()
            except Exception as e:
                logger.warning(f"{path}: Exception during executor.submit: {e}")
        flush_log_handlers()

        for i, future in enumerate(as_completed(futures), start=1):
            path = futures[future]
            try:
                future.result()
            except Exception as e:
                logger.warning(f"{path}: Unhandled exception during validation: {e}")
            flush_log_handlers()


def validate_csv_file(path: str, file_index: int, total_files: int, output_txt_path: str) -> None:
    """
    Validates a single forcing CSV file for structure and content errors.

    Checks include:
      - File existence and readability
      - Correct number of columns
      - Valid header
      - Timestamps are correctly formatted and in order
      - Value columns are numeric

    Errors are also written to the provided output_txt_path.

    :param path: Path to the CSV file.
    :param file_index: Index of the file in a batch, for logging.
    :param total_files: Total file count in batch, for logging.
    :param output_txt_path: Path to a .txt file where validation errors should be written.
    """
    start_time = time()

    if not os.path.isfile(path):
        msg = f"{path}: File not found"
        logger.warning(msg)
        flush_log_handlers()
        append_to_validation_output(msg, output_txt_path)
        return

    expected_columns = 9

    file_size_bytes = os.path.getsize(path)
    file_size_mb = file_size_bytes / (1024*1024)  # Convert to MB

    msg = f"Validating forcing file {path} ({file_index} of {total_files}) ({file_size_mb:.2f} MB)"
    logger.info(msg)
    flush_log_handlers()
    append_to_validation_output(msg, output_txt_path)

    rows = []

    # Read and validate structure
    try:
        read_start = time()
        with open(path, newline='') as f:
            reader = csv.reader(f)
            for i, row in enumerate(reader, start=1):
                if len(row) != expected_columns:
                    msg = (
                        f"   {path} [Line {i}]: Row {i} has {len(row)} columns, expected {expected_columns}\n"
                        f"      Line content: {','.join(row)}"
                    )
                    logger.warning(msg)
                    flush_log_handlers()
                    append_to_validation_output(msg, output_txt_path)
                    return
                rows.append(row)

    except Exception as e:
        msg = f"   {path}: Failed to read CSV (structural check): {e}"
        logger.warning(msg)
        flush_log_handlers()
        append_to_validation_output(msg, output_txt_path)
        return

    read_elapsed = time() - read_start
    logger.info(f"   Time to open+read forcing file {path}: {read_elapsed:.2f} sec")

    if len(rows) < 2:
        msg = f"   {path}: File does not contain data rows"
        logger.warning(msg)
        flush_log_handlers()
        append_to_validation_output(msg, output_txt_path)
        return

    if len(rows[0]) != expected_columns:
        msg = (
            f"   {path} [Line 1]: Header has {len(rows[0])} columns, expected {expected_columns}\n"
            f"       Line content: {','.join(rows[0])}"
        )
        logger.warning(msg)
        flush_log_handlers()
        append_to_validation_output(msg, output_txt_path)
        return

    # Now read the file fully with pandas for per-column type checking
    try:
        df = pd.DataFrame(rows[1:], columns=rows[0])  # Assumes header is first row
        df = df.reset_index(drop=True)  # Ensure numeric row indices
    except Exception as e:
        msg = f"   {path}: Failed to parse CSV with pandas: {e}"
        logger.warning(msg)
        flush_log_handlers()
        append_to_validation_output(msg, output_txt_path)
        return

    datetime_col = df.columns[0]
    value_columns = df.columns[1:]
    prev_time = None

    for row_number, (_, row) in enumerate(df.iterrows(), start=2):  # start=2 = header + 1-indexed
        # Validate datetime field
        datetime_str = row.at[datetime_col]
        try:
            current_time = pd.to_datetime(datetime_str)
        except Exception:
            msg = (
                f"   {path} [Line {row_number}]: Invalid datetime value in column '{datetime_col}': '{datetime_str}'\n"
                f"      Line content: {','.join([str(x) for x in row.values])}"
            )
            logger.warning(msg)
            flush_log_handlers()
            append_to_validation_output(msg, output_txt_path)
            continue

        if prev_time is not None and current_time < prev_time:
            msg = (
                f"   {path} [Line {row_number}]: Timestamps out of order: {datetime_str} is earlier than previous row {prev_time}\n"
                f"      Line content: {','.join([str(x) for x in row.values])}"
            )
            logger.warning(msg)
            append_to_validation_output(msg, output_txt_path)
        prev_time = current_time

        # Validate numeric fields
        for col in value_columns:
            try:
                float(row.at[col])
            except (ValueError, TypeError):
                msg = (
                    f"   {path} [Line {row_number}]: Column '{col}' must be numeric (value='{row[col]}')\n"
                    f"      Line content: {','.join([str(x) for x in row.values])}"
                )
                logger.warning(msg)
                append_to_validation_output(msg, output_txt_path)

    elapsed = time() - start_time
    minutes, seconds = divmod(int(elapsed), 60)
    msg = f"   Finished validating forcing file {path} ({file_index} of {total_files}) in {minutes}:{seconds:02d}"
    logger.info(msg)
    append_to_validation_output(msg, output_txt_path)
    flush_log_handlers()  # Final flush after completing the file


def validate_gage_data(gage: dict, forcing_directories: list[str], gage_index: int, total_gages: int, output_file_path: str) -> None:
    """
    Validates forcing data for a single gage across multiple forcing directories.

    Only the first matching directory found is validated. Errors are written to
    the provided output file.

    :param gage: Dictionary with 'gage_id' and 'domain'.
    :param forcing_directories: Root paths to look for gage data.
    :param gage_index: Index of this gage in the validation batch (1-based).
    :param total_gages: Total number of gages in the batch.
    :param output_file_path: Path to write validation error messages.
    """
    start_time = time()
    gage_id = gage['gage_id']
    domain = gage['domain']

    logger.info(f"Starting validation for gage {gage_id} ({gage_index} of {total_gages})")
    flush_log_handlers()

    logger.info(f"Checking forcing data for gage {gage_id} ({gage_index} of {total_gages})")
    flush_log_handlers()
    for dir_path in forcing_directories:
        forcing_dir = os.path.join(dir_path, domain, f"Gage_{gage_id}")
        logger.info(f'Looking for forcing directory {forcing_dir}')
        if os.path.isdir(forcing_dir):
            validate_csv_directory(forcing_dir, output_file_path)
            break
    else:
        msg = f"Gage_{gage_id}: Forcing directory not found"
        logger.warning(msg)
        append_to_validation_output(msg, output_file_path)

    elapsed = time() - start_time
    minutes, seconds = divmod(int(elapsed), 60)
    logger.info(f"Finished processing gage {gage_id} ({gage_index} of {total_gages}) in {minutes}:{seconds:02d}")
    flush_log_handlers()


def flush_log_handlers():
    """
    Flush all configured log handlers.

    Ensures that log output is immediately written, especially important
    in multithreaded or long-running processes.
    """
    for handler in logging.getLogger().handlers:
        if hasattr(handler, 'flush'):
            handler.flush()


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
