# Create virtual environment and install dependencies

Connect to the root directory where you cloned the repo, assumed to be `$cerfServer`

**_Important:_**
Make sure you create the virtual environment with Python 3.11.
You might have to use the `python3.11` command instead of `python`
Once you are in the virtual environment, you can use `python`

```
$ cd $cerfServer
$ python3.11 -m venv .venv-cerf
$ source $cerfServer/.venv-cerf/bin/activate
(.venv-cerf) $ pip install --upgrade pip
(.venv-cerf) $ pip install -r requirements.txt
```

# Setup local configuration
There are 2 files which need to be copied in order to provide custom settings for this installation.
The `settings.py` file contains settings that are applicable to all environments and should normally not be changed.

You should make copies of `__local_settings.py` and `__.env`. 
```
(.venv-cerf) $ cp $cerfServer/cerfServer/__local_settings.py cerfServer/local_settings.py
(.venv-cerf) $ cp $cerfServer/cerfServer/__.env cerfServer/.env
```
The 2 template files are suitable for development and no changes need to be made.
Note that these files are not checked in to Git


# Access to AWS
Some endpoints require access to AWS and therefore you must update your credentials.
The credentials only last a few hours, so be prepared to refresh them at least once a day.
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


In order to not have any AWS specific code, AWS buckets are mounted as a regular file system using s3fs.  Create a directory to contain the contents of a specific S3 bucket.
For example, if we will be using `ngwpc-dev`' create a directory called `~/s3/ngwpc-dev`.  Then install s3fs and mount the bucket
```
$ sudo apt update
$ sudo apt install s3fs
$ mkdir -p ~/s3/ngwpc-dev
$ s3fs ngwpc-dev ~/s3/ngwpc-dev 
$ ls ~/s3/ngwpc-dev
```
To unmount it at some later point use
```
fusermount -u ~/s3/ngwpc-dev
```
When refreshing your AWS credentials, you might have to unmount and re-mount
```
fusermount -u ~/s3/ngwpc-dev
$ s3fs ngwpc-dev ~/s3/ngwpc-dev 
```

There are some additional options for performance that I've played with.  At the very least, we should probably cache the results to avoid multiple round-trips to AWS.
But this might be moot on other environments.
```
$ s3fs ngwpc-dev ~/s3/ngwpc-dev -o parallel_count=20 -o multireq_max=50 -o multipart_size=100 -o use_cache=/tmp/s3fs_cache
```

This information should already be in local_settings.py, which defines the mount point that has just been created
```
HYDROFABRIC_BUCKET = 'ngwpc-dev'
HYDROFABRIC_BUCKET_MOUNT_POINT = os.path.join(Path.home(), 's3/ngwpc-dev')
```
Some of these might only be needed temporarily, until Hydrofabric returns file system urls and not S3 urls

**Note:** There are other tools that perform the same functionally as `s3fs`,  and 
environments, such as Parallel Works 
might have other ways of implementing this functionality.  There is nothing in the server code
that is dependant on `s3fs`.  All that matters is that the bucket is mounted as a file space
and that there is agreement between NgenServer and Hydrofabric on the mount point.


# Initial Set-up of database

Install Postgres if not already done so.

The `runCerf.sh` script will handle initialization of the database the 
first time it runs and will then  `manage.py runServer` to start up the server.  
For subsequent runs, it will run `migrate` and `runServer`.

In those cases where you need to re-initialize the data, after dropping all the tables you should
delete the file called `.load-static`.  If this file is missing, that tells `runCert.sh` to re-initialize the database

## Manual Steps
These are the steps the `runCert` is performing.  You can skip them if you've successfully run `runCerf`.

Ensure that you are still in the `.venv-cerf` virtual environment
Run `manage.py migrate` to create all the tables
```
(.venv-cerf) $ python manage.py migrate
```

Create a superuser called `admin` that is used for initializing 
the static tables.  Use `createsuperuser_docker` even though you are not creating a docker container.  
It is a locally modified version of `createsuperuser` that allows you to enter the password on the command line.

```
(.venv-cerf) $ python manage.py createsuperuser_docker --username admin --password admin
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
where `public` is the name of your schema.

# Updating
After pulling the latest updates from the repo, you should update any dependencies and  apply any database changes.  
Both of these commands can be run multiple times without any harm.
```
(.venv-cerf) $ pip install -r requirements.txt
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


# Installing ngen and ngen-cal

Follow the instructions at https://confluence.nextgenwaterprediction.com/display/NGWPC/Build+ngen-cal+and+ngen+from+GitLab. 

Use these recommended directory names to avoid having to change your settings.
* It is recommended that you create a directory called `~/ngen-cal-work`
* It is recommended that you clone ngen and ngen-cal in a directory called `~/noaa-owp/ngen` and `~.noaa-owp/ngen-cal`


