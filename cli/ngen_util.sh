#!/bin/bash

# Centralized function to handle HTTP errors
check_http_error() {
    local http_status="$1"
    local response="$2"

    if [ "$http_status" -eq 000 ]; then
        echo "Error: Could not connect to the server."
        return 1
    elif [ "$http_status" -eq 400 ]; then
        echo "Server returned HTTP 400 Bad Request. Response:"
        echo "$response" | jq --indent 3
        return 1
    elif [ "$http_status" -eq 401 ]; then
        echo "Invalid username or password."
        echo "Response: $response"
        return 1
    elif [ "$http_status" -ne 200 ]; then
        echo "Error: Server returned HTTP status code $http_status."
        echo "Response: $response"
        return 1
    fi
}
