# Target Environment 
These instructions are primarily for installing ngencerf-server in your local development environment.  Requires an AWS account with S3 bucket access.
An EDFS server is also required.  The url of the server is specified in `.env`

# Create virtual environment and install dependencies

Connect to the root directory where you cloned the server repo, assumed to be `$cerfServer`, for example, `~/ngecerf-server/`

The project requires Python 3.12.  If your system does not have Python 3.12, see your administrator

runCerf.sh will create the virtual environment, so it 
is not necessary to do it manually.

But if you do, make sure you create the virtual environment with Python 3.12.
You might have to use the `python3.12` command instead of `python`
Once you are in the virtual environment, you can use `python`

```
$ cd $cerfServer
$ python3.12 -m venv .venv-cerf_python3.12
$ source $cerfServer/.venv-cerf/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

# Setup local configuration
The `__env` file is a template for local environment settings.  Make a copy of it

```
cp $cerfServer/cerfServer/__.env $cerfServer/.env
```
This template file is suitable for development and no changes need to be made.
Note that the .env file is not checked in to Git

# Install Postgres

See your administer for instructions on installing Postgres locally.  Connection values can
be specified in `.env`, e.g., CERF_SERVER_DATABAWSE_HOST, CERF_SERVER_DATABASE_USER, etc.  Also, see `settings.py`


# Install Redis
Redis is used for the cache.  It is memory-only and non-persistent.  When the server is restarted, the cache *must* be cleared.
See your administer for instructions on installing Redis locally.  Each instance of the server needs to have its own istance of Redis,
so it should be installed for use by a single developer.

The file 'redis.conf.dev' has the configuration needed for Redis

# Create data directory

Create a directory that will hold the data.  It can be anything, such as `~/ngwpc/data`.  
But a symbolic link needs to be created to match the location specified by `CONTAINER_DATA_ROOT`, defined in `settings.py`.
which, by default, is `/ngencerf/data`.  For development, you can change this value to match your local directory.

Enter these commands to create the top-level `/ngencerf` directory and then create the symbolic link

```
sudo mkdir /ngencerf
sudo ln -s ~/ngwpc/data /ngencerf/data
```

# Access to AWS

Some endpoints require access to AWS and therefore you must update your credentials.
Follow your sites instructions for getting AWS Credentials and add them to `~/.aws/credentials` file (create the file if it doesn't exist)

# Archive/Zips Directory

In `$cerfServer/.env`, Define an s3 bucket/directory that will be used for archiving and zipping

For development, you can use any directory that you have write access to.  For example,
```
`NGENCERF_ARCHIVE_S3_PATH=s3://ngwpc-dev/<user>/ngencerf_archive/`
`NGENCERF_ARCHIVE_S3_PATH=s3://ngwpc-dev/<user>/ngencerf_zips/`
 ```

In this example, `s3://ngewpc-dev` is simply a bucket that you and others have access to.

Use your own directory. Do not share a directory with someone else

**_Important:_**
Since S3 directories aren't real directories, they will not persist if they are empty.  So it is important to
create a dummy file in the directory that will remain there.  Enter these commands
```
printf "Do not delete.\nThis placeholder file ensures this S3 prefix is retained.\nS3 does not preserve empty directories; at least one object must exist.\n" \
  | aws s3 cp - s3://ngwpc-dev/<user>/ngencerf_archive/.keep
  printf "Do not delete.\nThis placeholder file ensures this S3 prefix is retained.\nS3 does not preserve empty directories; at least one object must exist.\n" \
  | aws s3 cp - s3://ngwpc-dev/<user>/ngencerf_zips/.keep
```

# Static Files
There are some static files that are required for Ngen to run.  They should be in a directory under the data directory at `CONTAINER_DATA_ROOT` called `ngen-static-files`.

The data for the `ngen-static-files` directory is in several locations.  Execute the following commands to copy everything
to`/ngencerf/data/ngen-static-files`
(These commands might be different depending on where the static data is stored.  The names of the repositories might also be slightly different)
```
aws s3 cp --recursive s3://ngwpc-dev/nwm-tools-data/nwm_retrospective/ /ngencerf/data/ngen-static-files/nwm_retrospective/
aws s3 cp --recursive s3://ngwpc-dev/nwm-tools-data/esmf/ /ngencerf/data/ngen-static-files/forcing_static_dir/ 
```

In addition, copy the directory `module_parameter_files` and all its contents from
https://github.com/NGWPC/nwm-msw-mgr/tree/development/src/mswm/module_parameter_files to the `/ngencerf/data/ngen-static-files` directory.

```
cd /ngencerf/data/ngen-static-files 
# for PW, use:
# cd /ngencerf-app/data/ngen-cal-data/ngen-static-files

rm -rf module_parameter_files
git clone --depth 1 --filter=blob:none --sparse -b development https://github.com/NGWPC/nwm-msw-mgr.git tmp-nwm-msw-mgr && \
cd tmp-nwm-msw-mgr && \
git sparse-checkout set src/mswm/module_parameter_files && \
mv src/mswm/module_parameter_files ../ && \
cd .. && rm -rf tmp-nwm-msw-mgr
```

Copy the directory `https://github.com/NGWPC/ngen-forcing/tree/development/NextGen_Forcings_Engine_BMI/BMI_NextGen_Configs/config_templates`
and all its contents to the `/ngencerf/data/ngen-static-files` directory as `bmi_forcing_templates`