* Create the ngen-cal virtual environment.  This directory goes into `settings.py` as `NGEN_CAL_VENV`.   Suggested location is `~/ngen-cal-work/venv`
* Clone ngen-cal from Gitlab.  This directory goes into `settings.py` as `NGEN_CAL_REPO_ROOT`.  Suggested location is `~/noaa-owp/ngen-cal`
* Follow instructions for installing ngen-cal
* Clone ngen from Gitlab.  This directory goes into `settings.py` as `NGEN_REPO_ROOT`.  Suggested location is `~/noaa-owp/ngen`
* Follow instructions for installing ngen
* It is **not** necessary to create the ROOT_DIR_RUN_NGEN_CAL directory or to run the script that creates symbolic links in that directory
* Define a directory in `settings.py` where all the ngen-cal runs will live called `NGEN_CAL_RUN_DIR`.  Suggested location is `~/ngen-cal-work/run_calib`

# User Authentication

All endpoints require a user to be authenticated.  Unless we have a front-end, this authentication needs to be done manually -- 
preferably with a tool like Postman.

To create a user, send the username/password to the endpoint `/auth/users/`
```
{
   "username": <username>,
   "password": <password>
 }
```

User creation only needs to be done once.

To simulate a login, send the request payload to the endpoint `auth/awt/create`

Extract the access token.  For all subsequent requests, you need to include an `Authorization` header of 
type `Bearer token` that includes the access token.

# Directory structure

By convention with the Docker images, the mount point is at `~/ngwpc/data`.   This is defined in `settings.py` and should not change without proper coordination. 

Under there, we have our work directory, `ngen-cal-work`.  This directory contains files that are common and can be shared with all the calibration runs, such as forcing and observation data that comes from hydrofabric,
as well as some static files.

The static files are in `ngen-cal-work/bmi_config/Noah-OWP`  and `ngen-cal-work/parquet`.  These directories will be populated automatically at start-up.  Nothing else needs to be done.

`ngen-cal-work/forcing`, `ngen-cal-work/observation` and `ngen-cal-work/geopackage` are used for the forcing, observation and geopackage files that are downloaded from Hydrofabric.  
This is a shared location, since these files can be re-used by different jobs for the same gage.

If the user chooses to upload the forcing or observation files, they will be put into the instance specific directory, which is `ngen-cal-work/run_calib/{id}_{user}`, 
where `id` is the id of the calibration run and `user` is the owner of the run.  
The instance-specific directory is also where `create-input` creates the directory structure that is used at run-time by ngen and ngen-cal

In the example below, `20_peter/forcing` and `20_peter/observation` contain user-uploaded forcing and observation files.

```
peter.a.kronenberg@U-12SMBYD5450YI:~/ngwpc/data$ tree -L 4  -n -A
.
└── ngen-cal-work
    ├── bmi_config
    │   └── Noah-OWP
    │       ├── GENPARM.TBL
    │       ├── MPTABLE.TBL
    │       └── SOILPARM.TBL
    ├── forcing
    │   └── Gage_01123000
    │       ├── cat-10617.csv
    │       ├── cat-10618.csv
    │       ├── cat-10619.csv
    │       ├── cat-10620.csv
    │       ├── cat-10625.csv
    │       └── cat-10626.csv
    ├── geopackage
    │   ├── gauge_01073000.gpkg
    │   └── gauge_01123000.gpkg
    ├── observation
    │   └── 01123000_hourly_discharge.csv
    ├── parquet
    │   └── conus_model_attributes.parquet
    └── run_calib
        ├── 19_peter
        │   └── forcing
        ├── 1_peter
        │   ├── forcing
        │   └── observation
        └── 20_peter
            ├── forcing
            ├── input.config
            ├── KGE_DDS
            ├── observation
            ├── parameters.txt
            └── sloth_parameters.txt
```

# Importing test data

There is an import command that allows you to import data and create a calibration run job without having to go though the UI.  
This is intended to facilitate testing (and eventually, provide a CLI interface to the user)

In the `Import_test_data` directory, there are several scripts.  First, make sure they are executable.  Then, set environment variables with your username and password
```
$ chmod +x *.sh
$ export NGEN_USERNAME="your_username"
$ export NGEN_PASSWORD="your_password"
```

You can then run the `ngen_import.sh` script with one of the sample input files.  Everytime you run `ngen_import.sh`, a new Calibration Run job will be created.  
The different data files will create jobs will various amounts of data imported.
The error messages that you get from the import are intended to let you know which data is still required to make the job runnable and at this point, can be ignored.

Note that the `run_after_import` flag is not yet supported.

The metadata section is totally ignored on import and can be used to add your own comments, as long as it is in Json format.


