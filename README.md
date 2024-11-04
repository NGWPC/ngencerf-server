# Create virtual environment and install dependencies

Connect to the root directory where you cloned the server repo, assumed to be `$cerfServer`

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

# Create data directory

Create a directory that will hold the data.  It can be anything, such as `~/ngwpc/data`.  But a symbolic link needs to be created to match the location in the ngen/ngen-cal Docker, 
which is `/ngencerf/data`.
This is defined in `settings.py` as the mount point.

Enter these commands to create the top-level `/ngencerf` directory and then create the symbolic link

```
sudo mkdir /ngencerf
sudo ln -s ~/ngwpc/data /ngencerf/data
```


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
$ mkdir -p ~/s3/ngwpc-dev
$ goofys ngwpc-dev ~/s3/ngwpc-dev
$ ls ~/s3/ngwpc-dev
```

To unmount it at some later point use
```
fusermount -u ~/s3/ngwpc-dev
```
When refreshing your AWS credentials, you will have to unmount and re-mount
```
$ fusermount -u ~/s3/ngwpc-dev
$ s3fs ngwpc-dev ~/s3/ngwpc-dev or goofys ngwpc-dev ~/s3/ngwpc-dev
$ ls ~/s3/ngwpc-dev
```

**Note:** There are other tools that perform the same functionally as `s3fs`,  and 
environments, such as Parallel Works 
might have other ways of implementing this functionality.  There is nothing in the server code
that is dependant on `s3fs`.  All that matters is that the bucket is mounted as a file space
and that there is agreement between NgenCerf and Hydrofabric path.


# Static Files
There are some static files that are required for Ngen to run.  They should be in a directory under the mount point called `ngen-static-files`.  

The data for the `ngen-static-files` directory is on S3 at `s3://ngwpc-dev/ngen-static-files/`.  This directory and all its contents should be copied to
`/ngencerf/data/ngen-static-files`
```
aws s3 cp --recursive s3://ngwpc-dev/ngen-static-files /ngencerf/data/ngen-static-files
```


# Initial Set-up of database

Install Postgres if not already installed.
```
sudo apt update
sudo sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb\_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list'
wget -qO- https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo tee /etc/apt/trusted.gpg.d/pgdg.asc &>/dev/null
sudo apt install postgresql postgresql-client -y
systemctl status postgresql
```

Change the password for the Admin user
```
sudo -u postgres psql
ALTER USER postgres PASSWORD 'postgres';
\q
```

Confirm that you can log in with the new password
```
# psql -h localhost -U postgres
```

When you run `runCerf.sh` for the first time, or after dropping all tables from the database, include the `--load-static` option.  
For example,
```
./runCerf.sh --load-static
```

To update the code, do a `git pull` and run `runCerf.sh` again


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


# Running the server
To run the server, use `runCerf.sh`

**Note:** If running locally (ngen and ngen-cal are being spawned as processes on the same machine), then it is import to run `pre_start.py` from `manage.py` before the
server starts in order to clean up any Calibrations or Validations that were running at the time the server went down.
This is not necessary when running on Parallel Works


# User Authentication

All endpoints require a user to be authenticated.  You can create a user through the front-end UI or use this curl command:

You can use this `curl` command
```
curl --location 'localhost:8000/auth/users/' \
--header 'Content-Type: application/json' \
--data-raw '{
    "email": "<email>",
    "password": "<password>"
}'
```

User creation only needs to be done once.

To simulate a login, send the same payload, containing the email and password, to the endpoint `auth/awt/create`

Extract the access token.  For all subsequent requests, you need to include an `Authorization` header of 
type `Bearer token` that includes the access token.

# Importing test data

The `cli` directory contains an `ngencerf.sh` command line script which will allow you to import data and create a calibration run job without having to go though the UI.  

In the `import_test_data` directory, there are some sample import data files.  Set environment variables with your email and password (or put them in ~/.bashrc)
```
$ export NGEN_EMAIL="your_email"
$ export NGEN_PASSWORD="your_password"
```

You can then run the `ngencerf.sh` script with one of the sample input files.  Everytime you run `ngencerf.sh`, a new Calibration Run job will be created.  
The error messages that you get from the import are intended to let you know which data is still required to make the job runnable and at this point, can be ignored.

The metadata section is totally ignored on import and can be used to add your own comments, as long as it is in Json format.

