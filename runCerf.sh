#! /bin/bash

# Run ngenCerf outside of Pycharm

source ./cerfserver.env

cerfServer="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"

if [ -n "${CERF_VENV}" ] ; then
    source $cerfServer/.venv/bin/activate
fi

echo
echo Running pre_start
python3 $cerfServer/manage.py pre_start

echo
echo Starting server
python3 $cerfServer/manage.py runserver 0.0.0.0:8000

if [ -n "${CERF_VENV}" ] ; then
    deactivate
fi
