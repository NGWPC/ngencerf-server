#!/bin/bash

# Before running, you need to set your USERNAME and PASSWORD
# export NGEN_USERNAME="your_username"
# export NGEN_PASSWORD="your_password"

# Check if the USERNAME and PASSWORD environment variables are set
if [ -z "$NGEN_USERNAME" ] || [ -z "$NGEN_PASSWORD" ]; then
    echo "Error: NGEN_USERNAME and NGEN_PASSWORD environment variables must be set."
    exit 1
fi

# Define the register endpoint
register_endpoint="http://localhost:8000/auth/users/"

# Send the register request
curl --silent --location --request POST "$register_endpoint" \
    --header 'Content-Type: application/json' \
    --data-raw "{ \"username\": \"$NGEN_USERNAME\", \"password\": \"$NGEN_PASSWORD\" }" | jq .


