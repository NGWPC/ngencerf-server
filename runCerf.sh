#! /bin/bash

# Run ngenCerf outside of Pycharm

source "./cerfserver.env"


cerfServer="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"

if [ -n "${CERF_VENV}" ] ; then
    # shellcheck disable=SC1090
    source "$cerfServer/${CERF_VENV}/bin/activate"
else
    echo "CERF_VENV is not set.  PLease set the virtual environment variable."
fi

echo
echo "Running migrate"
python3 manage.py migrate

if [ ! -f "${CERF_LOAD_STATIC_DATA}" ] ; then
    echo
    echo "Loading ngenCERF static data"

    python3 manage.py createsuperuser_docker --noinput \
        --username admin \
        --password admin \
        --email admin@nextgenwaterprediction.com
    python3 manage.py init_sql; \
    python3 manage.py init_gages

    touch "${CERF_LOAD_STATIC_DATA}"
fi

echo
echo "Running pre_start"
python3 "$cerfServer"/manage.py pre_start

echo
echo "Starting server"
python3 "$cerfServer"/manage.py runserver 0.0.0.0:8000

if [ -n "${CERF_VENV}" ] ; then
    deactivate
fi
