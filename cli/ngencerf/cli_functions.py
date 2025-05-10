"""
Module providing CLI functionality for interacting with ngen calibration job endpoints.
Supports operations like uploading data, submitting/deleting/cancelling jobs, and
importing/exporting configurations.
"""

import json
import os
from datetime import datetime

import requests
import tabulate

from ngencerf.cli_util import check_http_error

API_BASE = "http://localhost:8000"


def get_auth_headers() -> dict:
    """
    Returns authentication headers using the ACCESS_TOKEN environment variable.
    """
    return {
        "Authorization": f"Bearer {os.environ.get('ACCESS_TOKEN', '')}",
    }


def upload_geopackage_data(geopackage_file: str, calibration_run_id: str):
    """
    Uploads a geopackage file for a given calibration run.

    :param geopackage_file: Path to the .gpkg file
    :param calibration_run_id: ID of the calibration run
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
        check_http_error(response.status_code, response.text, exit_on_error=True)


def upload_observational_data(observational_file: str, calibration_run_id: str):
    """
    Uploads observational data (CSV) for a given calibration run.

    :param observational_file: Path to observational CSV
    :param calibration_run_id: ID of the calibration run
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
        check_http_error(response.status_code, response.text, exit_on_error=True)


def upload_forcing_data(forcing_dir: str, calibration_run_id: str):
    """
    Uploads all files in a directory as forcing data for a given calibration run.

    :param forcing_dir: Path to directory containing forcing files
    :param calibration_run_id: ID of the calibration run
    """
    print(f"Uploading forcing data from directory: '{forcing_dir}' for calibration_run_id: {calibration_run_id}")
    files = []

    # Collect files from directory
    for fname in sorted(os.listdir(forcing_dir)):
        fpath = os.path.join(forcing_dir, fname)
        if os.path.isfile(fpath):
            files.append(('files', (fname, open(fpath, 'rb'))))

    if not files:
        raise RuntimeError("No forcing data files found to upload.")

    try:
        response = requests.post(
            f"{API_BASE}/calibration/upload_forcing_data/",
            headers=get_auth_headers(),
            files=files,
            data={"calibration_run_id": calibration_run_id},
        )
        check_http_error(response.status_code, response.text, exit_on_error=True)
    finally:
        for _, (_, f) in files:
            f.close()


