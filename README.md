# Target Environment 
These instructions are primarily for installing ngencerf-server in your local development environment.  Requires an AWS account with S3 bucket access.
An EDFS server is also required.  The url of the server is specified in `.env`

# Table of Contents

- [Target Environment](#target-environment)
- [Additional documentation](#additional-documentation)
- [Create virtual environment and install dependencies](#create-virtual-environment-and-install-dependencies)
- [Setup local configuration](#setup-local-configuration)
- [Configure the Database](#configure-the-database)
- [Configure the cache](#configure-the-cache)
- [Create data directory](#create-data-directory)
- [Access to AWS](#access-to-aws)
- [Archive/Zips Directory](#archivezips-directory)
- [Static Files](#static-files)
- [User Authentication](#user-authentication)
- [Runtime environments](#runtime-environments)
- [Directory structure](#directory-structure)
- [Running the server](#running-the-server)
- [Run the server in Docker](#run-the-server-in-docker)

# Additional documentation

- [ngenCERF_Server_Configuration_Reference.md](ngenCERF_Server_Configuration_Reference.md): every environment variable, startup flag, and hardcoded setting, with defaults and where each is read.
- [Readme_supporting_services.md](Readme_supporting_services.md): database and cache requirements, including PostgreSQL, SQLite, Redis, and local-memory cache configuration.
- [Readme_portable_deployment.md](Readme_portable_deployment.md): running without container bind mounts, without Docker, or on a plain Linux host; which paths are configurable.
- [Readme_active_directory_doc.md](Readme_active_directory_doc.md): Active Directory / LDAP authentication implementation.
- [Readme_active_directory_flow.md](Readme_active_directory_flow.md): authentication and Active Directory notes for the UI.
- [Readme_auth_flow.md](Readme_auth_flow.md): MFA authentication, UI integration guide.
- [password_reset.md](password_reset.md): resetting a user password through the API or console email flow.
- [cli/README.md](cli/README.md): the ngencerf command-line client.

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

# Configure the database

PostgreSQL remains the default, supported, and tested database. 
See your administrator for instructions on installing it locally. 
Connection values are set in `.env` (`CERF_SERVER_DATABASE_HOST`, `CERF_SERVER_DATABASE_USER`, and so on; see `settings.py`). 
A local PostgreSQL server without TLS needs `CERF_SERVER_DATABASE_SSLMODE=disable`.

The database backend is selected with `CERF_SERVER_DATABASE_ENGINE`. 
Its default remains:

```text
CERF_SERVER_DATABASE_ENGINE=django.db.backends.postgresql
```

PostgreSQL has no required extensions, and any recent version should work. Everything the server needs from PostgreSQL is listed in
[Readme_supporting_services.md](Readme_supporting_services.md).

For lightweight local development, SQLite can be used without installing or running a database server:

```text
CERF_SERVER_DATABASE_ENGINE=django.db.backends.sqlite3
CERF_SERVER_DATABASE_NAME=/absolute/path/to/ngencerf.sqlite3
```

If `CERF_SERVER_DATABASE_NAME` is omitted while SQLite is selected, the
database file defaults to `db.sqlite3` in the repository root. The PostgreSQL
host, port, user, password, SSL, connection-timeout, and statement-timeout
settings are ignored in SQLite mode. `runCerf.sh` applies the same Django
migrations and initialization commands to the selected database.

SQLite is intended for local development and testing. PostgreSQL remains the
production database. Other Django database backends may be selected through
`CERF_SERVER_DATABASE_ENGINE`, but they require the appropriate Python driver
and may require additional backend-specific settings or testing.

# Configure the cache

Redis remains the default cache and is required for production because Gunicorn
workers must share cached values. Point the server at Redis with `REDIS_URL` in
`.env`. The cache is non-persistent, and `runCerf.sh` clears it at every start.

For single-process local development without Gunicorn, Redis can be avoided by
setting this in `.env`:

```text
CERF_SERVER_CACHE_BACKEND=django.core.cache.backends.locmem.LocMemCache
```

Django's local-memory cache is private to each process. Do not use it with
Gunicorn or any deployment that runs more than one server process.

The file `redis/redis.conf.dev` is a ready-made configuration for a local `redis-server`. Everything the server needs
from Redis is listed in [Readme_supporting_services.md](Readme_supporting_services.md).

# Create data directory

Create a directory that will hold the data.  It can be anything, such as `~/ngwpc/data`.  
The server looks for it at `CONTAINER_DATA_ROOT`, an environment variable read by `settings.py` that defaults to `/ngencerf/data`.
You have two options:

1. Keep the default and create a symbolic link so `/ngencerf/data` points at your directory (commands below), or
2. Set `CONTAINER_DATA_ROOT` and `HOST_DATA_ROOT` in `cerfServer/.env` to your directory and skip the link
   (see [Directory structure](#directory-structure) and [Readme_portable_deployment.md](Readme_portable_deployment.md)).

For option 1, enter these commands to create the top-level `/ngencerf` directory and then create the symbolic link

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

By convention with the Docker images, `CONTAINER_DATA_ROOT` is `/ngencerf/data`. It is an environment variable read by `settings.py`
(default `/ngencerf/data`), together with `HOST_DATA_ROOT`, the same directory as seen by whatever launches the jobs
(the Docker host in DOCKER mode, the compute node in SLURM mode; defaults to `CONTAINER_DATA_ROOT`).
The server and the job runtime must agree on `CONTAINER_DATA_ROOT`, and it must not change on a deployment that already
has runs, because stored run paths embed it. See [Readme_portable_deployment.md](Readme_portable_deployment.md) for running without mounts.

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
values are baked in as defaults, so **no `--env-file` is needed**. Make sure the
data directory exists (by default the `/ngencerf/data` symlink, see [Create data directory](#create-data-directory))
and that its `ngen-static-files` directory is populated (see [Static Files](#static-files)).

The compose file is for development only (production is covered in the note at the end of this section).
Its bind mounts exist because ngenCERF is a distributed system: the Django server and the jobs it launches run as
separate processes (on separate machines under Slurm) and exchange large run directories through a shared directory
tree, so that tree cannot be private to any one container. Every host-side path in `compose.yaml` is a variable with
the historical default:

| Variable | Default | Mounted at (inside the container) |
|---|---|---|
| `NGEN_CAL_DATA_PATH` | `/ngencerf/data/` | `CONTAINER_DATA_ROOT` (default `/ngencerf/data`); also passed to the server as `HOST_DATA_ROOT` |
| `NGENCERF_INIT_PATH` | `../data/.ngencerf-init` | `/ngencerf/ngencerf-server/.init/` |
| `NGENCERF_LOGS_PATH` | `../logs/ngencerf-server` | `/ngencerf/ngencerf-server/logs/` |
| `POSTGRES_DATA_PATH` | `../data/db` | `/var/lib/postgresql/data` (the dev `db` service) |

For example: `NGEN_CAL_DATA_PATH=$HOME/ngwpc/data NGENCERF_LOGS_PATH=/var/log/ngencerf docker compose up ngencerf-services`.
Running without bind mounts, without Docker, or on a plain Linux host is covered in
[Readme_portable_deployment.md](Readme_portable_deployment.md).

```
CACHE_BUST=$(date +%s) docker compose up --build ngencerf-services
```

The server comes up at http://localhost:8000 and Postgres at localhost:5432.

> **Port conflict:** the `db` container binds host port **5432**. If you also run Postgres on the host (common if you switch between host and containerized Postgres), free the port first — e.g. `sudo systemctl stop postgresql` — or the `db` container won't start.

- **Force a rebuild** (to pick up code changes): keep `--build`, or run `docker compose build --no-cache ngencerf-services`.
- **Force a static-data reload:** static data loads once on first start, tracked by `../data/.ngencerf-init/.load_static`. Delete that file to reload on the next start.
- **Shell into the running container:** `docker exec -it $(docker ps -qf name=ngencerf-services) bash`.

> Parallel Works production deploys from the `development-pw` branch, which carries its own `production-pw.yaml` + `cerfServer/.env-override`. AWS deployments inject configuration through ECS task definitions.
