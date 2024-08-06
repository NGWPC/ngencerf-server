# Create virtual environment and install dependencies

Connect to the root directory where you cloned the repo, assumed to be `$cerfServer`

**_Important:_**
Make sure you create the virtual environment with Python 3.11.
You might have to use the `python3.11` command instead of `python`
Once you are in the virtual environment, you can use `python`

```
$ cd $cerfServer
$ python -m venv .venv-cerf
$ source $cerfServer/.venv-cerf/bin/activate
(.venv-cerf) $ pip install -r requirements.txt
```

# Setup local configuration
There are 2 files which need to be copied in order to provide custom settings for this installation.
The `settings.py` file contains settings that are applicable to all environments and should normally not be changed.

You should make copies of `__locall_settings.py` and `__.env`. 
```
(.venv-cerf) $ cp $cerfServer/cerfServer/__local_settings.py cerfServer/local_setings.py
(.venv-cerf) $ cp $cerfServer/cerfServer/__.env cerfServer/.env
```
The 2 template files are suitable for development and no changes need to be made.
Note that these files are not checked in to Git

# Initial Set-up of database

Install Postgres if not already done.

Ensure that you are still in the `.venv-cerf` virtual environment
Run `manage.py migrate` to create all the tables
```
(.venv-cerf) $ python manage.py migrate
```

Create a superuser called `admin` that is used for initializing 
the static tables. 

```
(.venv-cerf) $ python manage.py createsuperuser
```
Run `init_sql` and `init_gages` to initialize the static tables
```
(.venv-cerf) $ python manage.py init_sql
(.venv-cerf) $ python manage.py init_gages
```

# Updating
After pulling the latest updates from the repo, you should run `migrate` 
in case there have been any database changes
```
(.venv-cerf) $ python manage.py migrate
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



