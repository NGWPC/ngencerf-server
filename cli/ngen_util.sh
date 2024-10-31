#!/bin/bash

# Function to check HTTP errors with optional immediate exit
check_http_error() {
    local http_status=$1
    local response=$2
    local exit_on_error=${3:-false}  # Default to not exiting on error

    if [ "$http_status" -eq 000 ]; then
        echo "Error: Could not connect to the server."
        [[ "$exit_on_error" == true ]] && exit 1 || return 1
    elif [ "$http_status" -eq 400 ]; then
        echo "Server returned HTTP 400 Bad Request. Response:"
        echo "$response" | jq --indent 3
        [[ "$exit_on_error" == true ]] && exit 1 || return 1
    elif [ "$http_status" -ne 200 ]; then
        echo "Error: Server returned HTTP status code $http_status."
        echo "$response" | jq --indent 3
        [[ "$exit_on_error" == true ]] && exit 1 || return 1
    fi
}
