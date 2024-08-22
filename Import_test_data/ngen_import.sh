#!/bin/bash

# Check if a file argument is passed
if [ -z "$1" ]; then
    echo "Error: No file provided. Please provide a JSON file as an argument."
    exit 1
fi

source ./ngen_login.sh

# Check if ACCESS_TOKEN is set
if [ -z "$ACCESS_TOKEN" ]; then
    echo "Error: ACCESS_TOKEN is not set. Please check the login script."
    exit 1
fi


# Read data from file
data=$(cat "$1")

curl --location 'http://localhost:8000/calibration/import/' \
--header 'Content-Type: application/json' \
--header "Authorization: Bearer $ACCESS_TOKEN" \
--data "$data" | jq .


