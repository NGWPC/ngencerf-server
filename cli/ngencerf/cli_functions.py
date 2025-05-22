"""
Module providing CLI functionality for interacting with ngen calibration job endpoints.
Supports operations like uploading data, submitting/deleting/cancelling jobs, and
importing/exporting configurations.
"""

import json
import os
from contextlib import ExitStack
from datetime import datetime

import requests
import tabulate

from ngencerf.cli_util import check_http_error

API_BASE = "http://localhost:8000"

# Default download directory (fallbacks to cwd if ~/Downloads is missing)
DEFAULT_DOWNLOAD_DIR = os.path.expanduser("~/Downloads")
if not os.path.isdir(DEFAULT_DOWNLOAD_DIR):
    DEFAULT_DOWNLOAD_DIR = os.getcwd()


def get_auth_headers() -> dict[str, str]:
    """
    Returns authentication headers using the ACCESS_TOKEN environment variable.

    :returns: Dictionary containing the Authorization header.
    """
    return {
        "Authorization": f"Bearer {os.environ.get('ACCESS_TOKEN', '')}",
    }


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
        response = requests.post(
            f"{API_BASE}/calibration/upload_geopackage_data/",
            headers=get_auth_headers(),
            files=files,
            data=data,
        )
        response_json, success = check_http_error(response.status_code, response.text)
        if not success:
            return 1
        if response_json and (message := response_json.get("message")):
            print(message)
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
        response = requests.post(
            f"{API_BASE}/calibration/upload_observational_data/",
            headers=get_auth_headers(),
            files=files,
            data=data,
        )
        response_json, success = check_http_error(response.status_code, response.text)
        if not success:
            return 1
        if response_json and (message := response_json.get("message")):
            print(message)
        return 0


def upload_forcing_data(forcing_dir: str, calibration_run_id: int) -> int:
    """
    Uploads all files in a directory as forcing data for a given calibration run.

    :param forcing_dir: Path to directory containing forcing files.
    :param calibration_run_id: ID of the calibration run.
    :returns: 0 on success, 1 on failure.
    """
    print(f"Uploading forcing data from directory: '{forcing_dir}' for calibration_run_id: {calibration_run_id}")

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

        # Send the request
        response = requests.post(
            f"{API_BASE}/calibration/upload_forcing_data/",
            headers=get_auth_headers(),
            files=files,
            data={"calibration_run_id": calibration_run_id},
        )
        # Check for errors
        response_json, success = check_http_error(response.status_code, response.text)
        if not success:
            return 1
        if response_json and (message := response_json.get("message")):
            print(message)
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

    response = requests.post(
        f"{API_BASE}/calibration/get_calibration_job_zip/",
        headers=get_auth_headers(),
        json=payload,
        stream=True,
    )

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
    response = requests.post(
        f"{API_BASE}/calibration/run_calibration/",
        headers={**get_auth_headers(), "Content-Type": "application/json"},
        json=payload,
    )
    response_json, success = check_http_error(response.status_code, response.text)
    if not success:
        return 1
    if response_json and (message := response_json.get("message")):
        print(message)
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
    response = requests.post(
        f"{API_BASE}/calibration/delete_jobs/",
        headers={**get_auth_headers(), "Content-Type": "application/json"},
        json=payload,
    )
    response_json, success = check_http_error(response.status_code, response.text)
    if not success:
        return 1
    if response_json:
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
    response = requests.post(
        f"{API_BASE}/calibration/archive_jobs/",
        headers={**get_auth_headers(), "Content-Type": "application/json"},
        json=payload,
    )
    response_json, success = check_http_error(response.status_code, response.text)
    if not success:
        return 1
    if response_json:
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
    response = requests.post(
        f"{API_BASE}/calibration/archive_jobs/",
        headers={**get_auth_headers(), "Content-Type": "application/json"},
        json=payload,
    )
    response_json, success = check_http_error(response.status_code, response.text)
    if not success:
        return 1
    if response_json:
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
    response = requests.post(
        f"{API_BASE}/calibration/cancel_job/",
        headers={**get_auth_headers(), "Content-Type": "application/json"},
        json=payload,
    )
    response_json, success = check_http_error(response.status_code, response.text)
    if not success:
        return 1
    if response_json and (message := response_json.get("message")):
        print(message)
    return 0


