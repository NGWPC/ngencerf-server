#!/bin/bash

# Function to print usage
print_usage() {
    echo "Usage: $0 [import|export] <file|calibration_run_id>"
    echo "  import <file> : Import the provided JSON file."
    echo "  export <calibration_run_id> : Export the JSON data for the given calibration_run_id."
    exit 1
}

# Check if operation and argument are provided
if [ -z "$1" ] || [ -z "$2" ]; then
    print_usage
fi

# Set operation and argument
operation="$1"
argument="$2"

source ./ngen_login.sh

# Check if ACCESS_TOKEN is set
if [ -z "$ACCESS_TOKEN" ]; then
    echo "Error: ACCESS_TOKEN is not set. Please check the login script."
    exit 1
fi

# Function to check for HTTP errors
check_http_error() {
    http_status=$1
    response=$2
    if [ "$http_status" -eq 000 ]; then
        echo "Error: Could not connect to the server."
        exit 1
    elif [ "$http_status" -eq 400 ]; then
        echo "Server returned HTTP 400 Bad Request. Response:"
        echo "$response"  # Print the actual server response
        rm -f /tmp/curl_response  # Clean up the temp file
        exit 1
    elif [ "$http_status" -ne 200 ]; then
        echo "Error: Server returned HTTP status code $http_status."
        rm -f /tmp/curl_response  # Clean up the temp file
        exit 1
    fi
}

# Handle import operation
if [ "$operation" == "import" ]; then
    # Check if the provided argument is a file
    if [ ! -f "$argument" ]; then
        echo "Error: File $argument not found."
        exit 1
    fi

    # Read data from file
    data=$(cat "$argument")

    # Send import request, capture the HTTP status and response
    response=$(curl --location --write-out "%{http_code}" --silent --output /tmp/curl_response \
    --header 'Content-Type: application/json' \
    --header "Authorization: Bearer $ACCESS_TOKEN" \
    --data "$data" 'http://localhost:8000/calibration/import/')

    # Extract HTTP status and response
    http_status=$(tail -n1 <<< "$response")

    if [ -f /tmp/curl_response ]; then
       response=$(cat /tmp/curl_response)
    else
       response=""
    fi

    check_http_error "$http_status" "$response"

    # Print the response
    if ! echo "$response" | jq . 2>/dev/null; then
       echo "Error parsing response."
    fi

    # Clean up the temporary file
    rm -f /tmp/curl_response

# Handle export operation
elif [ "$operation" == "export" ]; then
    calibration_run_id="$argument"

    echo "calibration_run_id: $calibration_run_id"
    # Send export request, capture the HTTP status and response
    response=$(curl --location --write-out "%{http_code}" --silent -v --output /tmp/curl_response \
    --header 'Content-Type: application/json' \
    --header "Authorization: Bearer $ACCESS_TOKEN" \
    "http://localhost:8000/calibration/export/?calibration_run_id=$calibration_run_id")


    # Extract HTTP status and response
    http_status=$(tail -n1 <<< "$response")
    response=$(cat /tmp/curl_response)

    check_http_error "$http_status" "$response"

    # Save the response to a JSON file
    if ! echo "$response" | jq . > "calibration_run_$calibration_run_id.json" 2>/dev/null; then
       echo "Error parsing response or saving to file."
    else
       echo "Exported calibration run data to calibration_run_$calibration_run_id.json"
    fi

    # Clean up the temporary file
    rm -f /tmp/curl_response

else
    print_usage
fi
