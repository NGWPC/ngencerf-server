#!/bin/bash

# Before running, you need to set your USERNAME (email) and PASSWORD
# export NGEN_USERNAME="your_username"
# export NGEN_PASSWORD="your_password"
# or you can put them at the bottom of ~/.bashrc

# Check if the USERNAME and PASSWORD environment variables are set
if [ -z "$NGEN_USERNAME" ] || [ -z "$NGEN_PASSWORD" ]; then
    echo "Error: NGEN_USERNAME and NGEN_PASSWORD environment variables must be set."
    exit 1
fi

# Define the register endpoint
register_endpoint="http://localhost:8000/auth/users/"

# Send the register request and capture the response and status code
response=$(curl --silent --location --write-out "%{http_code}" --output /tmp/curl_register_response \
    --request POST "$register_endpoint" \
    --header 'Content-Type: application/json' \
    --data-raw "{ \"email\": \"$NGEN_USERNAME\", \"password\": \"$NGEN_PASSWORD\" }")

# Extract the HTTP status code
http_status="${response: -3}"
response_body=$(cat /tmp/curl_register_response)

# Print out the response body
echo "Response Body: $response_body"

# Print out the HTTP status code
echo "HTTP Status: $http_status"

# Clean up the temp file
rm -f /tmp/curl_register_response
