#! /bin/bash

# Get the directory of the script
SCRIPT_DIR="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"

# Source environment variables
source "$SCRIPT_DIR/cerfserver.env"

# Use the same directory variable for cerfServer
cerfServer="$SCRIPT_DIR"

# Redirect stdout and stderr to two log files and the console
mkdir -p run-logs
LOGFILE_DEV="run-logs/ngencerf_dev.log"
LOGFILE_PROD="run-logs/ngencerf_prod.log"

# Log initial message to both files only
printf "\n------- Server starting at %s --------\n" "$(date)" | tee -a "$LOGFILE_DEV" "$LOGFILE_PROD"

exec > >(tee -a "$LOGFILE_DEV" | tee -a "$LOGFILE_PROD") 2>&1

# Check for the --load-static flag
LOAD_STATIC_DATA=false
for arg in "$@"; do
  case $arg in
    --load-static)
    LOAD_STATIC_DATA=true
    shift
    ;;
  esac
done

# Function to generate git_info.properties
# Should parallel similar functionality in the Dockerfile
generate_git_info() {
    GIT_INFO_PATH=$cerfServer/git_info.json
    repo_url=$(git config --get remote.origin.url)
    # Extract the repo name (everything after the last slash) and remove any trailing .git
    key=${repo_url##*/}
    key=${key%.git}
    echo "Generating git_info.json..."
    jq -n \
        --arg commit_hash "$(git rev-parse HEAD)" \
        --arg branch "$(git rev-parse --abbrev-ref HEAD)" \
        --arg tags "$(git tag --points-at HEAD | tr '\n' ' ')" \
        --arg author "$(git log -1 --pretty=format:'%an')" \
        --arg commit_date "$(date -u -d @"$(git log -1 --pretty=format:'%ct')" +'%Y-%m-%d %H:%M:%S UTC')" \
        --arg message "$(git log -1 --pretty=format:'%s' | tr '\n' ';')" \
        --arg build_date "$(date -u +'%Y-%m-%d %H:%M:%S UTC')" \
        "{\"${key}\": {commit_hash: \$commit_hash, branch: \$branch, tags: \$tags, author: \$author, commit_date: \$commit_date, message: \$message, build_date: \$build_date}}" \
        > "$GIT_INFO_PATH"
    echo "git_info.json created at $GIT_INFO_PATH"
}

if [ "${CERF_VENV}" != "Docker" ]; then
    # Docker takes care of installing dependencies in the Dockerfile
    if [ -n "${CERF_VENV}" ]; then
       # shellcheck disable=SC1090
       source "$cerfServer/${CERF_VENV}/bin/activate"

       # Install all requirements
       echo "Installing requirements.txt"
       pip install --upgrade pip
       pip install -r requirements.txt

       # Doing a pip install with requirements.txt does not reliably pick up changes to the ngen-cal repo, so we have to force a re-install every time
       NGEN_CAL_BRANCH='development'
       NGEN_FORCING_BRANCH='development'
#       NGEN_CAL_BRANCH='129809ac'
#       NGEN_FORCING_BRANCH='xxxx'
       echo
       echo "Installing createInput"
       if pip show "createInput" > /dev/null 2>&1; then
           # Package is installed, reinstall without dependencies
           pip install --force-reinstall --no-deps -e "git+https://gitlab.sh.nextgenwaterprediction.com/NGWPC/nwm-ngen/ngen-cal.git@${NGEN_CAL_BRANCH}#egg=createInput&subdirectory=python/createInput"
       else
           # Package is not installed, install with dependencies
           pip install -e "git+https://gitlab.sh.nextgenwaterprediction.com/NGWPC/nwm-ngen/ngen-cal.git@${NGEN_CAL_BRANCH}#egg=createInput&subdirectory=python/createInput"
       fi

       echo
       echo "Installing swe_mapping"
       if pip show "swe_mapping" > /dev/null 2>&1; then
           # Package is installed, reinstall without dependencies
           pip install --force-reinstall --no-deps -e "git+https://gitlab.sh.nextgenwaterprediction.com/NGWPC/nwm-ngen/ngen-forcing.git@${NGEN_FORCING_BRANCH}#egg=swe_processing&subdirectory=swe_processing"
       else
           # Package is not installed, install with dependencies
           pip install -e "git+https://gitlab.sh.nextgenwaterprediction.com/NGWPC/nwm-ngen/ngen-forcing.git@${NGEN_FORCING_BRANCH}#egg=swe_processing&subdirectory=swe_processing"
       fi

       generate_git_info
    else
       echo "CERF_VENV is not set. Please set the virtual environment variable."
       exit 1
    fi
fi

# Function to run Django management commands without logging redirection
run_manage_command() {
    echo "Running $*"
    # Temporarily disable redirection
    exec >/dev/tty 2>/dev/tty

    python3 manage.py "$@"

    # Restore redirection
    exec > >(tee -a "$LOGFILE_DEV" | tee -a "$LOGFILE_PROD") 2>&1
}

# Run management commands with proper logging
run_manage_command migrate

# Only load static data if the flag is provided or the CERF_LOAD_STATIC_DATA file doesn't exist
if [ "$LOAD_STATIC_DATA" = true ] || [ ! -f "${CERF_LOAD_STATIC_DATA}" ]; then
    echo
    echo "Loading ngenCERF static data"

    run_manage_command createsuperuser_docker --noinput --password admin --email admin@nextgenwaterprediction.com
    echo
    run_manage_command init_sql
    echo
    run_manage_command init_gages

    touch "${CERF_LOAD_STATIC_DATA}"
else
    # Run this every time, since sometimes there are updates and it is very quick
    run_manage_command init_sql
fi

echo
run_manage_command pre_start

echo
echo "Starting server"

# Restore original stdout and stderr before starting the server
exec >/dev/tty 2>/dev/tty

python3 "$cerfServer"/manage.py runserver 0.0.0.0:8000 --noreload

if [ -n "${CERF_VENV}" ]; then
    deactivate
fi
