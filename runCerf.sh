# Run ngenCerf outside of Pycharm

cerfServer=~/projects/cerfServer/

source $cerfServer/.venv/bin/activate

echo
echo Running pre_start
$cerfServer/manage.py pre_start

echo
echo Starting server
$cerfServer/manage.py runserver localhost:8000

deactivate