def download_zip(calibration_run_id: str, output_path: str = None):
    """
    Downloads the ZIP archive for a calibration run from the server.

    :param calibration_run_id: ID of the calibration run to download
    :param output_path: Optional path to save the ZIP file or directory to save it in
    """
    print(f"Downloading ZIP for calibration run: {calibration_run_id}")

    payload = {"calibration_run_id": calibration_run_id}

    response = requests.post(
        f"{API_BASE}/calibration/get_calibration_job_zip/",
        headers=get_auth_headers(),
        json=payload,
        stream=True,
    )

    if not check_http_error(response.status_code, response.text, exit_on_error=True):
        return

    # Determine filename from Content-Disposition header or use default
    content_disp = response.headers.get("Content-Disposition", "")
    filename = f"calibration_job_{calibration_run_id}.zip"
    if "filename=" in content_disp:
        filename = content_disp.split("filename=")[-1].strip('"')

    # Resolve final path
    if output_path:
        output_path = os.path.expanduser(os.path.expandvars(output_path))
        if output_path.endswith(os.sep) or os.path.isdir(output_path):
            os.makedirs(output_path, exist_ok=True)
            full_path = os.path.join(output_path, filename)
        else:
            full_path = output_path
    else:
        full_path = filename

    # Save response content to file
    with open(full_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    print(f"Downloaded ZIP to: {full_path}")


def run_job(calibration_run_id: str):
    """
    Submits a calibration run for execution.

    :param calibration_run_id: ID of the calibration run
    """
    print(f"Submitting calibration run job {calibration_run_id}")
    payload = {"calibration_run_id": calibration_run_id}
    response = requests.post(
        f"{API_BASE}/calibration/run_calibration/",
        headers={**get_auth_headers(), "Content-Type": "application/json"},
        json=payload,
    )
    check_http_error(response.status_code, response.text, exit_on_error=True)


def delete_job(calibration_run_id: str):
    """
    Deletes an existing calibration run.

    :param calibration_run_id: ID of the calibration run
    """
    print(f"Deleting calibration run job {calibration_run_id}")
    payload = {"calibration_run_id": calibration_run_id}
    response = requests.post(
        f"{API_BASE}/calibration/delete_job/",
        headers={**get_auth_headers(), "Content-Type": "application/json"},
        json=payload,
    )
    check_http_error(response.status_code, response.text, exit_on_error=True)


def cancel_job(calibration_run_id: str):
    """
    Cancels a running calibration job.

    :param calibration_run_id: ID of the calibration run
    """
    print(f"Cancelling calibration run job {calibration_run_id}")
    payload = {"calibration_run_id": calibration_run_id}
    response = requests.post(
        f"{API_BASE}/calibration/cancel_job/",
        headers={**get_auth_headers(), "Content-Type": "application/json"},
        json=payload,
    )
    check_http_error(response.status_code, response.text, exit_on_error=True)


def list_jobs():
    """
    List all calibration jobs and save to a timestamped markdown file.
    """
    print("Fetching calibration jobs...")
    response = requests.post(
        f"{API_BASE}/calibration/get_calibration_jobs/",
        headers={**get_auth_headers(), "Content-Type": "application/json"},
    )
    check_http_error(response.status_code, response.text, exit_on_error=True)

    jobs = response.json().get("jobs", [])

    if not jobs:
        print("No jobs found.")
        return

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

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    filename = f"calibration_jobs_{timestamp}.md"
    full_path = os.path.abspath(filename)

    with open(full_path, "w", encoding="utf-8") as f:
        f.write(markdown_table)

    print(f"Saved {len(rows)} jobs to {full_path}")


def _submit_job_data(job_file: str, calibration_run_id: str | None = None):
    """
    Submits job data to the import endpoint, used by both import and update.

    :param job_file: Path to the JSON file
    :param calibration_run_id: Optional calibration_run_id for update
    """
    with open(job_file, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    payload = {"data": job_data}
    if calibration_run_id is not None:
        payload["calibration_run_id"] = calibration_run_id

    response = requests.post(
        f"{API_BASE}/calibration/import/",
        headers={**get_auth_headers(), "Content-Type": "application/json"},
        json=payload,
    )
    check_http_error(response.status_code, response.text, exit_on_error=True)


def import_job(job_file: str):
    """
    Imports a new job definition from a JSON file.
    """
    print(f"Importing job from: {job_file}")
    _submit_job_data(job_file)


def update_job(calibration_run_id: str, job_file: str):
    """
    Updates an existing calibration job using a JSON file.
    """
    print(f"Updating job {calibration_run_id} from: {job_file}")
    _submit_job_data(job_file, calibration_run_id=calibration_run_id)


def handle_export_display(calibration_run_id: str, output: str = None, display: bool = False):
    """
    Exports a calibration job to a file or displays it.
    """
    payload = {"calibration_run_id": calibration_run_id}

    response = requests.post(
        f"{API_BASE}/calibration/export/",
        headers={**get_auth_headers(), "Content-Type": "application/json"},
        json=payload,
    )

    if not check_http_error(response.status_code, response.text, exit_on_error=True):
        return

    data = response.json()

    if display:
        _pretty_print_job(calibration_run_id, data)

    if output is not None or not display:
        default_filename = f"export_{calibration_run_id}.json"
        output = os.path.expanduser(os.path.expandvars(output or default_filename))

        if output.endswith(os.sep) or (os.path.exists(output) and os.path.isdir(output)):
            os.makedirs(output, exist_ok=True)
            path = os.path.join(output, default_filename)
        else:
            path = output

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        print(f"Exported to {path}")


def _pretty_print_job(calibration_run_id: str, data: dict):
    """
    Prints selected fields from the exported calibration job in a structured format.
    """

    def fmt(dt: str | None) -> str:
        """
        Formats an ISO timestamp string in GMT (UTC) to 'YYYY-MM-DD HH:MM'.
        Handles optional 'Z' or '+00:00' suffixes.
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
