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
pip install --upgrade pip
pip install -r requirements.txt
```

# Setup local configuration
There are 2 files which need to be copied in order to provide custom settings for this installation.
The `settings.py` file contains settings that are applicable to all environments and should normally not be changed.

You should make copies of `__local_settings.py` and `__.env`. 
```
cp $cerfServer/cerfServer/__local_settings.py cerfServer/local_settings.py
cp $cerfServer/cerfServer/__.env cerfServer/.env
```
The 2 template files are suitable for development and no changes need to be made.
Note that these files are not checked in to Git

# Static Files
There are some static files that are required for Ngen to run.  They should be in a directory under the mount point called `ngen-static-files`.  
By default, when running locally, the mount point is at `~/ngwpc/data`.
It Docker, this is mapped to `data/ngen-cal-data`

The data for the `ngen-static-files` directory is on S3 at s3://ngwpc-dev/ngen-static-files/.  This directory and all its contents should be copied to
`~/ngwpc/data/ngen-static-files`



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


In order to not have any AWS specific code, AWS buckets are mounted as a regular file system.  
There are any number of tools that can do this.  I've tested `s3fs` and `goofys` on AWS Workspace.
Create a directory to contain the contents of a specific S3 bucket.
For example, if we will be using `ngwpc-dev`' create a directory called `~/s3/ngwpc-dev`.  
Then install  either `s3fs` or `goofys` and mount the bucket

### S3FS
```
$ sudo apt update
$ sudo apt install s3fs
$ mkdir -p ~/s3/ngwpc-dev
$ s3fs ngwpc-dev ~/s3/ngwpc-dev 
$ ls ~/s3/ngwpc-dev
```

### Goofys
```
$ sudo wget https://github.com/kahing/goofys/releases/download/v0.24.0/goofys -O /usr/local/bin/goofys
$ sudo chmod +x /usr/local/bin/goofys
$ goofys ngwpc-dev ~/s3/ngwpc-dev
$ ls ~/s3/ngwpc-dev
```

To unmount it at some later point use
```
fusermount -u ~/s3/ngwpc-dev
```
When refreshing your AWS credentials, you might have to unmount and re-mount
```
fusermount -u ~/s3/ngwpc-dev
$ s3fs ngwpc-dev ~/s3/ngwpc-dev or goofys ngwpc-dev ~/s3/ngwpc-dev
$ ls ~/s3/ngwpc-dev
```

There are some additional options for performance that I've played with.  At the very least, we should probably cache the results to avoid multiple round-trips to AWS.
But this might be moot on other environments.
```
$ s3fs ngwpc-dev ~/s3/ngwpc-dev -o parallel_count=20 -o multireq_max=50 -o multipart_size=100 -o use_cache=/tmp/s3fs_cache
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
For subsequent runs, it will run `pip install`, `migrate` and `runServer`.

In those cases where you need to re-initialize the data, after dropping all the tables you should
run  `runCerf.sh` with the `--load-static` argument.


## Manual Steps (optional if you're using runCerf.sh)
These are the steps the `runCert` is performing.  You can skip them if you've successfully run `runCerf`.

**Ensure that you are still in the `.venv-cerf` virtual environment**

Run `pip install -r requirements.txt` to update any dependencies
Run `manage.py migrate` to create all the tables
```
source $cerfServer/.venv-cerf/bin/activate
pip install -r requirements.txt
python manage.py migrate
```

Create a superuser called `admin` that is used for initializing 
the static tables.  Use `createsuperuser_docker` even though you are not creating a docker container.  
It is a locally modified version of `createsuperuser` that allows you to enter the password on the command line.

