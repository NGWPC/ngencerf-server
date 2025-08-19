"""
Module providing CLI functionality for interacting with ngen calibration job endpoints.
Supports operations like uploading data, submitting/deleting/cancelling jobs, and
importing/exporting configurations.
"""
import itertools
import json
import os
import sys
import threading
import time
from contextlib import ExitStack
from datetime import datetime

import requests
import tabulate

from ngencerf.cli_util import check_http_error

API_BASE = "http://localhost:8000"


def get_auth_headers() -> dict[str, str]:
    """
    Returns authentication headers using the ACCESS_TOKEN environment variable.

    :returns: Dictionary containing the Authorization header.
    """
    return {
        "Authorization": f"Bearer {os.environ.get('ACCESS_TOKEN', '')}",
    }


def post_with_spinner(message: str, post_func: callable) -> requests.Response | None:
    """
    Displays a spinner while executing a POST request callable.
    Gracefully handles KeyboardInterrupt (Ctrl-C) to avoid ugly tracebacks.

    :param message: Message to display while waiting.
    :param post_func: A callable that returns a requests.Response when invoked.
    :return: The requests.Response object from the callable, or None if interrupted.
    """
    spinner = Spinner(message)
    spinner.start()
    try:
        return post_func()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        return None
    finally:
        spinner.stop()


def about(output_path: str | None = None) -> int:
    """
    Fetch and display git information from the calibration server in a formatted manner.

    Returns:
        int: Exit code (0 for success, 1 for failure).
    """
    response = post_with_spinner("Sending to server", lambda: requests.post(
        f"{API_BASE}/calibration/get_git_info/",
        headers=get_auth_headers()
    ))

    if response is None:
        return 1  # Interrupted by user

    response_json, success = check_http_error(response.status_code, response.text)
    if not success:
        return 1

    final_path = resolve_output_path(output_path, "about_ngencerf.json")
    if response_json and (git_info := response_json.get("git_info")):
        with open(final_path, "w", encoding="utf-8") as f:
            json.dump(git_info, f, indent=2)

    print(f"ngenCerf 'about' info saved to {final_path}")
    return 0


def upload_geopackage_data(geopackage_file: str, calibration_run_id: int) -> int:
    """
    Uploads a geopackage file for a given calibration run.

    :param geopackage_file: Path to the .gpkg file.
    :param calibration_run_id: ID of the calibration run.
    :returns: 0 on success, 1 on failure.
    """
    print(f"Uploading geopackage: {geopackage_file} for calibration_run_id: {calibration_run_id}")

    with open(geopackage_file, "rb") as f:
        files = {"geopackage_file": f}
        data = {
            "calibration_run_id": calibration_run_id,
            "return_geopackage_url": "false",
        }
        response = post_with_spinner("Uploading geopackage...", lambda: requests.post(
            f"{API_BASE}/calibration/upload_geopackage_data/",
            headers=get_auth_headers(),
            files=files,
            data=data
        ))

        if response is None:
            return 1  # Interrupted by user

        response_json, success = check_http_error(response.status_code, response.text)
        if not success:
            return 1
        if message := response_json.get("message"):
            print(message)
        if warnings := response_json.get("warnings"):
            print("Warnings:")
            for w in warnings:
                print(f"   {w}")
        return 0


def upload_observational_data(observational_file: str, calibration_run_id: int) -> int:
    """
    Uploads observational data (CSV) for a given calibration run.

    :param observational_file: Path to observational CSV.
    :param calibration_run_id: ID of the calibration run.
    :returns: 0 on success, 1 on failure.
    """
    print(f"Uploading observational data: {observational_file} for calibration_run_id: {calibration_run_id}")
    with open(observational_file, "rb") as f:
        files = {"observational_file": f}
        data = {"calibration_run_id": calibration_run_id}

        response = post_with_spinner("Uploading observational data...", lambda: requests.post(
            f"{API_BASE}/calibration/upload_observational_data/",
            headers=get_auth_headers(),
            files=files,
            data=data
        ))

        if response is None:
            return 1  # Interrupted by user

        response_json, success = check_http_error(response.status_code, response.text)
        if not success:
            return 1
        if message := response_json.get("message"):
            print(message)
        if warnings := response_json.get("warnings"):
            print("Warnings:")
            for w in warnings:
                print(f"   {w}")
        return 0


