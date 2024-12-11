#!/bin/bash

# Source the utility functions
source ./ngen_util.sh

# Function to handle the geopackage upload
upload_geopackage_data() {
    # Arguments:
    # $1 - Path to the geopackage file
    # $2 - Calibration run ID for associating the upload

    local geopackage_file=$1
    local calibration_run_id=$2

    # Check if the geopackage file exists
    if [ ! -f "$geopackage_file" ]; then
        echo "Error: Geopackage file '$geopackage_file' does not exist."
        exit 1
    fi

    echo "Uploading geopackage: $geopackage_file for calibration_run_id: $calibration_run_id"

    # Send the upload request to the server
    response=$(curl --location --write-out "%{http_code}" --silent --output /tmp/curl_response \
        --header 'Content-Type: multipart/form-data' \
        --header "Authorization: Bearer $ACCESS_TOKEN" \
        --form "return_geopackage_url=false" \
        --form "geopackage_file=@$geopackage_file" \
        --form "calibration_run_id=$calibration_run_id" \
        "http://localhost:8000/calibration/upload_geopackage_data/")

    # Capture the HTTP status and response content
    http_status=$(tail -n1 <<< "$response")
    response=$([[ -f /tmp/curl_response ]] && cat /tmp/curl_response || echo "")

    # Check for HTTP errors and exit if needed
    check_http_error "$http_status" "$response" true

    # Clean up the temporary file
    rm -f /tmp/curl_response
}

# Function to handle the observational data upload
upload_observational_data() {
    # Arguments:
    # $1 - Path to the observational data file
    # $2 - Calibration run ID for associating the upload

    local observational_filepath=$1
    local calibration_run_id=$2

    # Check if the observational file exists
    if [ ! -f "$observational_filepath" ]; then
        echo "Error: Observational data file '$observational_filepath' does not exist."
        exit 1
    fi

    echo "Uploading observational data: $observational_filepath for calibration_run_id: $calibration_run_id"

    # Send the upload request to the server
    response=$(curl --location --write-out "%{http_code}" --silent --output /tmp/curl_response \
        --header 'Content-Type: multipart/form-data' \
        --header "Authorization: Bearer $ACCESS_TOKEN" \
        --form "observational_file=@$observational_filepath" \
        --form "calibration_run_id=$calibration_run_id" \
        "http://localhost:8000/calibration/upload_observational_data/")

    # Capture the HTTP status and response content
    http_status=$(tail -n1 <<< "$response")
    response=$([[ -f /tmp/curl_response ]] && cat /tmp/curl_response || echo "")

    # Check for HTTP errors and exit if needed
    check_http_error "$http_status" "$response" true

    # Clean up the temporary file
    rm -f /tmp/curl_response
}

# Function to handle the forcing data upload
upload_forcing_data() {
    # Arguments:
    # $1 - Directory containing forcing data files
    # $2 - Calibration run ID for associating the upload

    local forcing_dir=$1
    local calibration_run_id=$2

    # Check if the forcing data directory exists
    if [ ! -d "$forcing_dir" ]; then
        echo "Error: Forcing data directory '$forcing_dir' does not exist."
        exit 1
    fi

    echo "Uploading forcing data from directory: '$forcing_dir' for calibration_run_id: $calibration_run_id"

    # Gather forcing files from the specified directory
    form_files=()

    # Add the files from the directory to the form data
    for file in "$forcing_dir"/*; do
        if [ -f "$file" ]; then
            form_files+=("--form" "forcing_files=@$file")
        fi
    done

    # Ensure at least one file exists in the directory
    if [ ${#form_files[@]} -eq 0 ]; then
        echo "Error: No files found in the forcing data directory."
        exit 1
    fi

    # Send the upload request to the server
    response=$(curl --location --write-out "%{http_code}" --silent --output /tmp/curl_response \
        --header 'Content-Type: multipart/form-data' \
        --header "Authorization: Bearer $ACCESS_TOKEN" \
        "${form_files[@]}" \
        --form "calibration_run_id=$calibration_run_id" \
        "http://localhost:8000/calibration/upload_forcing_data/")

    # Capture the HTTP status and response content
    http_status=$(tail -n1 <<< "$response")
    response=$([[ -f /tmp/curl_response ]] && cat /tmp/curl_response || echo "")

    # Check for HTTP errors and exit if needed
    check_http_error "$http_status" "$response" true

    # Clean up the temporary file
    rm -f /tmp/curl_response
}

# Function to submit a calibration run job
run_job() {
    # Argument:
    # $1 - Calibration run ID for the job submission

    local calibration_run_id=$1

    echo "Submitting calibration run job $calibration_run_id"

    # Prepare the JSON payload for the request
    json_payload=$(jq -n --arg calibration_run_id "$calibration_run_id" '{calibration_run_id: $calibration_run_id}')

    # Send the job submission request to the server
    response=$(curl --location --write-out "%{http_code}" --silent --output /tmp/curl_response \
        --header 'Content-Type: application/json' \
        --header "Authorization: Bearer $ACCESS_TOKEN" \
        --data "$json_payload" \
        "http://localhost:8000/calibration/run_calibration/")

    # Capture the HTTP status and response content
    http_status=$(tail -n1 <<< "$response")
    response=$([[ -f /tmp/curl_response ]] && cat /tmp/curl_response || echo "")

    # Check for HTTP errors and exit if needed
    check_http_error "$http_status" "$response" true

    # Clean up the temporary file
    rm -f /tmp/curl_response
}

# Function to delete a calibration run job
delete_job() {
    # Argument:
    # $1 - Calibration run ID for the job to be deleted

    local calibration_run_id=$1

    echo "Deleting calibration run job $calibration_run_id"

    # Prepare the JSON payload for the request
    json_payload=$(jq -n --arg calibration_run_id "$calibration_run_id" '{calibration_run_id: $calibration_run_id}')

    # Send the job deletion request to the server
    response=$(curl --location --write-out "%{http_code}" --silent --output /tmp/curl_response \
        --header 'Content-Type: application/json' \
        --header "Authorization: Bearer $ACCESS_TOKEN" \
        --data "$json_payload" \
        "http://localhost:8000/calibration/delete_job/")

    # Capture the HTTP status and response content
    http_status=$(tail -n1 <<< "$response")
    response=$([[ -f /tmp/curl_response ]] && cat /tmp/curl_response || echo "")

    # Check for HTTP errors and exit if needed
    check_http_error "$http_status" "$response" true

    # Clean up the temporary file
    rm -f /tmp/curl_response
}

# Function to cancel a calibration run job
cancel_job() {
    # Argument:
    # $1 - Calibration run ID for the job to be canceled

    local calibration_run_id=$1

    echo "Cancelling calibration run job $calibration_run_id"

    # Prepare the JSON payload for the request
    json_payload=$(jq -n --arg calibration_run_id "$calibration_run_id" '{calibration_run_id: $calibration_run_id}')

    # Send the job cancellation request to the server
    response=$(curl --location --write-out "%{http_code}" --silent --output /tmp/curl_response \
        --header 'Content-Type: application/json' \
        --header "Authorization: Bearer $ACCESS_TOKEN" \
        --data "$json_payload" \
        "http://localhost:8000/calibration/cancel_job/")

    # Capture the HTTP status and response content
    http_status=$(tail -n1 <<< "$response")
    response=$([[ -f /tmp/curl_response ]] && cat /tmp/curl_response || echo "")

    # Check for HTTP errors and exit if needed
    check_http_error "$http_status" "$response" true

    # Clean up the temporary file
    rm -f /tmp/curl_response
}
