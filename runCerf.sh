#! /bin/bash

#=======================================================================
# Script must be sourced for 'activate' mode
#=======================================================================
if [[ "$1" == "activate" ]] && [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "Error: This script must be sourced, not executed, when using the 'activate' command."
    echo "Use 'source ./runCerf.sh activate' to activate the virtual environment."
    exit 1
fi

#=======================================================================
# Resolve script directory and load environment
#=======================================================================
SCRIPT_DIR="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"

# Source environment variables
source "$SCRIPT_DIR/cerfserver.env"

# Use the same directory variable for cerfServer
cerfServer="$SCRIPT_DIR"

#=======================================================================
# Bootstrap logging
#=======================================================================
mkdir -p "$cerfServer/logs"
LOGFILE_DEV="$cerfServer/logs/ngencerf_dev.log"
printf "\n------- Server starting at %s --------\n" "$(date)" | tee -a "$LOGFILE_DEV"
exec > >(tee -a "$LOGFILE_DEV") 2>&1

#=======================================================================
# Function: ensure_virtualenv
#   - If CERF_VENV is empty or “Docker”, do nothing
#   - If the directory "$cerfServer/$CERF_VENV" does not exist, create it
#   - Activate that venv so “python3” and “pip” later refer to the venv
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
        echo "Activated virtual environment at $VENV_PATH"
    fi
}

# Redirect stdout and stderr to LOGFILE_DEV
exec > >(tee -a "$LOGFILE_DEV") 2>&1

#=======================================================================
# Function: run_manage_command
#   - Temporarily un-redirect stdout/stderr for interactive output
#   - Runs “python manage.py <args…>”
#   - Then re-redirects stdout/stderr back to the logfile
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
# Special case: if the first argument is "activate", just activate the venv and return
#=======================================================================
if [ "$1" == "activate" ]; then
    ensure_virtualenv  # Activates and creates virtualenv if needed
    echo "Virtual environment activated. You can now run Python commands in this environment."
    # Return to stop further execution but not exit the terminal
    return 0
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

#=======================================================================
# Function: generate_git_info
#   - Writes <repo>_git_info.json with commit metadata similar to how the Dockerfile does it
#=======================================================================
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

#=======================================================================
# Fingerprint logic for init_gages inputs
#   - Computes a stable SHA256 for init_gages.py + files in gage_data/
#   - Stores/compares to decide whether to re-run init_gages
#=======================================================================
CERF_GAGES_FPRINT="${CERF_GAGES_FPRINT:-$SCRIPT_DIR/.gages_fingerprint}"

# Compute a stable combined SHA256 of init_gages.py + all files in gage_data
compute_gages_fingerprint() {
    set -o pipefail
    local base="$SCRIPT_DIR/calibration/management/commands"
    local files=()

    # Must have init_gages.py
    if [ ! -f "$base/init_gages.py" ]; then
        echo "compute_gages_fingerprint: missing $base/init_gages.py" >&2
        return 1
    fi
    files+=("$base/init_gages.py")

    # Hash everything inside gage_data/ if present (excluding pyc/__pycache__)
    if [ -d "$base/gage_data" ]; then
        while IFS= read -r -d '' f; do
            files+=("$f")
        done < <(find "$base/gage_data" -type f ! -name '*.pyc' ! -path '*/__pycache__/*' -print0 | sort -z)
    fi

    # Hash each file then hash the list into a single digest
    sha256sum "${files[@]}" | sha256sum | awk '{print $1}'
}

store_gages_fingerprint() {
    local fp="$1"
    if [ -z "$fp" ]; then
        echo "store_gages_fingerprint: empty fingerprint" >&2
        return 1
    fi
    echo "$fp" > "$CERF_GAGES_FPRINT"
    echo "Saved gage fingerprint: ${fp:0:12}… -> $CERF_GAGES_FPRINT"
}

#=======================================================================
# Helper: run init_gages and store a provided fingerprint (or recompute if empty)
#=======================================================================
run_init_gages_and_store() {
    local fp="$1"
    if ! run_manage_command init_gages; then
        echo "init_gages failed"
        exit 1
    fi
    if [ -n "$fp" ]; then
        store_gages_fingerprint "$fp"
    else
        if FP_NOW="$(compute_gages_fingerprint)"; then
            store_gages_fingerprint "$FP_NOW"
        else
            echo "Warning: could not compute fingerprint after init_gages"
        fi
    fi
}