def upload_forcing_data(forcing_dir: str, calibration_run_id: int) -> int:
    """
    Uploads all files in a directory as forcing data for a given calibration run.

    :param forcing_dir: Path to directory containing forcing files.
    :param calibration_run_id: ID of the calibration run.
    :returns: 0 on success, 1 on failure.
    """
    print(f"Uploading forcing data from directory: '{forcing_dir}' for calibration_run_id: {calibration_run_id}")

    # noinspection PyAbstractClass
    with ExitStack() as stack:
        # Collect files from directory
        files = [
            ('files', (fname, stack.enter_context(open(os.path.join(forcing_dir, fname), 'rb'))))
            for fname in sorted(os.listdir(forcing_dir))
            if os.path.isfile(os.path.join(forcing_dir, fname))
        ]

        if not files:
            print("No forcing data files found to upload.")
            return 1

        response = post_with_spinner("Uploading forcing data...", lambda: requests.post(
            f"{API_BASE}/calibration/upload_forcing_data/",
            headers=get_auth_headers(),
            files=files,
            data={"calibration_run_id": calibration_run_id}
        ))

        if response is None:
            return 1  # Interrupted by user

        # Check for errors
        response_json, success = check_http_error(response.status_code, response.text)
        if not success:
            return 1
        if message := response_json.get("message"):
            print(message)
        if warnings := response_json.get("warnings"):
            print("Warnings:")
            for w in warnings:
                print(f"   {w}")
        return 0


