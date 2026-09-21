# Portable deployment

How to run the ngenCERF server without container bind mounts, without Docker,
or on a plain Linux host, and what cannot be removed.

# The one hard requirement

ngenCERF is a distributed system. The Django server prepares a run directory,
launches a job, and later reads the job's output; the job runs as a separate
process (a container on the same host in DOCKER mode, an Apptainer image on a
compute node in SLURM mode). Both sides must see the same directory tree at
the same path:

- `CONTAINER_DATA_ROOT` is the path the server reads and writes under, and the
  path the job runtime must see the same data at. The server writes absolute
  paths under this root into job configs and into the database.
- `HOST_DATA_ROOT` is the same tree as seen by whatever launches the job (the
  Docker host, or the compute node). It defaults to `CONTAINER_DATA_ROOT`.

Anything that satisfies "same tree, same path on both sides" works: one
machine and one directory, a bind mount, a shared filesystem (EFS on AWS, the
cluster filesystem on Parallel Works). Nothing in the server assumes which of
those you use. What cannot be removed is the shared tree itself: the jobs
produce gigabytes of output the server must read back, and they do not
communicate any other way.

# Every path is a setting

| Setting | Read by | Default | Notes |
|---|---|---|---|
| `CONTAINER_DATA_ROOT` | `settings.py`, `runCerf.sh`, `compose.yaml` | `/ngencerf/data` | Must be identical for the server and the job runtime. Do not change it on a deployment that already has runs. |
| `HOST_DATA_ROOT` | `settings.py` | `CONTAINER_DATA_ROOT` | Only differs when the jobs run on another machine or the host path differs from the container path. |
| `SINGULARITY_DIR` | `settings.py` | `/ngencerf/containers` | Slurm mode only; where the server reads the `.sif` images for the About page. |
| `RUN_CERF_FLAG_DIRECTORY` | `runCerf.sh` | `./` (image: `/ngencerf/ngencerf-server/.init`) | Small marker files that stop first-boot work from re-running. Must persist across restarts. |
| `NGENCERF_TEMP_DIR` | `settings.py` | Python's `tempfile.gettempdir()` (`TMPDIR` if set, else `/tmp`) | Base for the server's own temporary files (the ZIP download workspace, the S3 download fallback). Set it where `/tmp` is unavailable, read-only, or too small. Created at startup if missing. |
| `NGEN_CAL_DATA_PATH`, `NGENCERF_INIT_PATH`, `NGENCERF_LOGS_PATH`, `POSTGRES_DATA_PATH` | `compose.yaml` only | see README | Host side of the dev-compose bind mounts (server data, init, logs, and the dev Postgres data directory). |
| `CAL_MGR_DOCKER_CMD`, `NGEN_FORECAST_DOCKER_CMD`, `NWM_EVAL_DOCKER_CMD` | `settings.py` | `docker run ...` | Job launcher templates for DOCKER mode. Override to change the image reference, add flags, or use another container runtime. |

The full attribute tables are in `ngenCERF_Server_Configuration_Reference.md`.

# Option A: server as a plain process on a Linux host (no Docker, no mounts)

This is the normal development setup and it is fully supported today. The
server runs directly on the machine through `runCerf.sh`; only the jobs use a
container runtime (see Option C for jobs without Docker).

Prerequisites, derived from what the server image installs (`Dockerfile`).
Package names are Debian/Ubuntu; map them to your distribution:

- Python 3.12 (the version `cerfserver.env` pins in `REQUIRED_PYTHON`; NumPy 1.x caps it there)
- PostgreSQL (any recent version) and Redis (see the README sections "Install Postgres" and "Install Redis")
- `git`, `curl`, `ca-certificates`, `jq`
- build tools for the Python packages: `gcc`, `g++`, `make`, `pkg-config`, `libpq-dev`
- GDAL/PROJ for GeoPandas/Fiona: `gdal-bin`, `libgdal-dev`, `libproj-dev`, `proj-data`

Setup:

1. Clone this repository and copy `cerfServer/__.env` to `cerfServer/.env`.
2. Pick a data directory, for example `/srv/ngencerf/data`, and set both roots
   to it in `cerfServer/.env`:

   ```
   CONTAINER_DATA_ROOT=/srv/ngencerf/data
   HOST_DATA_ROOT=/srv/ngencerf/data
   ```

   No symlink and no mount is needed. (Leaving both unset and creating the
   `/ngencerf/data` symlink from the README is the other way to get the same
   result.)
