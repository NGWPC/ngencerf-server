#! /bin/bash

# Get the directory of the script
SCRIPT_DIR="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"

# Source environment variables
source "$SCRIPT_DIR/cerfserver.env"

# Use the same directory variable for cerfServer
cerfServer="$SCRIPT_DIR"

# Redirect stdout and stderr to a log file and the console
mkdir -p "$cerfServer/logs"
LOGFILE_DEV="$cerfServer/logs/ngencerf_dev.log"
printf "\n------- Server starting at %s --------\n" "$(date)" | tee -a "$LOGFILE_DEV"
exec > >(tee -a "$LOGFILE_DEV") 2>&1

#=======================================================================
# Function: ensure_virtualenv
#   - If CERF_VENV is empty or “Docker”, do nothing
#   - If the directory "$cerfServer/$CERF_VENV" does not exist, create it.
#   - Activate that venv so “python3” and “pip” later refer to the venv.
#=======================================================================
ensure_virtualenv() {
    if [ -n "${CERF_VENV}" ] && [ "${CERF_VENV}" != "Docker" ]; then
        VENV_PATH="$cerfServer/${CERF_VENV}"

        if [ ! -d "$VENV_PATH" ]; then
            echo "Virtual environment not found at $VENV_PATH. Creating it..."
            python3.11 -m venv "$VENV_PATH"
        fi

        # shellcheck disable=SC1090
        source "$VENV_PATH/bin/activate"
    fi
}

# Redirect stdout and stderr to LOGFILE_DEV
exec > >(tee -a "$LOGFILE_DEV") 2>&1

#=======================================================================
# Function: run_manage_command
#   - Temporarily “un-redirects” stdout/stderr so you can see Django output.
#   - Runs “python $SCRIPT_DIR/manage.py <args…>” (which will use the venv’s python).
#   - Then re-redirects stdout/stderr back to the logfile.
#=======================================================================
run_manage_command() {
    echo "Running manage.py $*"
    # Temporarily disable redirection
    exec >/dev/tty 2>/dev/tty

    python "$SCRIPT_DIR/manage.py" "$@"

    # Restore redirection
    exec > >(tee -a "$LOGFILE_DEV") 2>&1
}

#=======================================================================
# Special case: if the first argument is “manage”, just run manage.py <args>
#=======================================================================
if [ "$1" == "manage" ]; then
    shift
    ensure_virtualenv  # Activates and creates virtualenv if needed
    run_manage_command "$@"
    exit $?
fi

#=======================================================================
# Parse “--load-static” flag (if present), then shift it away
#=======================================================================
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
    repo_url=$(git config --get remote.origin.url)
    # Extract the repo name (everything after the last slash) and remove any trailing .git
    key=${repo_url##*/}
    key=${key%.git}
    GIT_INFO_PATH=$SCRIPT_DIR/${key}_git_info.json
    echo "Generating ${GIT_INFO_PATH}..."
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
    echo "Generated $GIT_INFO_PATH"
}

if [ "${CERF_VENV}" != "Docker" ]; then
    # Docker takes care of installing dependencies in the Dockerfile
    if [ -n "${CERF_VENV}" ]; then
        ensure_virtualenv  # Activates and creates virtualenv if needed

        # Install all requirements
        echo "Upgrading pip"
        pip install --upgrade pip
        pip --version
        echo "Installing requirements.txt"
        pip install -r "$SCRIPT_DIR/requirements.txt"

        # Doing a pip install with requirements.txt does not reliably pick up changes to the other repos, so we have to force a re-install every time
        MSWM_BRANCH='development'
        NGEN_FORCING_BRANCH='development'
#       MSWM_BRANCH='129809ac'
#       NGEN_FORCING_BRANCH='xxxx'
        echo
        echo "Installing mswm"
        if pip show "mswm" > /dev/null 2>&1; then
            # Package is installed, reinstall without dependencies
            pip install --force-reinstall --no-deps --no-cache-dir "git+https://gitlab.sh.nextgenwaterprediction.com/NGWPC/nwm-ngen/mswm.git@${MSWM_BRANCH}#egg=mswm"
        else
            # Package is not installed, install with dependencies
            pip install "git+https://gitlab.sh.nextgenwaterprediction.com/NGWPC/nwm-ngen/mswm.git@${MSWM_BRANCH}#egg=mswm"

        fi

        echo
        echo "Installing swe_mapping"
        if pip show "swe_mapping" > /dev/null 2>&1; then
            # Package is installed, reinstall without dependencies
            pip install --force-reinstall --no-deps --no-cache-dir "git+https://gitlab.sh.nextgenwaterprediction.com/NGWPC/nwm-ngen/ngen-forcing.git@${NGEN_FORCING_BRANCH}#egg=swe_processing&subdirectory=swe_processing"
        else
            # Package is not installed, install with dependencies
            pip install "git+https://gitlab.sh.nextgenwaterprediction.com/NGWPC/nwm-ngen/ngen-forcing.git@${NGEN_FORCING_BRANCH}#egg=swe_processing&subdirectory=swe_processing"
        fi

        generate_git_info
    else
        echo "CERF_VENV is not set. Please set the virtual environment variable."
        exit 1
    fi
fi

# Run management commands with proper logging
if ! run_manage_command migrate; then
  echo "migrate failed"
  exit 1
fi

# Only load static data if the flag is provided or the CERF_LOAD_STATIC_DATA file doesn't exist
if [ "$LOAD_STATIC_DATA" = true ] || [ ! -f "${CERF_LOAD_STATIC_DATA}" ]; then
    echo
    echo "Loading ngenCERF static data"

    run_manage_command createsuperuser_docker --noinput --password admin --email admin@nextgenwaterprediction.com
    echo
    if ! run_manage_command init_sql; then
      echo "init_sql failed"
      exit 1
    fi

    echo
    if ! run_manage_command init_gages; then
      echo "init_gages failed"
      exit 1
    fi

    touch "${CERF_LOAD_STATIC_DATA}"
else
    # Run this every time, since sometimes there are updates and it is very quick
    if ! run_manage_command init_sql; then
      echo "init_sql failed"
      exit 1
    fi
fi

echo
if ! run_manage_command pre_start; then
  echo "pre_start failed"
  exit 1
fi

echo
echo "Starting server"

# Restore original stdout and stderr before starting the server
exec >/dev/tty 2>/dev/tty

python "$cerfServer"/manage.py runserver 0.0.0.0:8000 --noreload

if [ -n "${CERF_VENV}" ]; then
    deactivate
fi