#=======================================================================
# Superuser helpers (email is the USERNAME_FIELD)
#=======================================================================
# Function: superuser_exists
#   - Checks if a superuser with the given email already exists.
#   - We have to shell out to Python/Django here because the user model
#     lives in Django (with a custom AUTH_USER_MODEL using email).
#
#   Implementation details:
#     * We run "manage.py shell -c" with a short Python snippet:
#         from django.contrib.auth import get_user_model
#         User = get_user_model()
#         print(User.objects.filter(is_superuser=True, email=...).exists())
#       This prints exactly "True" or "False".
#
#     * Unfortunately, "manage.py shell" also triggers app startup, which
#       prints a bunch of INFO log lines (database info, settings, etc.).
#       Those would otherwise get captured into our Bash variable.
#
#     * To make this robust:
#         --verbosity 0   => suppresses most management command chatter
#         2>/dev/null     => discards stderr noise
#         tail -n 1       => keeps only the *last* line of stdout (our True/False)
#         tr -d "\r"      => strip any stray carriage returns
#
#   Return value:
#     * Echoes a log line with the raw "True"/"False".
#     * Returns 0 (success) if "True", else 1.
#=======================================================================
superuser_exists() {
    local email="$1"
    echo "Checking for superuser [$email]..."
    local out
    out=$(
        DJANGO_EMAIL="$email" \
        python "$SCRIPT_DIR/manage.py" shell -c '
from django.contrib.auth import get_user_model
import os
User = get_user_model()
print(User.objects.filter(is_superuser=True, email=os.environ["DJANGO_EMAIL"]).exists())
' --verbosity 0 2>/dev/null | tail -n 1 | tr -d "\r"
    )
    echo "superuser_exists result: $out"
    [[ "$out" == "True" ]]
}

#=======================================================================
# Function: ensure_superuser
#   - If DJANGO_SUPERUSER_EMAIL/PASSWORD are set and the account is missing, create it.
#   - If vars are missing, log a WARNING and skip creation.
#=======================================================================
ensure_superuser() {
    # Pull from env; set these in cerfserver.env
    local email="${DJANGO_SUPERUSER_EMAIL}"
    local password="${DJANGO_SUPERUSER_PASSWORD}"

    if [ -z "$email" ] || [ -z "$password" ]; then
        echo "WARNING: ensure_superuser: DJANGO_SUPERUSER_EMAIL and/or DJANGO_SUPERUSER_PASSWORD not set."
        echo "WARNING: No superuser will be created automatically. Set these env vars to bootstrap an admin account."
        return 0
    fi

    if superuser_exists "$email"; then
        echo "Superuser [$email] already exists; skipping creation."
        return 0
    fi

    echo "Creating superuser [$email]..."
    DJANGO_SUPERUSER_EMAIL="$email" \
    DJANGO_SUPERUSER_PASSWORD="$password" \
    python "$SCRIPT_DIR/manage.py" createsuperuser --noinput
}

#=======================================================================
# Non-Docker environment setup (packages, deps, git info)
#=======================================================================
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
            pip install --force-reinstall --no-deps --no-cache-dir "git+https://github.com/NGWPC/nwm-msw-mgr.git@${MSWM_BRANCH}#egg=mswm"
        else
            # Package is not installed, install with dependencies
            pip install "git+https://github.com/NGWPC/nwm-msw-mgr.git@${MSWM_BRANCH}#egg=mswm"
        fi

        echo
        echo "Installing swe_mapping"
        if pip show "swe_mapping" > /dev/null 2>&1; then
            # Package is installed, reinstall without dependencies
            pip install --force-reinstall --no-deps --no-cache-dir "git+https://github.com/NGWPC/ngen-forcing.git@${NGEN_FORCING_BRANCH}#egg=swe_processing&subdirectory=swe_processing"
        else
            # Package is not installed, install with dependencies
            pip install "git+https://github.com/NGWPC/ngen-forcing.git@${NGEN_FORCING_BRANCH}#egg=swe_processing&subdirectory=swe_processing"
        fi

        generate_git_info
    else
        echo "CERF_VENV is not set. Please set the virtual environment variable."
        exit 1
    fi
