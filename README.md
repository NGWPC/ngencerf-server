# Initial Set-up of database

Start up `manage.py`.  
Assuming `$cerfServer` is the root directory of the project
```
$ source $cerfServer/.venv/bin/activate
$ $cerfServer/manage.py
```
Run `migrate` to create all the tables
```
manage.py@cerfServer> migrate
```

Create a superuser called `admin` that is used for initializing 
the static tables. 

```
manage.py@cerfServer> createsuperuser
```
Run `init_sql` and `init_gages` to initialize the static tables
```
manage.py@cerfServer> init_sql
manage.py@cerfServer> init_gages
```

# Updating
After pulling the latest updates from the repo, you should run `migrate` 
in case there have been any database changes
```
manage.py@cerfServer> migrate
```

# Running the server
To run the server outside of Pycharm, use `runCerf.sh`

Running the server in production is likely very different, 
but it's important to run `pre_start.py` from `manage.py` before the server starts, 
in order to clean up any  Calibrations or Validations that were running at the time the server went down.

# Installing ngen and ngen-cal

Follow the instructions at https://confluence.nextgenwaterprediction.com/display/NGWPC/Build+ngen-cal+and+ngen+from+GitLab
* Create the ngen-cal virtual environment.  This directory goes into `settings.py` as `NGEN_CAL_VENV`
* Clone ngen-cal from Gitlab.  This directory goes into `settings.py` as `NGEN_CAL_REPO_ROOT`
* Follow instructions for installing ngen-cal
* Clone ngen from Gitlab.  This directory goes into `settings.py` as `NGEN_REPO_ROOT`
* Follow instructions for installing ngen
* It is **not** necessary to create the ROOT_DIR_RUN_NGEN_CAL directory or to run the script that creates symbolic links in that directory
* Define a directory in `settings.py` where all the ngen-cal runs will live called `NGEN_CAL_RUN_DIR`



