#!/bin/bash

# Before running, you need to set your USERNAME and PASSWORD
# export NGEN_USERNAME="your_username"
# export NGEN_PASSWORD="your_password"
# or you can put them at the bottom of ~/.bashrc

# Check if the USERNAME and PASSWORD environment variables are set
if [ -z "$NGEN_USERNAME" ] || [ -z "$NGEN_PASSWORD" ]; then
    echo "Error: NGEN_USERNAME and NGEN_PASSWORD environment variables must be set."
    exit 1
fi

# Function to check for HTTP errors
check_http_error() {
    http_status=$1
    if [ "$http_status" -eq 000 ]; then
        echo "Error: Could not connect to the server."
        exit 1
    elif [ "$http_status" -eq 401 ]; then
        echo "Invalid userid or password"
        rm -f /tmp/curl_response  # Clean up the temp file
        exit 1
    elif [ "$http_status" -ne 200 ]; then
        echo "Error: Server returned HTTP status code $http_status."
        rm -f /tmp/curl_response  # Clean up the temp file
        exit 1
    fi
}

# Define the login endpoint
login_endpoint="http://localhost:8000/auth/jwt/create"

# Send the login request and capture both the HTTP status and response
response=$(curl --silent --location --write-out "%{http_code}" --output /tmp/curl_response \
    --request POST "$login_endpoint" \
    --header 'Content-Type: application/json' \
    --data-raw "{ \"email\": \"$NGEN_USERNAME\", \"password\": \"$NGEN_PASSWORD\" }")

# Extract the HTTP status code and response
http_status=$(tail -n1 <<< "$response")
if [ -f /tmp/curl_response ]; then
   response=$(cat /tmp/curl_response)
else
   response=""
fi

check_http_error "$http_status"

# Extract the access token from the response
access_token=$(echo "$response" | jq -r '.access' 2>/dev/null)

# Check if the access token was successfully retrieved
if ! echo "$response" | jq -e '.access' >/dev/null 2>&1 || [ -z "$access_token" ] || [ "$access_token" == "null" ]; then
    echo "Login failed. Please check your email and password."
    echo "Response: $response"
    rm -f /tmp/curl_response  # Clean up the temp file
    exit 1
else
    export ACCESS_TOKEN="$access_token"
    echo "'$NGEN_USERNAME' login successful."
fi

