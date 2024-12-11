#! /bin/bash

# Run ngenCerf outside of Pycharm

source "./cerfserver.env"

cerfServer="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"

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

if [ "${CERF_VENV}" != "Docker" ]; then
    if [ -n "${CERF_VENV}" ]; then
       # shellcheck disable=SC1090
       source "$cerfServer/${CERF_VENV}/bin/activate"

       # Install all requirements
       echo "Installing requirements.txt"
       pip install -r requirements.txt
       echo

      echo "Installing createInput"
       # Doing a  pip install with requirements.txt does not reliably pick up changes to the ngen-cal repo, so we have to force a re-install every time
#       NGEN_CAL_BRANCH='development'
       NGEN_CAL_BRANCH='129809ac'
       if pip show "createInput" > /dev/null 2>&1; then
           # Package is installed, reinstall without dependencies
           pip install --force-reinstall --no-deps -e "git+https://gitlab.sh.nextgenwaterprediction.com/NGWPC/nwm-ngen/ngen-cal.git@${NGEN_CAL_BRANCH}#egg=createInput&subdirectory=python/createInput"
       else
           # Package is not installed, install with dependencies
           pip install -e "git+https://gitlab.sh.nextgenwaterprediction.com/NGWPC/nwm-ngen/ngen-cal.git@${NGEN_CAL_BRANCH}#egg=createInput&subdirectory=python/createInput"
       fi
    else
       echo "CERF_VENV is not set. Please set the virtual environment variable."
       exit 1
    fi
fi

echo
echo "Running migrate"
python3 manage.py migrate

# Only load static data if the flag is provided or the CERF_LOAD_STATIC_DATA file doesn't exist
if [ "$LOAD_STATIC_DATA" = true ] || [ ! -f "${CERF_LOAD_STATIC_DATA}" ]; then
    echo
    echo "Loading ngenCERF static data"

    python3 manage.py createsuperuser_docker --noinput \
        --password admin \
        --email admin@nextgenwaterprediction.com
    echo
    echo "Calling init_sql"
    python3 manage.py init_sql
    echo
    echo "Calling init_gages"
    python3 manage.py init_gages

    touch "${CERF_LOAD_STATIC_DATA}"
else
    # Run this every time, since sometimes there are updates and it is very quick
    python3 manage.py init_sql
fi

echo
echo "Running pre_start"
python3 "$cerfServer"/manage.py pre_start

echo
echo "Starting server"
python3 "$cerfServer"/manage.py runserver 0.0.0.0:8000 --noreload

if [ -n "${CERF_VENV}" ]; then
    deactivate
fi