3. Populate `<CONTAINER_DATA_ROOT>/ngen-static-files` as described in the
   README section "Static Files".
4. Run `./runCerf.sh`. On a host it creates a virtual environment next to the
   repo, installs the requirements and the Git-hosted dependencies, sources
   `cerfserver.env`, `cerfServer/.env` and `cerfServer/.env-override`, runs
   the migrations, loads the gage data, clones `bmi_forcing_templates` into
   the static directory, and starts the Django development server (or
   Gunicorn when `CERF_ASGI=1`). Marker files go to `RUN_CERF_FLAG_DIRECTORY`
   (default `./`, the repo directory).

Jobs in this setup run in DOCKER mode by default (`JOB_EXECUTION_MODE=DOCKER`
in `.env`): the server runs `docker run -v <HOST_DATA_ROOT>:<CONTAINER_DATA_ROOT> nwm-cal-mgr ...`
for each job, so Docker is required for the jobs, not for the server. With both
roots equal that bind is a plain directory mapping on the local machine.

# Option B: server in a container without bind mounts

Every path the container needs is a setting, so nothing forces a bind mount.
Give the container its own storage instead:

- Put the data tree on a container-managed volume (`docker volume create`,
  or the equivalent in Podman or Kubernetes) mounted at `CONTAINER_DATA_ROOT`,
  or simply create the directory inside the container's filesystem.
- Do the same for the init directory (`RUN_CERF_FLAG_DIRECTORY`, which needs
  to survive restarts) and, if you want the log files outside the container,
  the logs directory (`/ngencerf/ngencerf-server/logs`).
- Pass `CONTAINER_DATA_ROOT` and `HOST_DATA_ROOT` (and `RUN_CERF_FLAG_DIRECTORY`
  if you moved it) in the container environment. The image's own defaults are
  guarded, so values from the environment win.
- If `/tmp` inside the container is unavailable or read-only, set
  `NGENCERF_TEMP_DIR` to a writable directory; the server keeps its own
  temporary files there.

The consequence is the hard requirement above: the jobs must run in that same
filesystem. A job launched by `docker run` on the host cannot see a directory
that exists only inside the server container, so this option needs a shared
volume that both the server container and the job containers mount.

The dev `compose.yaml` keeps bind mounts because they are the simplest thing
for a developer machine, but each host path is a variable (see the README
section "Run the server in Docker"), so it can be pointed anywhere.

# Option C: jobs without Docker

The model workloads (nwm-cal-mgr, nwm-fcst-mgr, nwm-eval-mgr, each built on
ngen) are delivered as container images and as Apptainer `.sif` files. The
server has three job modes: `DOCKER`, `SLURM`, and `SLURM_MOCK` (debug only,
runs nothing). None of them runs a workload as a plain host process.

The supported way to run jobs without Docker is Apptainer under Slurm, which
is what the AWS and Parallel Works deployments run. Apptainer (formerly
Singularity) is rootless, has no daemon, is standard on HPC systems and
installable on any Linux distribution, and it uses a plain directory bind
(`-B <HOST_DATA_ROOT>:<CONTAINER_DATA_ROOT>`), not an overlay. Settings:
`JOB_EXECUTION_MODE=SLURM`, the `SLURM_REST_*` variables, the three
`*_SINGULARITY_CONTAINER_PATH` variables (compute-node paths to the `.sif`
files), `HOST_DATA_ROOT` set to the compute-node path of the shared tree, and
`SINGULARITY_DIR` to where the server can read the same `.sif` files.

In DOCKER mode the launcher itself is configuration: each `*_DOCKER_CMD`
template can be overridden through the environment to use a different image
reference, extra flags, or another container runtime such as `podman run`
(keep `{name}` in it, cancellation calls `docker kill <name>`).

# What cannot be removed

The shared directory tree between the server and the jobs. Every option above
is a different way of providing it; none of them removes it. If the goal is a
standalone evaluation mode with no job execution at all, `SLURM_MOCK` starts
the server without launching anything, but it is restricted to
`DJANGO_DEBUG=true`.