def download_zip(calibration_run_id: int, output_path: str | None = None) -> int:
    """
    Downloads the ZIP archive for a calibration run from the server.

    :param calibration_run_id: ID of the calibration run to download.
    :param output_path: Path to save the ZIP file or directory (default: ~/Downloads).
    :returns: 0 on success, 1 on failure.
    """
    print(f"Downloading ZIP for calibration run: {calibration_run_id}")

    payload = {"calibration_run_id": calibration_run_id}

    response = post_with_spinner("Downloading zip...", lambda: requests.post(
        f"{API_BASE}/calibration/get_calibration_job_zip/",
        headers=get_auth_headers(),
        json=payload,
        stream=True
    ))

    if response is None:
        return 1  # Interrupted by user

    response_json, success = check_http_error(response.status_code, response.text)
    if not success:
        return 1

    # Determine filename from Content-Disposition header or use default
    content_disp = response.headers.get("Content-Disposition", "")
    default_filename = f"calibration_job_{calibration_run_id}.zip"
    if "filename=" in content_disp:
        default_filename = content_disp.split("filename=")[-1].strip('"')

    final_path = resolve_output_path(output_path, default_filename)

    # Save response content to file
    with open(final_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    print(f"Downloaded ZIP to: {final_path}")
    return 0


def run_job(calibration_run_id: int) -> int:
    """
    Submits a calibration run for execution.

    :param calibration_run_id: ID of the calibration run.
    :returns: 0 on success, 1 on failure.
    """
    print(f"Submitting calibration run job {calibration_run_id}")
    payload = {"calibration_run_id": calibration_run_id}

    response = post_with_spinner("Submitting job", lambda: requests.post(
        f"{API_BASE}/calibration/run_calibration/",
        headers={**get_auth_headers(), "Content-Type": "application/json"},
        json=payload,
    ))

    if response is None:
        return 1  # Interrupted by user

    response_json, success = check_http_error(response.status_code, response.text)
    if not success:
        return 1
    if message := response_json.get("message"):
        print(message)
    if warnings := response_json.get("warnings"):
        print("Warnings:")
        for w in warnings:
            print(f"   {w}")
    return 0


def delete_job(calibration_run_ids: list[int]) -> int:
    """
    Deletes one or more calibration runs, with confirmation.

    :param calibration_run_ids: A list of one or more calibration run IDs.
    :returns: 0 on success, 1 on failure.
    """
    if len(calibration_run_ids) == 1:
        # Display job details before deletion
        print("\nFetching job details for confirmation...\n")

        # Display the job details
        handle_export_display(calibration_run_ids[0], display=True)

    try:
        # Confirm deletion
        confirmation = input(f"\nType 'delete' to confirm the permanent deletion of calibration jobs {calibration_run_ids}: ").strip()
        if confirmation.lower() != "delete":
            print("\nDeletion aborted. The calibration jobs were not deleted.")
            return 1
    except KeyboardInterrupt:
        print("\n\nDeletion aborted. The calibration jobs were not deleted.")
        return 1

    # Proceed with deletion
    print(f"\nDeleting calibration run jobs {calibration_run_ids}")
    payload = {"calibration_run_ids": calibration_run_ids}

    response = post_with_spinner("Deleting jobs", lambda: requests.post(
        f"{API_BASE}/calibration/delete_jobs/",
        headers={**get_auth_headers(), "Content-Type": "application/json"},
        json=payload,
    ))

    if response is None:
        return 1  # Interrupted by user

    response_json, success = check_http_error(response.status_code, response.text)
    if not success:
        return 1

    for job in response_json.get("jobs", []):
        print(job.get("message", f"Job {job['calibration_run_id']} processed."))
    return 0


def archive_job(calibration_run_ids: list[int]) -> int:
    """
    Archives one or more calibration runs.

    :param calibration_run_ids: A list of one or more calibration run IDs.
    :returns: 0 on success, 1 on failure.
    """
    print(f"Archiving calibration run jobs {calibration_run_ids}")
    payload = {"calibration_run_ids": calibration_run_ids, "archive": True}

    response = post_with_spinner("Archiving jobs...", lambda: requests.post(
        f"{API_BASE}/calibration/archive_jobs/",
        headers={**get_auth_headers(), "Content-Type": "application/json"},
        json=payload,
    ))

    if response is None:
        return 1  # Interrupted by user

    response_json, success = check_http_error(response.status_code, response.text)
    if not success:
        return 1

    for job in response_json.get("jobs", []):
        print(job.get("message", f"Job {job['calibration_run_id']} processed."))
    return 0


def unarchive_job(calibration_run_ids: list[int]) -> int:
    """
    Unarchives one or more calibration runs.

    :param calibration_run_ids: A list of one or more calibration run IDs.
    :returns: 0 on success, 1 on failure.
    """
    print(f"Unarchiving calibration run jobs {calibration_run_ids}")
    payload = {"calibration_run_ids": calibration_run_ids, "archive": False}

    response = post_with_spinner("Unarchiving jobs...", lambda: requests.post(
        f"{API_BASE}/calibration/archive_jobs/",
        headers={**get_auth_headers(), "Content-Type": "application/json"},
        json=payload,
    ))

    if response is None:
        return 1  # Interrupted by user

    response_json, success = check_http_error(response.status_code, response.text)
    if not success:
        return 1

    for job in response_json.get("jobs", []):
        print(job.get("message", f"Job {job['calibration_run_id']} processed."))
    return 0


def cancel_job(calibration_run_id: int) -> int:
    """
    Cancels a running calibration job.

    :param calibration_run_id: ID of the calibration run
    :return: 0 on success, 1 on failure
    """
    print(f"Cancelling calibration run job {calibration_run_id}")
    payload = {"calibration_run_id": calibration_run_id}

    response = post_with_spinner("Cancelling job...", lambda: requests.post(
        f"{API_BASE}/calibration/cancel_job/",
        headers={**get_auth_headers(), "Content-Type": "application/json"},
        json=payload,
    ))

    if response is None:
        return 1  # Interrupted by user

    response_json, success = check_http_error(response.status_code, response.text)
    if not success:
        return 1
    if message := response_json.get("message"):
        print(message)
    if warnings := response_json.get("warnings"):
        print("Warnings:")
        for w in warnings:
            print(f"   {w}")
    return 0


def list_jobs(output_path: str | None = None) -> int:
    """
    Lists all calibration jobs and saves them to a markdown file.

    :param output_path: Path to save the job list (optional)
    :return: 0 on success, 1 on failure
    """
    response = post_with_spinner("Fetching job list...", lambda: requests.post(
        f"{API_BASE}/calibration/get_jobs/",
        headers={**get_auth_headers(), "Content-Type": "application/json"},
    ))

    if response is None:
        return 1  # Interrupted by user

    response_json, success = check_http_error(response.status_code, response.text)
    if not success:
        return 1
    if not response_json:
        return 0

    jobs = response_json.get("jobs", [])
    if not jobs:
        print("No jobs found.")
        return 0

    rows = []
    for job in jobs:
        rows.append([
            job.get("calibration_run_id"),
            job.get("gage_id") or "-",
            job.get("status") or "-",
            (job.get("calibration_start_period") or "-").replace("T", " ").split(".")[0],
            (job.get("calibration_end_period") or "-").replace("T", " ").split(".")[0],
            job.get("formulation_name") or "-",
            job.get("objective_function") or "-",
            job.get("optimization_algorithm") or "-",
            (job.get("created_at") or "-").replace("T", " ").split(".")[0],
            ", ".join(job.get("modules", []))
        ])

    headers = [
        "Run ID", "Gage", "Status", "Start", "End",
        "Formulation", "Objective", "Optimization", "Created", "Modules"
    ]

    markdown_table = tabulate.tabulate(rows, headers=headers, tablefmt="github")

    final_path = resolve_output_path(output_path, f"calibration_jobs_{datetime.now().strftime('%Y-%m-%d_%H%M')}.md")

    with open(final_path, "w", encoding="utf-8") as f:
        f.write(markdown_table)

    print(f"Saved {len(rows)} jobs to {final_path}")
    return 0


def _submit_job_data(job_file: str, action: str, calibration_run_id: int | None = None, run_after_import: bool | None = None) -> int:
    """
    Submits job data to the import or update endpoint.

    :param job_file: Path to the JSON file
    :param calibration_run_id: Optional calibration_run_id for update
    :param run_after_import: Optional override for the run_after_import field
    :return: 0 on success, 1 on failure
    """
    # Load the JSON file
    try:
        with open(job_file, "r", encoding="utf-8") as f:
            job_data = json.load(f)
    except FileNotFoundError:
        print(f"{job_file} does not exist")
        return 1
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON file {job_file}: {e}")
        return 1

    # Override the run_after_import field if specified
    if run_after_import is not None:
        print(f"Overriding run_after_import: {run_after_import}")
        job_data["run_after_import"] = run_after_import

    # Build the payload
    payload = {"data": job_data}
    if calibration_run_id is not None:
        payload["calibration_run_id"] = calibration_run_id

    response = post_with_spinner(f"{action} job", lambda: requests.post(
        f"{API_BASE}/calibration/import/",
        headers={**get_auth_headers(), "Content-Type": "application/json"},
        json=payload
    ))

    if response is None:
        return 1  # Interrupted by user

    response_json, success = check_http_error(response.status_code, response.text)
    if not success:
        return 1

    # Print top-level message
    if message := response_json.get("message"):
        print(message)

    # Collect errors into one list
    combined_errors = []
    combined_warnings = []

    # Nested messages block
    if messages := response_json.get("messages"):
        if errors := messages.get("errors"):
            combined_errors.extend(errors)

        if eds_errors := messages.get("eds_errors"):
            combined_errors.extend(e.get("message", str(e)) for e in eds_errors)

        if warnings := messages.get("warnings"):
            combined_warnings.extend(warnings)

    # Top-level blocks
    if errors := response_json.get("errors"):
        combined_errors.extend(errors)
    if warnings := response_json.get("warnings"):
        combined_warnings.extend(warnings)

    # Print all collected errors and warnings
    if combined_errors:
        print("Errors:")
        for e in combined_errors:
            print('  ', e)

    if combined_warnings:
        print("Warnings:")
        for w in combined_warnings:
            print('  ', w)

    return 0


def import_job(job_file: str, run_after_import: bool | None = None) -> int:
    """
    Imports a new job definition from a JSON file.

    :param job_file: Path to the JSON file
    :param run_after_import: Optional override for the run_after_import field
    :return: 0 on success, 1 on failure
    """
    print(f"Importing job from: {job_file}")
    return _submit_job_data(job_file, action='Importing', run_after_import=run_after_import)


def update_job(calibration_run_id: int, job_file: str, run_after_update: bool | None = None) -> int:
    """
    Updates an existing calibration job using a JSON file.

    :param calibration_run_id: ID of the calibration run
    :param job_file: Path to the JSON file
    :param run_after_update: Optional override for the run_after_import field
    :return: 0 on success, 1 on failure
    """
    print(f"Updating job {calibration_run_id} from: {job_file}")
    return _submit_job_data(job_file, action='Updating', calibration_run_id=calibration_run_id, run_after_import=run_after_update)


def handle_export_display(calibration_run_id: int, output_path: str | None = None, display: bool = False) -> int:
    """
    Exports a calibration job to a file or displays it.

    :param calibration_run_id: ID of the calibration run to export
    :param output_path: Path to save the export file (default: ~/Downloads)
    :param display: Whether to print the job to the console
    :return: 0 on success, 1 on failure
    """
    payload = {"calibration_run_id": calibration_run_id}

    response = post_with_spinner("Fetching job...", lambda: requests.post(
        f"{API_BASE}/calibration/export/",
        headers={**get_auth_headers(), "Content-Type": "application/json"},
        json=payload,
    ))

    if response is None:
        return 1  # Interrupted by user

    response_json, success = check_http_error(response.status_code, response.text)
    if not success:
        return 1
    if not response_json:
        return 0

    if display:
        _pretty_print_job(calibration_run_id, response_json)

    final_path = resolve_output_path(output_path, f"export_{calibration_run_id}.json")
    with open(final_path, "w", encoding="utf-8") as f:
        json.dump(response_json, f, indent=2)

    print(f"Job {calibration_run_id} exported to {final_path}")
    return 0


def _pretty_print_job(calibration_run_id: int, data: dict) -> None:
    """
    Prints selected fields from the exported calibration job in a structured format.

    :param calibration_run_id: ID of the calibration run
    :param data: Exported job data
    """

    def fmt(dt: str | None) -> str:
        """
        Formats an ISO timestamp string in GMT (UTC) to 'YYYY-MM-DD HH:MM'.
        Handles optional 'Z' or '+00:00' suffixes.

        :param dt: ISO timestamp string
        :return: Formatted timestamp
        """
        if not dt:
            return "-"
        dt = dt.replace("Z", "").split("+")[0]  # strip 'Z' or '+00:00'
        try:
            return datetime.fromisoformat(dt).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return dt  # fallback: return original if parsing fails

    cal_times = data.get("calibration_times", {})
    val_times = data.get("validation_times", {})
    metadata = data.get("metadata", {})

    print()
    print(f"Calibration Job ID {metadata.get('source_calibration_run_id', calibration_run_id)}")
    print(f"Status: {metadata.get('source_status')}")
    print(f"Job Data directory: {metadata.get('job_data_dir')}")
    print(f"Gage: {data.get('gage_id')}")
    print(f"Catchments: {metadata.get('num_catchments', '-')}")
    print(f"Forcing Source: {data.get('forcing_source')}")
    print(f"Observational Source: {data.get('observational_source')}")
    print(f"Geopackage Source: {data.get('geopackage_source')}")
    print(data.get("description", "").strip())
    print()

    print(f"Formulation Name: {data.get('formulation_name')}")
    print(f"Modules: {', '.join(data.get('modules', []))}")
    print()

    print(f"{'Calibration Run':<50}{'Validation Run'}")
    print(f"{'Sim Start:':<25}{fmt(cal_times.get('simulation_start_time')):<25}Sim Start: {fmt(val_times.get('simulation_start_time'))}")
    print(f"{'Sim End:':<25}{fmt(cal_times.get('simulation_end_time')):<25}Sim End:   {fmt(val_times.get('simulation_end_time'))}")
    print(f"{'Calib Start:':<25}{fmt(cal_times.get('calibration_start_time')):<25}Val Start: {fmt(val_times.get('validation_start_time'))}")
    print(f"{'Calib End:':<25}{fmt(cal_times.get('calibration_end_time')):<25}Val End:   {fmt(val_times.get('validation_end_time'))}")
    print()

    print(f"Optimization Algorithm: {data.get('optimization')}")
    print(f"Objective Function: {data.get('objective_function')}")
    print(f"Plot Generation Frequency: {data.get('save_plot_iteration_frequency')}")
    print()

    print(f"Tuning Parameters: {len(data.get('parameters', []))}")
    print(f"Calibration Stop Criteria: {data.get('stop_criteria')}")
    print()


def resolve_output_path(output_path: str | None, default_filename: str) -> str:
    """
    Resolves the final output path for a file, handling directory, relative, and full file paths.

    :param output_path: The provided output path, which can be a directory, relative file name, or full file path.
    :param default_filename: The default filename to use if output_path is a directory or filename without a path.
    :return: The resolved full file path.
    """
    # Determine the base directory
    if output_path is None or output_path == "__DEFAULT__":
        base_dir = os.getcwd()
        output_path = os.path.join(base_dir, default_filename)
    else:
        # Expand user and environment variables
        output_path = os.path.expanduser(os.path.expandvars(output_path))

        # If output_path is a directory, append the default filename
        if os.path.isdir(output_path) or output_path.endswith(os.sep):
            os.makedirs(output_path, exist_ok=True)
            output_path = os.path.join(output_path, default_filename)
        else:
            # If output_path is just a filename, prepend current working directory
            dir_name = os.path.dirname(output_path)
            if not dir_name:
                output_path = os.path.join(os.getcwd(), output_path)
            else:
                # Ensure the directory exists for the specified file path
                os.makedirs(dir_name, exist_ok=True)

    return output_path


class Spinner:
    def __init__(self, message="Processing..."):
        self.spinner = itertools.cycle(["|", "/", "-", "\\"])
        self.running = False
        self.thread = None
        self.message = message

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._spin)
        self.thread.start()

    def _spin(self):
        print(self.message, end=" ", flush=True)
        while self.running:
            sys.stdout.write(next(self.spinner))
            sys.stdout.flush()
            time.sleep(0.1)
            sys.stdout.write("\b")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
        sys.stdout.write(" \n")
        sys.stdout.flush()