fi

#=======================================================================
# Run migrations, always ensure superuser, then run init_sql once
#=======================================================================
echo
echo --------------------------------------------------------
if ! run_manage_command migrate; then
    echo "migrate failed"
    exit 1
fi

echo
echo --------------------------------------------------------
ensure_superuser
echo

echo
echo --------------------------------------------------------
if ! run_manage_command init_sql; then
    echo "init_sql failed"
    exit 1
fi

#=======================================================================
# Init data handling
#   - '--load-static' or missing marker => unconditional init_gages
#   - Else compare fingerprint and conditionally run init_gages
#=======================================================================
# Only load static data if the flag is provided or the CERF_LOAD_STATIC_DATA file doesn't exist
# load_static is a misnomer.  All we are doing is unconditionally loading the gage data
if [ "$LOAD_STATIC_DATA" = true ] || [ ! -f "${CERF_LOAD_STATIC_DATA}" ]; then
    echo
    echo "Loading ngenCERF gage data"

    echo
    echo --------------------------------------------------------
    # Unconditional run in this branch
    run_init_gages_and_store ""

    touch "${CERF_LOAD_STATIC_DATA}"
else
    echo
    echo --------------------------------------------------------
    # Auto-run init_gages if inputs changed; if hashing fails, run to be safe.
    if FP_NOW="$(compute_gages_fingerprint)"; then
        if [ ! -f "$CERF_GAGES_FPRINT" ]; then
            echo "No prior gage fingerprint found; running init_gages..."
            run_init_gages_and_store "$FP_NOW"
        else
            read -r FP_OLD < "$CERF_GAGES_FPRINT" || FP_OLD=""
            if [ "$FP_NOW" != "$FP_OLD" ]; then
                echo "Gage inputs changed; running init_gages..."
                run_init_gages_and_store "$FP_NOW"
            else
                echo "Gage inputs unchanged; skipping init_gages."
            fi
        fi
    else
        echo "Fingerprinting failed. Running init_gages to be safe…"
        run_init_gages_and_store ""
    fi
fi

#=======================================================================
# Pre-start hook and start server
#=======================================================================
echo
if ! run_manage_command pre_start; then
    echo "pre_start failed"
    exit 1
fi

echo
echo "Starting server"

ASGI_FLAG="${CERF_ASGI:-}" # explicit override
PROD_FLAG="${CERF_PRODUCTION:-}" # general prod indicator

# Restore original stdout and stderr before starting the server
exec >/dev/tty 2>/dev/tty

# use ASGI server if ASGI_FLAG or PROD_FLAG are set
if [ "$ASGI_FLAG" = "1" ] || [ "$PROD_FLAG" = "1" ]; then
    echo "Launching Gunicorn (Uvicorn workers) ASGI server"
    # Default workers: 1 per CPU core * 2 + 1 (common heuristic) but cap small; allow override
    WORKERS=${GUNICORN_WORKERS:-$(python - <<'PY'
import multiprocessing, math
cpu = multiprocessing.cpu_count()
print(min(8, max(2, cpu*2+1)))
PY
)}
    TIMEOUT=${GUNICORN_TIMEOUT:-120}
    BIND_ADDR=${GUNICORN_BIND:-0.0.0.0:8000}
    # --graceful-timeout extra time to finish in-flight requests on restart
    exec gunicorn cerfServer.asgi:application \
            --name ngencerf \
            --workers ${WORKERS} \
            --worker-class uvicorn.workers.UvicornWorker \
            --bind ${BIND_ADDR} \
            --log-level ${GUNICORN_LOG_LEVEL:-info} \
            --timeout ${TIMEOUT} \
            --graceful-timeout ${GUNICORN_GRACEFUL_TIMEOUT:-30} \
            --access-logfile - \
            --error-logfile -
else
    echo "Launching Django development server (runserver)"
    python "$cerfServer"/manage.py runserver 0.0.0.0:8000 --noreload
fi

if [ -n "${CERF_VENV}" ]; then
    deactivate
fi
