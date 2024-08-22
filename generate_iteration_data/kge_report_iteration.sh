#!/bin/bash

# Check if a file argument is passed
if [ -z "$1" ]; then
    echo "Error: No file provided. Please provide a JSON file as an argument."
    exit 1
fi

# shellcheck disable=SC1090
source ~/projects/cerfServer/Import_test_data/ngen_login.sh

# Check if ACCESS_TOKEN is set
if [ -z "$ACCESS_TOKEN" ]; then
    echo "Error: ACCESS_TOKEN is not set. Please check the login script."
    exit 1
fi


# Read data from file
data=$(cat "$1")

# Extract optimization value
optimization=$(echo "$data" | jq -r '.optimization'  | awk '{print toupper($0)}')

# Loop through each entry in the JSON data
echo "$data" | jq -c '.list[]' | while read -r entry; do
    calibration_run_id=$(echo "$entry" | jq -r '.calibration_run_id')
    iteration=$(echo "$entry" | jq -r '.iteration')
    worker_name=$(echo "$entry" | jq -r '.worker_name')

    # Construct and execute the curl command
    curl --location 'http://localhost:8000/calibration/report_iteration/' \
    --header 'Content-Type: application/json' \
    --header "Authorization: Bearer $ACCESS_TOKEN" \
    --data '{
        "calibration_run_id": '"$calibration_run_id"',
        "optimization": "'"$optimization"'",
        "iteration": '"$iteration"',
        "worker_name": "'"$worker_name"'"
    }'
    echo
done

