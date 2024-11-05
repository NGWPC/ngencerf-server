#!/bin/bash

# Function to check HTTP errors with optional immediate exit
# Arguments:
#   - http_status: The HTTP status code from the server response.
#   - response: The server response body, typically in JSON format.
#   - exit_on_error: Optional flag (default: false). If true, exits the script upon encountering an error.
# Behavior:
#   - Prints the response body in formatted JSON regardless of the error status.
#   - If http_status is not 200, displays an error message based on the code.
#   - Exits the script immediately if exit_on_error is true and an error is encountered.
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
        echo "Error: Server returned HTTP status code $http_status. Response:"
        echo "$response" | jq --indent 3
        [[ "$exit_on_error" == true ]] && exit 1 || return 1
    fi
    # For a successful response, print it only if it's not empty and the status is 200
    if [ "$http_status" -eq 200 ] && [ -n "$response" ]; then
        echo "$response" | jq --indent 3
    fi
    return 0
}
