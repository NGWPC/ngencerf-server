#!/bin/bash

# Function to print usage
print_usage() {
    echo "Usage: $0 [import|export] <file|calibration_run_id> [keyword arguments]"
    echo "  import <file> : Import the provided JSON file."
    echo "  export <calibration_run_id> : Export the JSON data for the given calibration_run_id."
    echo "  Optional keyword arguments:"
    echo "      observational_data_filepath=<file path>"
    echo "      forcing_data_dir=<directory path>"
    echo "      geopackage_filepath=<file path>"
    echo "      output=<directory or file path>"
    echo "      run_after_import=true|false"
    exit 1
}

# Function to handle the geopackage upload
upload_geopackage_data() {
    local geopackage_filepath=$1
    local calibration_run_id=$2

    echo "Uploading geopackage: $geopackage_filepath for calibration_run_id: $calibration_run_id"

    # Send upload_geopackage request, capture the HTTP status and response
    response=$(curl --location --write-out "%{http_code}" --silent --output /tmp/curl_response \
    --header 'Content-Type: multipart/form-data' \
    --header "Authorization: Bearer $ACCESS_TOKEN" \
    --form "geopackage_file=@$geopackage_filepath" \
    --form "calibration_run_id=$calibration_run_id" \
    "http://localhost:8000/calibration/upload_geopackage_data/")

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

    # Print the response
    if ! echo "$response" | jq . --indent 3 2>/dev/null; then
       echo "Error parsing response."
    fi

    # Clean up the temporary file
    rm -f /tmp/curl_response
}

# Function to handle the forcing upload
upload_forcing_data() {
    local forcing_data_dir=$1
    local calibration_run_id=$2

    echo "Uploading forcing data from directory: '$forcing_data_dir' for calibration_run_id: $calibration_run_id"

    # Initialize an array to hold all the --form arguments
    form_files=()

    # Add the files from the directory to the form data
    for file in "$forcing_data_dir"/*; do
        if [ -f "$file" ]; then
            form_files+=("--form" "forcing_files[]=@$file")
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

    # Print the response
    if ! echo "$response" | jq . --indent 3 2>/dev/null; then
       echo "Error parsing response."
    fi

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
observational_data_filepath=""
forcing_data_dir=""
geopackage_filepath=""
output=""
run_after_import=false

# Parse the keyword arguments
for arg in "$@"; do
    case $arg in
        observational_data_filepath=*)
            observational_data_filepath="${arg#*=}"
            ;;
        forcing_data_dir=*)
            forcing_data_dir="${arg#*=}"
            ;;
        geopackage_filepath=*)
            geopackage_filepath="${arg#*=}"
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

echo checking output
echo [ -f "$output" ]
if [ "$operation" == "import" ] && [ -f "$output" ]; then
    echo "Error; The output option is not valid for import."f
    exit 1
fi

if [ "$operation" == "output" ] && ([ -f "observational_data_filepath" ] || [ -f "forcing_data_dir" ] || [ -f "geopackage_filepath" ] ); then
    echo "Error: Upload files can only be specified for import"
    exit 1
fi

if [ "$operation" == "output" ] && [ -f "run_after_import" ]; then
    echo "Error: The run_after_import option is only valid for import."
    exit 1
fi

if [ -n "$observational_data_filepath" ]; then
    if [ ! -f "$observational_data_filepath" ]; then
        echo "Error: Observational file '$observational_data_filepath' not found."
        exit 1
    elif [[ "$observational_data_filepath" != *.csv ]]; then
        echo "Error: Observational file must have a .csv extension."
        exit 1
    fi
fi

if [ -n "$geopackage_filepath" ]; then
    if [ ! -f "$geopackage_filepath" ]; then
        echo "Error: Geopackage file '$geopackage_filepath' not found."
        exit 1
    elif [[ "$geopackage_filepath" != *.gpkg ]]; then
        echo "Error: Geopackage file must have a .gpkg extension."
        exit 1
    fi
fi

if [ -n "$forcing_data_dir" ]; then
    if [ ! -d "$forcing_data_dir" ]; then
        echo "Error: Forcing data directory '$forcing_data_dir' not found."
        exit 1
    fi
    for file in "$forcing_data_dir"/*; do
        if [ ! -f "$file" ]; then
            echo "Error: No files found in the forcing data directory, '$forcing_data_dir'."
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

    check_http_error "$http_status" "$response"

    # Print the response
    if ! echo "$response" | jq . --indent 3 2>/dev/null; then
       echo "Error parsing response."
    fi

    calibration_run_id=$(echo "$response" | jq -r '.calibration_run_id' 2>/dev/null)

    if [ -n "$geopackage_filepath" ]; then
        upload_geopackage_data "$geopackage_filepath" "$calibration_run_id"
    fi

    if [ -n "$observational_data_filepath" ]; then
        upload_observational_data "$observational_data_filepath" "$calibration_run_id"
    fi

    if [ -n "$forcing_data_dir" ]; then
        upload_forcing_data "$forcing_data_dir" "$calibration_run_id"
    fi

    if [ "$run_after_import" = true ]; then
        run_job "$calibration_run_id"
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

else
    echo You must enter 'import' or 'export'
    echo
    print_usage
fi
