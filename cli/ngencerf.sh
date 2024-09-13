#!/bin/bash

# Function to print usage
print_usage() {
    echo "Usage: $0 [import|export|run] <file|calibration_run_id> [keyword arguments]"
    echo ""
    echo "  Commands:"
    echo "    import <file> : Import the provided JSON file."
    echo "        Arguments:"
    echo "          observational_file=<file path>    (optional) : Path to the observational data file (CSV format)."
    echo "          forcing_dir=<directory path>      (optional) : Path to the directory containing forcing data (CSV files)."
    echo "          geopackage_file=<file path>       (optional) : Path to the geopackage file (GPKG format)."
    echo "          run_after_import=true|false       (optional) : Whether to run the calibration job after import (default: false)."
    echo ""
    echo "    export <calibration_run_id> : Export the JSON data for the given calibration_run_id."
    echo "        Arguments:"
    echo "          output=<directory or file path>   (optional) : Path to save the exported file (default filename used if a directory is provided)."
    echo ""
    echo "    run <calibration_run_id> : Run the calibration_run_id job."
    echo "        Arguments:"
    echo "          <None>"
    echo ""
    echo "  Example usage:"
    echo "    $0 import data.json observational_file=obs.csv forcing_dir=forcing run_after_import=true"
    echo "    $0 export 123 output=/path/to/exported_data.json"
    echo "    $0 run 123"
    exit 1
}


# Function to handle the geopackage upload
upload_geopackage_data() {
    local geopackage_file=$1
    local calibration_run_id=$2

    echo "Uploading geopackage: $geopackage_file for calibration_run_id: $calibration_run_id"

    # Send upload_geopackage request, capture the HTTP status and response
    response=$(curl --location --write-out "%{http_code}" --silent --output /tmp/curl_response \
    --header 'Content-Type: multipart/form-data' \
    --header "Authorization: Bearer $ACCESS_TOKEN" \
    --form "return_geopackage_url=false" \
    --form "geopackage_file=@$geopackage_file" \
    --form "calibration_run_id=$calibration_run_id" \
    "http://localhost:8000/calibration/upload_geopackage_data/")

    # Extract HTTP status and response
    http_status=$(tail -n1 <<< "$response")
    response=$(cat /tmp/curl_response)

    check_http_error "$http_status" "$response"

    # Extract the status field
    # status=$(echo "$response" | jq -r '.status')

    # Print the full response
    echo "$response" | jq --indent 3

    # Clean up the temporary file
    rm -f /tmp/curl_response
}

# Function to handle the observational upload
upload_observational_data() {
    local observational_filepath=$1
    local calibration_run_id=$2

    echo "Uploading observational data: $observational_filepath for calibration_run_id: $calibration_run_id"

    # Send upload_observational request, capture the HTTP status and response
    response=$(curl --location --write-out "%{http_code}" --silent --output /tmp/curl_response \
    --header 'Content-Type: multipart/form-data' \
    --header "Authorization: Bearer $ACCESS_TOKEN" \
    --form "observational_file=@$observational_filepath" \
    --form "calibration_run_id=$calibration_run_id" \
    "http://localhost:8000/calibration/upload_observational_data/")

    # Extract HTTP status and response
    http_status=$(tail -n1 <<< "$response")
    response=$(cat /tmp/curl_response)

    check_http_error "$http_status" "$response"

    # Extract the status field
    # status=$(echo "$response" | jq -r '.status')

    # Print the full response
    echo "$response" | jq --indent 3

    # Clean up the temporary file
    rm -f /tmp/curl_response
}

