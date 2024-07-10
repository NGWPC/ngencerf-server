# Run ngenCerf outside of Pycharm

cerfServer=~/projects/cerfServer/

source $cerfServer/.venv/bin/activate
$cerfServer/manage.py runserver localhost:8000

deactivate
