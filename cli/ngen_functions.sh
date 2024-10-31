#!/bin/bash

# Source the utility functions
source ./ngen_util.sh

# Function to handle the geopackage upload
upload_geopackage_data() {
    local geopackage_file=$1
    local calibration_run_id=$2

    echo "Uploading geopackage: $geopackage_file for calibration_run_id: $calibration_run_id"

    # Send upload_geopackage request, capture the HTTP status and response
    response=$(curl --location --write-out "%{http_code}" --silent --output /tmp/curl_response \
    --header 'Content-Type: multipart/form-data' \
    --header "Authorization: Bearer $ACCESS_TOKEN" \
    --form "return_geopackage_url=false" \
    --form "geopackage_file=@$geopackage_file" \
    --form "calibration_run_id=$calibration_run_id" \
    "http://localhost:8000/calibration/upload_geopackage_data/")

    # Extract HTTP status and response
    http_status=$(tail -n1 <<< "$response")
    response=$([[ -f /tmp/curl_response ]] && cat /tmp/curl_response || echo "")

    check_http_error "$http_status" "$response" true

    # Print the full response
    echo "$response" | jq --indent 3

    # Clean up the temporary file
    rm -f /tmp/curl_response
}

# Function to handle the observational upload
upload_observational_data() {
    local observational_filepath=$1
    local calibration_run_id=$2

    echo "Uploading observational data: $observational_filepath for calibration_run_id: $calibration_run_id"

    # Send upload_observational request, capture the HTTP status and response
    response=$(curl --location --write-out "%{http_code}" --silent --output /tmp/curl_response \
    --header 'Content-Type: multipart/form-data' \
    --header "Authorization: Bearer $ACCESS_TOKEN" \
    --form "observational_file=@$observational_filepath" \
    --form "calibration_run_id=$calibration_run_id" \
    "http://localhost:8000/calibration/upload_observational_data/")

    # Extract HTTP status and response
    http_status=$(tail -n1 <<< "$response")
    response=$([[ -f /tmp/curl_response ]] && cat /tmp/curl_response || echo "")

    check_http_error "$http_status" "$response" true

    # Print the full response
    echo "$response" | jq --indent 3

    # Clean up the temporary file
    rm -f /tmp/curl_response
}

# Function to handle the forcing upload
upload_forcing_data() {
    local forcing_dir=$1
    local calibration_run_id=$2

    echo "Uploading forcing data from directory: '$forcing_dir' for calibration_run_id: $calibration_run_id"

    # Initialize an array to hold all the --form arguments
    form_files=()

    # Add the files from the directory to the form data
    for file in "$forcing_dir"/*; do
        if [ -f "$file" ]; then
            form_files+=("--form" "forcing_files=@$file")
        fi
    done

    if [ ${#form_files[@]} -eq 0 ]; then
        echo "Error: No files found in the forcing data directory."
        exit 1
    fi

    # Send upload_forcing request, capture the HTTP status and response
    response=$(curl --location --write-out "%{http_code}" --silent --output /tmp/curl_response \
    --header 'Content-Type: multipart/form-data' \
    --header "Authorization: Bearer $ACCESS_TOKEN" \
    "${form_files[@]}" \
    --form "calibration_run_id=$calibration_run_id" \
    "http://localhost:8000/calibration/upload_forcing_data/")

    # Extract HTTP status and response
    http_status=$(tail -n1 <<< "$response")
    response=$([[ -f /tmp/curl_response ]] && cat /tmp/curl_response || echo "")

    check_http_error "$http_status" "$response" true

    # Print the full response
    echo "$response" | jq --indent 3

    # Clean up the temporary file
    rm -f /tmp/curl_response
}

# Function to run the job
run_job() {
    local calibration_run_id=$1

    echo "Submitting calibration run job $calibration_run_id"

    # Prepare the JSON payload
    json_payload=$(jq -n --arg calibration_run_id "$calibration_run_id" '{calibration_run_id: $calibration_run_id}')

    response=$(curl --location --write-out "%{http_code}" --silent --output /tmp/curl_response \
    --header 'Content-Type: application/json'\
    --header "Authorization: Bearer $ACCESS_TOKEN" \
    --data "$json_payload" \
    "http://localhost:8000/calibration/run_calibration/")

    # Extract HTTP status and response
    http_status=$(tail -n1 <<< "$response")
    response=$([[ -f /tmp/curl_response ]] && cat /tmp/curl_response || echo "")

    check_http_error "$http_status" "$response"
    echo "$response" | jq . --indent 3 2>/dev/null || echo "Error parsing response."
    rm -f /tmp/curl_response
}

# Function to delete the job
delete_job() {
    local calibration_run_id=$1

    echo "Deleting calibration run job $calibration_run_id"

    # Prepare the JSON payload
    json_payload=$(jq -n --arg calibration_run_id "$calibration_run_id" '{calibration_run_id: $calibration_run_id}')

    response=$(curl --location --write-out "%{http_code}" --silent --output /tmp/curl_response \
    --header 'Content-Type: application/json'\
    --header "Authorization: Bearer $ACCESS_TOKEN" \
    --data "$json_payload" \
    "http://localhost:8000/calibration/delete_job/")

    # Extract HTTP status and response
    http_status=$(tail -n1 <<< "$response")
    response=$([[ -f /tmp/curl_response ]] && cat /tmp/curl_response || echo "")

    check_http_error "$http_status" "$response"
    echo "$response" | jq . --indent 3 2>/dev/null || echo "Error parsing response."
    rm -f /tmp/curl_response
}

# Function to cancel the job
cancel_job() {
    local calibration_run_id=$1

    echo "Cancelling calibration run job $calibration_run_id"

    # Prepare the JSON payload
    json_payload=$(jq -n --arg calibration_run_id "$calibration_run_id" '{calibration_run_id: $calibration_run_id}')

    response=$(curl --location --write-out "%{http_code}" --silent --output /tmp/curl_response \
    --header 'Content-Type: application/json'\
    --header "Authorization: Bearer $ACCESS_TOKEN" \
    --data "$json_payload" \
    "http://localhost:8000/calibration/cancel_job/")
    http_status=$(tail -n1 <<< "$response")
    response=$([[ -f /tmp/curl_response ]] && cat /tmp/curl_response || echo "")

    check_http_error "$http_status" "$response"
    echo "$response" | jq . --indent 3 2>/dev/null || echo "Error parsing response."
    rm -f /tmp/curl_response
}
