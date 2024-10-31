#!/bin/bash

# Source functions from both ngen_util.sh and ngen_functions.sh
source ./ngen_util.sh
source ./ngen_functions.sh
source ./ngen_user.sh  # For ngen_login and ngen_register functions

# Instructions for setting NGEN_EMAIL and NGEN_PASSWORD
# --------------------------------------------------------
# To avoid being prompted for your email and password, you can set these variables in several ways:
#
# 1. Temporarily export in the current session (lasts only until the session ends):
#    Run the following commands before executing this script:
#        export NGEN_EMAIL="your_email@example.com"
#        export NGEN_PASSWORD="your_password"
#
# 2. Add to your shell configuration file (persistent across sessions):
#    Add the following lines to your ~/.bashrc (or ~/.zshrc if using zsh) and then reload the file
#    by running `source ~/.bashrc`:
#        export NGEN_EMAIL="your_email@example.com"
#        export NGEN_PASSWORD="your_password"
#
# 3. Pass directly on the command line (applies only to this execution):
#    Use the export command inline with your call to this script:
#        NGEN_EMAIL="your_email@example.com" NGEN_PASSWORD="your_password" ./ngencerf.sh import <file>
#
# Note: If NGEN_EMAIL is not set, NGEN_USERNAME will be used as a fallback.

# Function to print usage
print_usage() {
    echo "Usage: $0 [import|export|delete|cancel|run|register] <file|calibration_run_id> [keyword arguments]"
    echo ""
    echo "  Commands:"
    echo "    import <file> : Import the provided JSON file."
    echo "        Optional arguments:"
    echo "          observational_file=<file path>    (optional) : Path to the observational data file (CSV format)."
    echo "          forcing_dir=<directory path>      (optional) : Path to the directory containing forcing data (CSV files)."
    echo "          geopackage_file=<file path>       (optional) : Path to the geopackage file (GPKG format)."
    echo "          run_after_import=true|false       (optional) : Whether to run the calibration job after import (default: false)."
    echo ""
    echo "    export <calibration_run_id> : Export the JSON data for the given calibration_run_id."
    echo "        Optional arguments:"
    echo "          output=<directory or file path>   (optional) : Path to save the exported file (default filename used if a directory is provided)."
    echo ""
    echo "    run <calibration_run_id> : Run the calibration_run_id job."
    echo "    delete <calibration_run_id> : Delete the calibration_run_id job."
    echo "    cancel <calibration_run_id> : Cancel the calibration_run_id job."
    echo "    register [email] : Register a new user with email and password. Optionally provide email as an argument."
    echo ""
    echo "  Example usage:"
    echo "    $0 import data.json observational_file=obs.csv forcing_dir=forcing run_after_import=true"
    echo "    $0 export 123 output=/path/to/exported_data.json"
    echo "    $0 run 123"
    echo "    $0 register user@example.com"
    exit 1
}

# Main Script Execution Logic
# ---------------------------

# Check if operation is provided
if [ -z "$1" ]; then
    print_usage
fi

# Set operation and argument
operation="$1"
argument="$2"
shift 2  # Shift past the first two positional arguments

# Handle the "register" operation before parsing other options
if [ "$operation" == "register" ]; then
    ngen_register "$argument"  # Call the register function with optional email argument
    exit 0
fi

# Parse the keyword arguments for other operations
observational_file=""
forcing_dir=""
geopackage_file=""
output=""
run_after_import=false

for arg in "$@"; do
    case $arg in
        observational_file=*) observational_file="${arg#*=}";;
        forcing_dir=*) forcing_dir="${arg#*=}";;
        geopackage_file=*) geopackage_file="${arg#*=}";;
        output=*) output="${arg#*=}";;
        run_after_import=*) run_after_import="${arg#*=}";;
        *) echo "Unknown argument: $arg"; print_usage;;
    esac
done

# Preserve the operation variable before calling login
original_operation="$operation"
ngen_login  # Call the login function from ngen_user.sh
operation="$original_operation"  # Restore the original operation after login

if [ -z "$ACCESS_TOKEN" ]; then
    echo "Error: ACCESS_TOKEN is not set. Please check the login script."
    exit 1
fi

# Case statement for handling different operations
case "$operation" in
    "import")
        # Ensure the import file exists
        if [ ! -f "$argument" ]; then
            echo "Error: Import file '$argument' not found."
            exit 1
        fi

        # Read data from the import file
        data=$(cat "$argument")

        # Send import request, capture the HTTP status and response
        response=$(curl --location --write-out "%{http_code}" --silent --output /tmp/curl_response \
            --header 'Content-Type: application/json' \
            --header "Authorization: Bearer $ACCESS_TOKEN" \
            --data "$data" 'http://localhost:8000/calibration/import/')

        # Extract HTTP status and response
        http_status=$(tail -n1 <<< "$response")
        response=$([[ -f /tmp/curl_response ]] && cat /tmp/curl_response || echo "")

        check_http_error "$http_status" "$response"

        # Extract the calibration_run_id from the response
        calibration_run_id=$(echo "$response" | jq -r '.calibration_run_id' 2>/dev/null)
        if [ -n "$geopackage_file" ]; then upload_geopackage_data "$geopackage_file" "$calibration_run_id" || exit 1; fi
        if [ -n "$observational_file" ]; then upload_observational_data "$observational_file" "$calibration_run_id" || exit 1; fi
        if [ -n "$forcing_dir" ]; then upload_forcing_data "$forcing_dir" "$calibration_run_id" || exit 1; fi
        if [ "$run_after_import" = true ]; then run_job "$calibration_run_id" || exit 1; fi
        rm -f /tmp/curl_response
        ;;

    "export")
        if [ -z "$argument" ]; then echo "Error: Calibration run ID required for export."; exit 1; fi
        response=$(curl --location --write-out "%{http_code}" --silent --output /tmp/curl_response \
            --header 'Content-Type: application/json' \
            --header "Authorization: Bearer $ACCESS_TOKEN" \
            "http://localhost:8000/calibration/export/?calibration_run_id=$argument")

        # Extract HTTP status and response
        http_status=$(tail -n1 <<< "$response")
        response=$([[ -f /tmp/curl_response ]] && cat /tmp/curl_response || echo "")

        check_http_error "$http_status" "$response"

        # Determine whether output is a directory or file
        if [ -n "$output" ]; then
            if [ -d "$output" ]; then
                output_path="$output/calibration_run_$argument.json"  # Use default filename in specified directory
            else
                output_path="$output"  # Use specified file path
            fi
        else
            output_path="calibration_run_$argument.json"  # Default filename if output not specified
        fi

        # Save the response to the file
        if echo "$response" | jq . --indent 3 > "$output_path"; then
            echo "Exported calibration run data to $output_path"
        else
            echo "Error saving export response to file."
            exit 1
        fi

        # Clean up
        rm -f /tmp/curl_response
        ;;

    "run")
        if [ -z "$argument" ]; then echo "Error: Calibration run ID required to run job."; exit 1; fi
        run_job "$argument"
        ;;

    "delete")
        if [ -z "$argument" ]; then echo "Error: Calibration run ID required to delete job."; exit 1; fi
        delete_job "$argument"
        ;;

    "cancel")
        if [ -z "$argument" ]; then echo "Error: Calibration run ID required to cancel job."; exit 1; fi
        cancel_job "$argument"
        ;;

    *)
        echo "Invalid operation: $operation"
        print_usage
        ;;
esac