```
cd /ngencerf/data/ngen-static-files 
# For PW, use:
# cd /ngencerf-app/data/ngen-cal-data/ngen-static-files

rm -rf bmi_forcing_templates
git clone --depth 1 --filter=blob:none --sparse -b development https://github.com/NGWPC/ngen-forcing.git tmp-ngen-forcing && \
cd tmp-ngen-forcing && \
git sparse-checkout set NextGen_Forcings_Engine_BMI/BMI_NextGen_Configs/config_templates && \
mv NextGen_Forcings_Engine_BMI/BMI_NextGen_Configs/config_templates ../bmi_forcing_templates && \
cd .. && rm -rf tmp-ngen-forcing
```

From the directory `https://github.com/NGWPC/nwm-eval-mgr/tree/development/data/inputs/gage_files`,
copy only the *.parquet files to the `/ngencerf/data/ngen-static-files/verification_data` directory

```
cd /ngencerf/data/ngen-static-files
# For PW, use:
# cd /ngencerf-app/data/ngen-cal-data/ngen-static-files

rm -rf verification_data
git clone --depth 1 --filter=blob:none --sparse --branch development https://github.com/NGWPC/nwm-eval-mgr.git tmp-nwm-eval-mgr && \
cd tmp-nwm-eval-mgr && \
git sparse-checkout set data/inputs/gage_files && \
mkdir -p ../verification_data && \
find data/inputs/gage_files -type f -name '*.parquet' -exec cp {} ../verification_data/ \; && \
cd .. && rm -rf tmp-nwm-eval-mgr
```

When done, your `ngen-static-files` directory should look something like this


ngen-static-files/
├── bmi_forcing_templates
├── module_parameter_files
│  ├── lasam
│  ├── noah-owp-modular
│  └── ueb
└── nwm_retrospective


# User Authentication

All endpoints require a user to be authenticated.  You can create a user through the front-end UI, the command-line interface or use this curl command:

You can use this `curl` command
```
curl --location 'localhost:8000/auth/users/' \
--header 'Content-Type: application/json' \
--data-raw '{
    "email": "<email>",
    "password": "<password>"
}'
```

To use the CLI, from the `cli` directory, enter
`./ngencerf register`

User creation only needs to be done once.

To simulate a login, send the same payload, containing the email and password, to the endpoint `auth/awt/create`

Extract the access token.  For all subsequent requests, you need to include an `Authorization` header of
type `Bearer token` that includes the access token.

# Runtime environments

There are 2 environments that ngen/ngen-cerf can run in, defined by `settings.JOB_EXECUTION_MODE` in .env.


```
JOB_EXECUTION_MODE = DOCKER
```


1. DOCKER - ngen and cal-mgr are installed in a docker container.  This is the method used for running locally.
Follow these steps to pull the latest docker containers. 


   Follow your administer's instructions for installing Docker.  The image urls will also be different

   ```
   docker pull ghcr.io/ngwpc/nwm-cal-mgr:latest && docker tag ghcr.io/ngwpc/nwm-cal-mgr nwm-cal-mgr
   docker pull ghcr.io/ngwpc/nwm-fcst-mgr:latest && docker tag ghcr.io/ngwpc/nwm-fcst-mgr:latest nwm-fcst-mgr
   docker pull ghcr.io/ngwpc/ngen-bmi-forcing:latest && docker tag ghcr.io/ngwpc/ngen-bmi-forcing:latest ngen-bmi-forcing
   ```

   **Note:** If you are developing and have updates to the repos that you want to include, use one of the following from the appropriate repo directory:

    ```
    docker build --tag=nwm-cal-mgr . 
    docker build --tag=nwm-fcst-mgr . 
    docker build --file Dockerfile.bmi-forcings --tag=ngen-bmi-forcing .
    ```
 
2. SLURM - The docker/singularity containers are built for you and the server uses Slurm to communicate.  This is used when running on AWS, with an HPC environment



# Directory structure

By convention with the Docker images, the CONTAINER_DATA_ROOT is at `/ngencerf/data`.   This is defined in `settings.py` and should not change without proper coordination.

`/ngencerf/data` contains `ngen-static-files` and `ngen-cal-work`

`ngen-cal-work/run_calib` contains the data for ngen and cal-mgr

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
        └── nwm_retrospective
            ├── 01118000.csv
            ├── 01121000.csv
            ├── 01123000.csv
            ├── 01127500.csv
            ├── 01130000.csv
            └── 01134500.csv


```


# Running the server
To run the server, use `runCerf.sh`.
```
./runCerf.sh
```

**Note:** If running with JOB_EXECUTION_MODE=DOCKER, then it is important to run `pre_start.py` from `manage.py` before the
server starts in order to clean up any Calibrations or Validations that were running at the time the server went down.


# Run the server in Docker

The dev stack (server + Postgres + Redis) runs via `compose.yaml`. All dev
values are baked in as defaults, so **no `--env-file` is needed** — just make
sure the `/ngencerf/data` symlink (see [Create data directory](#create-data-directory)) exists and its `ngen-static-files`
directory is populated (see [Static Files](#static-files)).

```
CACHE_BUST=$(date +%s) docker compose up --build ngencerf-services
```

The server comes up at http://localhost:8000 and Postgres at localhost:5432.

> **Port conflict:** the `db` container binds host port **5432**. If you also run Postgres on the host (common if you switch between host and containerized Postgres), free the port first — e.g. `sudo systemctl stop postgresql` — or the `db` container won't start.

- **Force a rebuild** (to pick up code changes): keep `--build`, or run `docker compose build --no-cache ngencerf-services`.
- **Force a static-data reload:** static data loads once on first start, tracked by `../data/.ngencerf-init/.load_static`. Delete that file to reload on the next start.
- **Shell into the running container:** `docker exec -it $(docker ps -qf name=ngencerf-services) bash`.

> Parallel Works production deploys from the `development-pw` branch, which carries its own `production-pw.yaml` + `cerfServer/.env-override`. AWS deployments inject configuration through ECS task definitions.
