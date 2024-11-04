#!/bin/bash

# Function to check HTTP errors and optionally exit the script
# Arguments:
# $1 - HTTP status code returned from the request
# $2 - Exit flag (optional); if set to true, exit on any error
check_http_error() {
    local http_status=$1
    local exit_on_error=${2:-false}  # Default behavior is not to exit

    # Handle connection failure (status code 000 indicates no connection)
    if [ "$http_status" -eq 000 ]; then
        echo "Error: Could not connect to the server."
        # Exit if specified, otherwise return error status
        [[ "$exit_on_error" == true ]] && exit 1 || return 1

    # Handle specific HTTP error 400 (Bad Request)
    elif [ "$http_status" -eq 400 ]; then
        echo "Server returned HTTP 400 Bad Request."
        # Exit if specified, otherwise return error status
        [[ "$exit_on_error" == true ]] && exit 1 || return 1

    # Handle all other non-200 HTTP status codes as generic errors
    elif [ "$http_status" -ne 200 ]; then
        echo "Error: Server returned HTTP status code $http_status."
        # Exit if specified, otherwise return error status
        [[ "$exit_on_error" == true ]] && exit 1 || return 1
    fi

    # If no errors, return success status
    return 0
}
