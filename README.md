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

**_Note:_**
Due to a compatibility issue with ngen-cal's create_input, make sure you are running numpy 1.26.4 and not 2.x

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

**_Important:_**
During development, there might be times when the entire database needs to be initialized.  
In that case, drop all existing tables in the database and run these initialize steps again.

To drop all tables, you can use this script:
```
do $$ declare
    r record;
begin
    for r in (select tablename from pg_tables where schemaname = 'public') loop
        execute 'drop table if exists ' || quote_ident(r.tablename) || ' cascade';
    end loop;
end $$;
```
where `public` is the name of you schema.

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

**_Note:_**
You will get warnings about `ngen` and `ngen-cal` files that don't exist.  That is fine if you haven't installed them yet.
The server will still run.  You just won't be able to actually run a Calibration.

# Access to AWS
Some endpoints require access to AWS and therefore you must update your credentials.
The credentials only last a few hours, so no need to get them until you're ready.
Follow instructions here: https://confluence.nextgenwaterprediction.com/display/NGWPC/Accessing+S3+Bucket+Programmatically+or+through+AWS+CLI, 
to get your credentials.
Add them to your `~/.aws/credentials` file (create the file if it doesn't exist)
You should manually add the region.  The file will look something like this

```
[default]
region=us-east-1

aws_access_key_id = <key_id>
aws_secret_access_key = <access_key>
aws_session_token = <token>
```

# Installing ngen and ngen-cal

Follow the instructions at https://confluence.nextgenwaterprediction.com/display/NGWPC/Build+ngen-cal+and+ngen+from+GitLab. 

Use these recommended directory names to avoid having to change your settings.
* It is recommended that you create a directory called `~/ngen-cal-work`
* It is recommended that you clone ngen and ngen-cal in a directory called `~/noaa-owp/ngen` and `~.noaa-owp/ngen-cal`


* Create the ngen-cal virtual environment.  This directory goes into `settings.py` as `NGEN_CAL_VENV`.   Suggested location is `~/ngen-cal-work/venv`
* Clone ngen-cal from Gitlab.  This directory goes into `settings.py` as `NGEN_CAL_REPO_ROOT`.  Suggested location is `~/noaa-owp/ngen`
* Follow instructions for installing ngen-cal
* Clone ngen from Gitlab.  This directory goes into `settings.py` as `NGEN_REPO_ROOT`.  Suggested location is `~/noaa-owp/ngen-cal`
* Follow instructions for installing ngen
* It is **not** necessary to create the ROOT_DIR_RUN_NGEN_CAL directory or to run the script that creates symbolic links in that directory
* Define a directory in `settings.py` where all the ngen-cal runs will live called `NGEN_CAL_RUN_DIR`.  Suggested location is `~/ngen-cal-work/run_calib`



