#!/bin/bash

# Define the endpoints
login_endpoint="http://localhost:8000/auth/jwt/create"
register_endpoint="http://localhost:8000/auth/users/"

# Function to print usage
print_usage() {
    echo "Usage: $0 [ngen_login|ngen_register] [optional_email]"
    echo ""
    echo "  Commands:"
    echo "    ngen_login : Log in the user and retrieve an access token."
    echo "    ngen_register [optional_email] : Register a new user account. Email can be passed as an argument."
    echo ""
    return 1
}

# Function for login
ngen_login() {
    # Use NGEN_EMAIL if set, otherwise fallback to NGEN_USERNAME
    email="${NGEN_EMAIL:-$NGEN_USERNAME}"

    if [ -z "$email" ]; then
        read -p "ngenCerf email: " email
    fi
    if [ -z "$NGEN_PASSWORD" ]; then
        read -sp "ngenCerf password: " NGEN_PASSWORD
        echo  # Move to a new line after password input
    fi

    # Send the login request and capture both the HTTP status and response
    response=$(curl --silent --location --write-out "%{http_code}" --output /tmp/curl_response \
        --request POST "$login_endpoint" \
        --header 'Content-Type: application/json' \
        --data-raw "{ \"email\": \"$email\", \"password\": \"$NGEN_PASSWORD\" }")

    # Extract the HTTP status code and response
    http_status="${response: -3}"
    response_body=$([[ -f /tmp/curl_response ]] && cat /tmp/curl_response || echo "")

    check_http_error "$http_status" "$response_body" || return 1

    # Extract the access token from the response
    access_token=$(echo "$response_body" | jq -r '.access' 2>/dev/null)

    if [ -z "$access_token" ] || [ "$access_token" == "null" ]; then
        echo "Login failed. Please check your email and password."
        echo "Response: $response_body"
        return 1
    else
        export ACCESS_TOKEN="$access_token"
        echo "'$email' login successful. ACCESS_TOKEN set."
    fi
}

# Function for register with optional email argument
ngen_register() {
    # Check if an email was passed as an argument, otherwise use NGEN_EMAIL or NGEN_USERNAME as fallback
    email="${1:-${NGEN_EMAIL:-$NGEN_USERNAME}}"

    # Prompt for email if none was provided
    if [ -z "$email" ]; then
        read -p "Enter a new email for ngenCerf registration: " email
    fi

    # Prompt for password twice for confirmation
    while true; do
        read -sp "Enter a new password for ngenCerf registration: " NGEN_PASSWORD
        echo
        read -sp "Confirm your password: " NGEN_PASSWORD_CONFIRM
        echo
        if [ "$NGEN_PASSWORD" == "$NGEN_PASSWORD_CONFIRM" ]; then
            break
        else
            echo "Passwords do not match. Please try again."
        fi
    done

    # Send the registration request, capture the HTTP status and response
    response=$(curl --silent --location --write-out "%{http_code}" --output /tmp/curl_response \
        --request POST "$register_endpoint" \
        --header 'Content-Type: application/json' \
        --data-raw "{ \"email\": \"$email\", \"password\": \"$NGEN_PASSWORD\" }")

    http_status="${response: -3}"
    response_body=$([[ -f /tmp/curl_response ]] && cat /tmp/curl_response || echo "")

    # Check registration status
    if [ "$http_status" -eq 201 ]; then
        echo "Registration successful for user '$email'."
    else
        echo "Registration failed. HTTP Status: $http_status"
        echo "Response Body: $response_body"
        return 1
    fi
}

# Clean up the temp file
rm -f /tmp/curl_response