def list_jobs(output_path: str | None = None) -> int:
    """
    Lists all calibration jobs and saves them to a markdown file.

    :param output_path: Path to save the job list (optional)
    :return: 0 on success, 1 on failure
    """
    print("Fetching calibration jobs...")
    response = requests.post(
        f"{API_BASE}/calibration/get_calibration_jobs/",
        headers={**get_auth_headers(), "Content-Type": "application/json"},
    )

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

    path = resolve_output_path(output_path, f"calibration_jobs_{datetime.now().strftime('%Y-%m-%d_%H%M')}.md")

    with open(path, "w", encoding="utf-8") as f:
        f.write(markdown_table)

    print(f"Saved {len(rows)} jobs to {path}")
    return 0


def _submit_job_data(job_file: str, calibration_run_id: int | None = None, run_after_import: bool | None = None) -> int:
    """
    Submits job data to the import or update endpoint.

    :param job_file: Path to the JSON file
    :param calibration_run_id: Optional calibration_run_id for update
    :param run_after_import: Optional override for the run_after_import field
    :return: 0 on success, 1 on failure
    """
    print(f"Loading job data from: {job_file}")

    # Load the JSON file
    with open(job_file, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    # Override the run_after_import field if specified
    if run_after_import is not None:
        print(f"Overriding run_after_import: {run_after_import}")
        job_data["run_after_import"] = run_after_import

    # Build the payload
    payload = {"data": job_data}
    if calibration_run_id is not None:
        payload["calibration_run_id"] = calibration_run_id

    # Send the modified job data to the server
    response = requests.post(
        f"{API_BASE}/calibration/import/",
        headers={**get_auth_headers(), "Content-Type": "application/json"},
        json=payload,
    )

    response_json, success = check_http_error(response.status_code, response.text)
    if not success:
        return 1
    if response_json and (message := response_json.get("message")):
        print(message)
    return 0


def import_job(job_file: str, run_after_import: bool | None = None) -> int:
    """
    Imports a new job definition from a JSON file.

    :param job_file: Path to the JSON file
    :param run_after_import: Optional override for the run_after_import field
    :return: 0 on success, 1 on failure
    """
    print(f"Importing job from: {job_file}")
    return _submit_job_data(job_file, run_after_import=run_after_import)


def update_job(calibration_run_id: int, job_file: str, run_after_import: bool | None = None) -> int:
    """
    Updates an existing calibration job using a JSON file.

    :param calibration_run_id: ID of the calibration run
    :param job_file: Path to the JSON file
    :param run_after_import: Optional override for the run_after_import field
    :return: 0 on success, 1 on failure
    """
    print(f"Updating job {calibration_run_id} from: {job_file}")
    return _submit_job_data(job_file, calibration_run_id=calibration_run_id, run_after_import=run_after_import)


def handle_export_display(calibration_run_id: int, output_path: str | None = None, display: bool = False) -> int:
    """
    Exports a calibration job to a file or displays it.

    :param calibration_run_id: ID of the calibration run to export
    :param output_path: Path to save the export file (default: ~/Downloads)
    :param display: Whether to print the job to the console
    :return: 0 on success, 1 on failure
    """
    payload = {"calibration_run_id": calibration_run_id}

    print(f"Sending request to {API_BASE}/calibration/export/")
    response = requests.post(
        f"{API_BASE}/calibration/export/",
        headers={**get_auth_headers(), "Content-Type": "application/json"},
        json=payload,
    )

    response_json, success = check_http_error(response.status_code, response.text)
    if not success:
        return 1
    if not response_json:
        return 0

    if display:
        _pretty_print_job(calibration_run_id, response_json)

    # If --output was used (including the default case), resolve the output path
    if output_path is not None:
        path = resolve_output_path(output_path, f"export_{calibration_run_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(response_json, f, indent=2)

        print(f"Exported to {path}")
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
    print(f"Setup - Calibration Job ID {metadata.get('source_calibration_run_id', calibration_run_id)}")
    print(f"Job Data directory: {metadata.get('job_data_dir')}")
    print(f"Gage: {data.get('gage_id')}")
    print(f"Catchments: {metadata.get('num_catchments', '-')}")
    print(f"Forcing Data: {data.get('forcing_source')}")
    print(f"Observational Data: {data.get('observational_source')}")
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
    # Use the default directory if no output path is specified
    if output_path == "__DEFAULT__" or not output_path:
        output_path = DEFAULT_DOWNLOAD_DIR

    output_path = os.path.expanduser(os.path.expandvars(output_path))

    # Use the default directory if the path is just a filename
    if not os.path.isabs(output_path) and not os.path.dirname(output_path):
        output_path = os.path.join(DEFAULT_DOWNLOAD_DIR, output_path)

    # If the path is a directory, use the default filename
    if output_path.endswith(os.sep) or os.path.isdir(output_path):
        os.makedirs(output_path, exist_ok=True)
        return os.path.join(output_path, default_filename)

    # Ensure the directory exists for full or relative paths
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    return output_path