See [NgenCERF Command Line Interface (CLI)](https://confluence.nextgenwaterprediction.com/pages/viewpage.action?pageId=20056845)

# Runtime environments

There are 3 environments that ngen/ngen-cerf can run in, defined by `settings.NGEN_ENVIRONMENT` in .env

```
NGEN_ENVIRONMENT = DOCKER
```


1. LOCAL - ngen and ngen-cal must be installed on your local machine, for example, in `~/noaa-owp/ngen` and `~/noaa-owp/ngen-cal`
Create a symbolic link to match the specifying in settings.py.
   ```
   sudo mkdir /ngen-app
   sudo ln -s ~/noaa-owp /ngen-app
   ```
   This environment is the hardest to set up because of the steps involved in installing ngen and ngen-cal, and is not recommended.


2. DOCKER - ngen and ngen-cal are installed in a docker container.  This is the easiest for running locally.
Follow these steps to pull the latest ngen-cal docker container.  This container includes both ngen and ngen-cal

   1. If you don't have Docker installed, follow the instructions here: https://confluence.nextgenwaterprediction.com/display/NGWPC/AWS+Ubuntu+22.04+LTS+Workspace+for+Docker#AWSUbuntu22.04LTSWorkspaceforDocker-InstallDocker
   2. Follow the instructions here to 'Manage Docker as a non-root user': https://docs.docker.com/engine/install/linux-postinstall/#manage-docker-as-a-non-root-user
   3. (Use your AWS credentials to login)
   ```
   docker login registry.sh.nextgenwaterprediction.com
   docker pull registry.sh.nextgenwaterprediction.com/ngwpc/nwm-ngen/ngen-cal:latest && docker tag registry.sh.nextgenwaterprediction.com/ngwpc/nwm-ngen/ngen-cal:latest ngen-cal
   ```

   **Note:** If you are developing and have updates to ngen-cal that you want to include, use the following from the ngen-cal repo directory:
   ```
   GITLAB_TOKEN=$(cat ~/.gitlab_token) docker build --secret id=GITLAB_TOKEN,env=GITLAB_TOKEN --tag=ngen-cal . 
   ```
 
3. PARALLEL_WORKS - ngen and ngen-cal are installed in a docker container and spawning of ngen-cal process are done using Slurm



# Directory structure

By convention with the Docker images, the mount point is at `/ngencerf/data`.   This is defined in `settings.py` and should not change without proper coordination. 

`/ngencerf/data` contains `ngen-static-files` and `ngen-cal-work`

`ngen-cal-work/run_calib` contains the data for ngen and ngen-cal

Files from Hydrofabric are in `s3/ngwpc-dev/hyrofabric`.  This is an S3 bucket that is mounted as a file system.  This allows us not to have to worry about downloading files from S3. 
This is a shared location, since these files can be re-used by different jobs for the same gage.

If the user chooses to upload the forcing, observation or geopackage files, they will be put into the instance specific directory, which is `ngen-cal-work/run_calib/{id}_{user}`, 
where `id` is the id of the calibration run and `user` is the owner of the run.  
The instance-specific directory is also where `create-input` creates the directory structure that is used at run-time by ngen and ngen-cal.

Prior to running the job, the Observation and Forcing files from Hydrofabric will be subsetted to conform to the time range of the job.
These files will be placed in the instance specific directory, as described above.
So at run time, the Observation and Forcing data will be in the same location, regardless of whether it came from Hydrofabric or User upload


```
peter.a.kronenberg@U-12SMBYD5450YI:~$ tree /ngencerf -L 4 -n -A
/ngencerf
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
    └── ngwpc-dev/hydrfabric  
```


# Installing ngen and ngen-cal
**Note:** This process is not recommended.  Run ngen and ngen-cal in a docker container as described in Runtime Environments

Follow the instructions at https://confluence.nextgenwaterprediction.com/display/NGWPC/Build+ngen-cal+and+ngen+from+GitLab. 

Use these recommended directory names to avoid having to change your settings.
* It is recommended that you create a directory called `~/ngwpc/data/ngen-cal-work`
* It is recommended that you clone ngen and ngen-cal in a directory called `~/noaa-owp/ngen` and `~/noaa-owp/ngen-cal`


* Create the ngen-cal virtual environment.  This directory is defined in `settings.py` as `NGEN_CAL_VENV`.   Default location is `~/ngen-cal-work/venv-cal`
* Clone ngen-cal from Gitlab.  This directory is defined in `settings.py` as `NGEN_CAL_REPO_ROOT`.  Default location is `~/noaa-owp/ngen-cal`
* Follow instructions for installing ngen-cal
* Clone ngen from Gitlab into `~/noaa-owp/ngen`
* Follow instructions for installing ngen
* It is **not** necessary to create the ROOT_DIR_RUN_NGEN_CAL directory or to run the script that creates symbolic links in that directory
* Create the `NGEN_CAL_RUN_DIR` at `~/ngwpc/data/run_calib`

