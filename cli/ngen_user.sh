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

    # Extract the HTTP status code
    http_status="${response: -3}"

    # Read the response body if the file exists
    response_body=$([[ -f /tmp/curl_response ]] && cat /tmp/curl_response || echo "")

    # Handle login success
    if [[ "$http_status" -eq 200 ]]; then
        access_token=$(echo "$response_body" | jq -r '.access' 2>/dev/null)
        export ACCESS_TOKEN="$access_token"
        echo "'$email' login successful."
    else
        # Handle login failure or connection issues
        if [[ "$http_status" -eq 000 ]]; then
            echo "Login failed: Unable to connect to the server."
        else
            echo "Login failed with status code $http_status."
            echo "$response_body" | jq --indent 3 2>/dev/null || echo "$response_body"
        fi
        rm -f /tmp/curl_response
        exit 1
    fi

    # Clean up the temp file
    rm -f /tmp/curl_response
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
        if [[ "$http_status" -eq 000 ]]; then
            echo "Registration failed: Unable to connect to the server."
        else
            echo "Registration failed. HTTP Status: $http_status"
            echo "$response_body" | jq --indent 3 2>/dev/null || echo "$response_body"
        fi
        rm -f /tmp/curl_response
        return 1
    fi

    # Clean up the temp file
    rm -f /tmp/curl_response
}

# Clean up the temp file
rm -f /tmp/curl_response