```
python manage.py createsuperuser_docker --username admin --password admin
```
Run `init_sql` and `init_gages` to initialize the static tables
```
python manage.py init_sql
python manage.py init_gages
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
After pulling the latest updates from the repo, you should update any dependencies and apply any database changes.  
Both of these commands can be run multiple times without any harm.  `runCerf.sh` will automatically take care of these steps
```
pip install -r requirements.txt
python manage.py migrate
```

# Running the server
To run the server, use `runCerf.sh`

**Note:** If running locally (ngen and ngen-cal are being spawned as processes on the same machine), then it is import to run `pre_start.py` from `manage.py` before the
server starts in order to clean up any Calibrations or Validations that were running at the time the server went down.
This is not necessary when running on Parallel Works


# Installing ngen and ngen-cal

Follow the instructions at https://confluence.nextgenwaterprediction.com/display/NGWPC/Build+ngen-cal+and+ngen+from+GitLab. 

Use these recommended directory names to avoid having to change your settings.
* It is recommended that you create a directory called `~/ngwpc/data/ngen-cal-work`
* It is recommended that you clone ngen and ngen-cal in a directory called `~/noaa-owp/ngen` and `~/noaa-owp/ngen-cal`


* Create the ngen-cal virtual environment.  This directory is defined in `settings.py` as `NGEN_CAL_VENV`.   Default location is `~/ngen-cal-work/venv`
* Clone ngen-cal from Gitlab.  This directory is defined in `settings.py` as `NGEN_CAL_REPO_ROOT`.  Default location is `~/noaa-owp/ngen-cal`
* Follow instructions for installing ngen-cal
* Clone ngen from Gitlab into `~/noaa-owp/ngen`
* Follow instructions for installing ngen
* It is **not** necessary to create the ROOT_DIR_RUN_NGEN_CAL directory or to run the script that creates symbolic links in that directory
* Create the `NGEN_CAL_RUN_DIR` at `~/ngwpc/data/run_calib`

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

You can use this `curl` command
```
curl --location 'localhost:8000/auth/users/' \
--header 'Content-Type: application/json' \
--data-raw '{
    "username": "<username>",
    "password": "<password"
}'
```

User creation only needs to be done once.

To simulate a login, send the request payload to the endpoint `auth/awt/create`

Extract the access token.  For all subsequent requests, you need to include an `Authorization` header of 
type `Bearer token` that includes the access token.

# Directory structure

By convention with the Docker images, the mount point is at `~/ngwpc/data`.   This is defined in `settings.py` and should not change without proper coordination. 

`~/ngwpc/data` contains `ngen-static-files` and `ngen-cal-work`


`ngen-cal-work/run_calib` contains the data for ngen and ngen-cal

Files from Hydrofabric are in `s3/ngwpc-dev`.  This is an S3 bucket that is mounted as a file system.  This allows us not to have to worry about downloading files from S3. 
This is a shared location, since these files can be re-used by different jobs for the same gage.

If the user chooses to upload the forcing or observation files, they will be put into the instance specific directory, which is `ngen-cal-work/run_calib/{id}_{user}`, 
where `id` is the id of the calibration run and `user` is the owner of the run.  
The instance-specific directory is also where `create-input` creates the directory structure that is used at run-time by ngen and ngen-cal.

Prior to running the job, the Observation and Forcing files from Hydrofabric will be subsetted to confirm to the time range of the job.  These files will be placed in the instance specific directory, as described above.
So at run time, the Observation and Forcing data will be in the same location, regardless of whether it came from Hydrofabric or User upload


```
peter.a.kronenberg@U-12SMBYD5450YI:~$ tree ngwpc -L 4 -n -A
ngwpc
└── data
    ├── ngen-cal-work
    │   ├── run_calib
    │   │   ├── 100_peter
    │   │   │    ├── forcing
    │   │   │    ├── observation
    │   │   │    ├── geopackage
    │   │   │    ├── parameters.txt
    │   │   │    └── sloth_parameters.txt
    │   │   └── 98_peter
    │   │        ├── forcing
    │   │        ├── observation
    │   │        ├── geopackage
    │   │        ├── parameters.txt
    │   │        └── sloth_parameters.txt
    │   └── venv.cal
    └── ngen-static-files
        ├── bmi_config
        │   └── Noah-OWP
        │       ├── GENPARM.TBL
        │       ├── MPTABLE.TBL
        │       └── SOILPARM.TBL
        ├── parquet
        │   └── conus_model_attributes.parquet
        └── nwm_retrospective
            ├── 01118000.csv
            ├── 01121000.csv
            ├── 01123000.csv
            ├── 01127500.csv
            ├── 01130000.csv
            └── 01134500.csv

.
└── s3
    └── ngwpc-dev   
```

# Importing test data

The `cli` directory contains an ngencerf.sh command line script which will allow you to import data and create a calibration run job without having to go though the UI.  

In the `import_test_data` directory, there are some sample import data files.  Set environment variables with your username and password (or put them in ~/.bashrc)
```
$ export NGEN_USERNAME="your_username"
$ export NGEN_PASSWORD="your_password"
```

You can then run the `ngencerft.sh` script with one of the sample input files.  Everytime you run `ngencerf.sh`, a new Calibration Run job will be created.  
The different data files will create jobs will various amounts of data imported.
The error messages that you get from the import are intended to let you know which data is still required to make the job runnable and at this point, can be ignored.

The metadata section is totally ignored on import and can be used to add your own comments, as long as it is in Json format.

See [NgenCERF Command Line Interface (CLI)](https://confluence.nextgenwaterprediction.com/pages/viewpage.action?pageId=20056845)
