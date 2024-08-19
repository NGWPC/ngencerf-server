#!/bin/bash

# Before running, you need to set your USERNAME and PASSWORD
# export NGEN_USERNAME="your_username"
# export NGEN_PASSWORD="your_password"

# Check if the USERNAME and PASSWORD environment variables are set
if [ -z "$NGEN_USERNAME" ] || [ -z "$NGEN_PASSWORD" ]; then
    echo "Error: NGEN_USERNAME and NGEN_PASSWORD environment variables must be set."
    exit 1
fi

# Define the login endpoint
login_endpoint="http://localhost:8000/auth/jwt/create"

# Send the login request
response=$(curl --silent --location --request POST "$login_endpoint" \
    --header 'Content-Type: application/json' \
    --data-raw "{ \"username\": \"$NGEN_USERNAME\", \"password\": \"$NGEN_PASSWORD\" }")

# Extract the access token from the response
access_token=$(echo "$response" | jq -r '.access')

# Check if the access token was successfully retrieved
if [ "$access_token" != "null" ]; then
    export ACCESS_TOKEN="$access_token"
    echo "Login successful. Access token saved to ACCESS_TOKEN environment variable."
else
    echo "Login failed. Please check your username and password."
    echo "Response: $response"
    exit 1
fi