# Function to handle the forcing upload
upload_forcing_data() {
    local forcing_dir=$1
    local calibration_run_id=$2

    echo "Uploading forcing data from directory: '$forcing_dir' for calibration_run_id: $calibration_run_id"

    # Initialize an array to hold all the --form arguments
    form_files=()

    # Add the files from the directory to the form data
    for file in "$forcing_dir"/*; do
        if [ -f "$file" ]; then
            form_files+=("--form" "forcing_files=@$file")
        fi
    done

    if [ ${#form_files[@]} -eq 0 ]; then
        echo "Error: No files found in the forcing data directory."
        exit 1
    fi

    # Send upload_forcing request, capture the HTTP status and response
    response=$(curl --location --write-out "%{http_code}" --silent --output /tmp/curl_response \
    --header 'Content-Type: multipart/form-data' \
    --header "Authorization: Bearer $ACCESS_TOKEN" \
    "${form_files[@]}" \
    --form "calibration_run_id=$calibration_run_id" \
    "http://localhost:8000/calibration/upload_forcing_data/")

    # Extract HTTP status and response
    http_status=$(tail -n1 <<< "$response")
    response=$(cat /tmp/curl_response)

    check_http_error "$http_status" "$response"

    # Extract the status field
    # status=$(echo "$response" | jq -r '.status')

    # Print the full response
    echo "$response" | jq --indent 3

    # Clean up the temporary file
    rm -f /tmp/curl_response
}


# Function to run the job
run_job() {
    local calibration_run_id=$1

    echo "Submitting calibration run job $calibration_run_id"

    # Prepare the JSON payload
    json_payload=$(jq -n --arg calibration_run_id "$calibration_run_id" '{calibration_run_id: $calibration_run_id}')

    response=$(curl --location --write-out "%{http_code}" --silent --output /tmp/curl_response \
    --header 'Content-Type: application/json'\
    --header "Authorization: Bearer $ACCESS_TOKEN" \
    --data "$json_payload" \
    "http://localhost:8000/calibration/run_calibration/")

    # Extract HTTP status and response
    http_status=$(tail -n1 <<< "$response")
    response=$(cat /tmp/curl_response)

    check_http_error "$http_status" "$response"

    # Print the response
    if ! echo "$response" | jq . --indent 3 2>/dev/null; then
       echo "Error parsing response."
    fi

    # Clean up the temporary file
    rm -f /tmp/curl_response
}


# Check if operation and argument are provided
if [ -z "$1" ] || [ -z "$2" ]; then
    print_usage
fi

# Set operation and argument
operation="$1"
argument="$2"
shift 2  # Shift past the first two positional arguments

# Initialize variables for optional keyword arguments
observational_file=""
forcing_dir=""
geopackage_file=""
output=""
run_after_import=false

# Parse the keyword arguments
for arg in "$@"; do
    case $arg in
        observational_file=*)
            observational_file="${arg#*=}"
            ;;
        forcing_dir=*)
            forcing_dir="${arg#*=}"
            ;;
        geopackage_file=*)
            geopackage_file="${arg#*=}"
            ;;
        output=*)
            output="${arg#*=}"
            ;;
        run_after_import=*)
        run_after_import="${arg#*=}"
            ;;
        *)
            echo "Unknown argument: $arg"
            print_usage
            ;;
    esac
done

# Ensure run_after_import is either true or false
if [[ "$run_after_import" != "true" && "$run_after_import" != "false" ]]; then
    echo "Error: run_after_import must be either 'true' or 'false'."
    exit 1
fi

# Ensure all specified files and directories exist before proceeding
if [ "$operation" == "import" ] && [ ! -f "$argument" ]; then
    echo "Error: Import file '$argument' not found."
    exit 1
fi

if [ "$operation" == "import" ] && [ -f "$output" ]; then
    echo "Error: The output option is not valid for import."f
    exit 1
fi

if [ "$operation" == "output" ] && { [ -f "$observational_file" ] || [ -f "$forcing_dir" ] || [ -f "$geopackage_file" ]; }; then
    echo "Error: Upload files can only be specified for import"
    exit 1
fi


if [ "$operation" == "output" ] && [ -f "run_after_import" ]; then
    echo "Error: The run_after_import option is only valid for import."
    exit 1
fi

if [ -n "$observational_file" ]; then
    if [ ! -f "$observational_file" ]; then
        echo "Error: Observational file '$observational_file' not found."
        exit 1
    elif [[ "$observational_file" != *.csv ]]; then
        echo "Error: Observational file must have a .csv extension."
        exit 1
    fi
fi

if [ -n "$geopackage_file" ]; then
    if [ ! -f "$geopackage_file" ]; then
        echo "Error: Geopackage file '$geopackage_file' not found."
        exit 1
    elif [[ "$geopackage_file" != *.gpkg ]]; then
        echo "Error: Geopackage file must have a .gpkg extension."
        exit 1
    fi
fi

if [ -n "$forcing_dir" ]; then
    if [ ! -d "$forcing_dir" ]; then
        echo "Error: Forcing data directory '$forcing_dir' not found."
        exit 1
    fi
    for file in "$forcing_dir"/*; do
        if [ ! -f "$file" ]; then
            echo "Error: No files found in the forcing data directory, '$forcing_dir'."
            exit 1
        elif [[ "$file" != *.csv ]]; then
            echo "Error: All forcing files must have a .csv extension. Invalid file: $file"
            exit 1
        fi
    done
fi


source ./ngen_login.sh

# Check if ACCESS_TOKEN is set
if [ -z "$ACCESS_TOKEN" ]; then
    echo "Error: ACCESS_TOKEN is not set. Please check the login script."
    exit 1
fi

# Function to check for HTTP errors
check_http_error() {
    http_status=$1
    response=$2
    if [ "$http_status" -eq 000 ]; then
        echo "Error: Could not connect to the server."
        exit 1
    elif [ "$http_status" -eq 400 ]; then
        echo "Server returned HTTP 400 Bad Request. Response:"
        echo "$response" | jq --indent 3 # Print the actual server response
        rm -f /tmp/curl_response  # Clean up the temp file
        exit 1
    elif [ "$http_status" -ne 200 ]; then
        echo "Error: Server returned HTTP status code $http_status."
        rm -f /tmp/curl_response  # Clean up the temp file
        exit 1
    fi
}

# Handle import operation
if [ "$operation" == "import" ]; then
    # Read data from file
    data=$(cat "$argument")

    # Send import request, capture the HTTP status and response
    response=$(curl --location --write-out "%{http_code}" --silent --output /tmp/curl_response \
    --header 'Content-Type: application/json' \
    --header "Authorization: Bearer $ACCESS_TOKEN" \
    --data "$data" 'http://localhost:8000/calibration/import/')

    # Extract HTTP status and response
    http_status=$(tail -n1 <<< "$response")

    if [ -f /tmp/curl_response ]; then
       response=$(cat /tmp/curl_response)
    else
       response=""
    fi

    # Check if there was an HTTP error, and exit if so
    check_http_error "$http_status" "$response"

    # Print the response
    if ! echo "$response" | jq . --indent 3 2>/dev/null; then
       echo "Error parsing response."
       exit 1
    fi

    # Extract the calibration_run_id from the response
    calibration_run_id=$(echo "$response" | jq -r '.calibration_run_id' 2>/dev/null)

    # Upload geopackage data (exit if there's an error)
    if [ -n "$geopackage_file" ]; then
        upload_geopackage_data "$geopackage_file" "$calibration_run_id" || exit 1
    fi

    # Upload observational data (exit if there's an error)
    if [ -n "$observational_file" ]; then
        upload_observational_data "$observational_file" "$calibration_run_id" || exit 1
    fi

    # Upload forcing data (exit if there's an error)
    if [ -n "$forcing_dir" ]; then
        upload_forcing_data "$forcing_dir" "$calibration_run_id" || exit 1
    fi

    # Run the calibration job after import if requested (exit if there's an error)
    if [ "$run_after_import" = true ]; then
        run_job "$calibration_run_id" || exit 1
    fi

    # Clean up the temporary file
    rm -f /tmp/curl_response

# Handle export operation
elif [ "$operation" == "export" ]; then
    calibration_run_id="$argument"

    # Send export request, capture the HTTP status and response
    response=$(curl --location --write-out "%{http_code}" --silent --output /tmp/curl_response \
    --header 'Content-Type: application/json' \
    --header "Authorization: Bearer $ACCESS_TOKEN" \
    "http://localhost:8000/calibration/export/?calibration_run_id=$calibration_run_id")

    # Extract HTTP status and response
    http_status=$(tail -n1 <<< "$response")
    response=$(cat /tmp/curl_response)

    check_http_error "$http_status" "$response"

    # Determine if output is a directory or a file
    if [ -z "$output" ]; then
        # If output is not specified, use the default filename
        output="calibration_run_$calibration_run_id.json"
    elif [ -d "$output" ]; then
        # If output is a directory, append the default filename
        output="$output/calibration_run_$calibration_run_id.json"
    fi

    # Save the response to a JSON file
    if ! echo "$response" | jq . --indent 3 > "$output" 2>/dev/null; then
       echo "Error parsing response or saving to file."
    else
       full_path="$(realpath "$output")"
       echo "Exported calibration run data to $full_path"
    fi

    # Clean up the temporary file
    rm -f /tmp/curl_response

elif [ "$operation" == "run" ]; then
    calibration_run_id="$argument"

    run_job "$calibration_run_id"

else
    echo You must enter 'import', 'export' or 'run'
    echo
    print_usage
fi
