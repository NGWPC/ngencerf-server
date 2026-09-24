# Podman Support (Additive Path)

This repository maintains Docker as its primary documented and production CI path. Podman is supported as an **additional** option for local development, rootless execution, and container build/smoke verification.

Existing Docker workflows (`.github/workflows/cicd.yml`) and production release tags remain untouched and active.

---

## Prerequisites

Verify that Podman is installed on your workstation:

```bash
podman version
podman info
```

For Ubuntu 24.04+ (Noble) or RHEL 8/9, Podman 4.9+ is recommended.

---

## Building with Podman

Build the server image directly using the existing `Dockerfile`. Following NOAA-OWP/WRES conventions, use `--format docker` to ensure standard OCI/Docker compatibility:

```bash
podman build \
  --ulimit nofile=65535:65535 \
  --format docker \
  -f Dockerfile \
  -t local/ngencerf-server:podman-test \
  .
```

*Note: The Dockerfile uses BuildKit syntax (`# syntax=docker/dockerfile:1.4`) and `--mount=type=cache` for pip caching. Modern Podman (via Buildah $\ge$ 1.24) natively resolves cache mounts locally without requiring a Docker daemon. The `--ulimit nofile=65535:65535` flag ensures sufficient file descriptors are available while building Python C extensions (GDAL, Fiona, Shapely).*

---

## Smoke Verification

### 1. Test Entrypoint & Django Management CLI
```bash
# Verify runCerf.sh entrypoint help (exits 0)
podman run --rm local/ngencerf-server:podman-test --help

# Verify manage.py dispatch through runCerf.sh (exits 0)
podman run --rm local/ngencerf-server:podman-test manage --help
```

### 2. Verify Python Environment & Dependencies
Test that Python 3.12 and core packages (`django`, `cerfServer`, `mswm`, `data_assimilation_engine`, `ewts`) are functional:
```bash
podman run --rm --entrypoint python local/ngencerf-server:podman-test --version
podman run --rm --entrypoint python local/ngencerf-server:podman-test \
  -c "import django, cerfServer, mswm, data_assimilation_engine, ewts; print('Packages healthy')"
```

### 3. Verify Provenance Metadata & Prebuilt Templates
```bash
podman run --rm --entrypoint test local/ngencerf-server:podman-test -s /ngencerf/ngencerf-server/ngencerf-server_git_info.json
podman run --rm --entrypoint test local/ngencerf-server:podman-test -d /ngencerf/prebuilt/bmi_forcing_templates
```

---

## Runtime Engine Configuration (`CONTAINER_CLI`)

When `JOB_EXECUTION_MODE=DOCKER` is used (local development or standalone instance deployments), `ngencerf-server` launches containerized calibration, forecast, and verification jobs.

The server natively supports both Docker and Podman through auto-detection and environment overrides:

* **Auto-Detection:** If `docker` is available on the `PATH`, `CONTAINER_CLI` defaults to `docker` (preserving existing developer workflows). If only `podman` is present, it automatically defaults to `podman`.
* **Explicit Override:** You can explicitly select the container engine by setting `CONTAINER_CLI=podman` in your `.env` or `cerfserver.env`:
  ```bash
  CONTAINER_CLI=podman
  ```
* **SELinux Relabeling (`CONTAINER_VOLUME_FLAGS`):** On SELinux-enforcing hosts (such as RHEL, Rocky, or AL2023), rootless Podman requires the `:Z` flag on bind-mounted directories so the container process has read/write access. Set:
  ```bash
  CONTAINER_VOLUME_FLAGS=:Z
  ```
  This automatically appends `:Z` to worker container data volume mounts (`-v /ngencerf/data:/ngencerf/data:Z`), eliminating permission errors without needing `sudo`.
* **No `docker` Alias Required:** `ngencerf-server` directly invokes the configured `CONTAINER_CLI` for job execution (`run`), cancellation (`kill`), and metadata extraction (`create`, `cp`, `rm`), so customers do not need to install `podman-docker` or set up shell aliases.

---

## Compose & SELinux Considerations

When using `podman compose` with `compose.yaml`:
* **SELinux Relabeling:** On SELinux-enforcing hosts (RHEL / Fedora), bind mounts declared in `compose.yaml` (such as `../data/db` and `./redis/redis.conf.prod`) require the `:Z` (private unshared) or `:z` (shared) volume mount flag so rootless containers have access.
* To validate compose structure:
  ```bash
  podman compose -f compose.yaml config
  ```

---

## CI / Automation

* **Workflow:** `.github/workflows/podman-smoke.yml`
* **Triggers:** Manual (`workflow_dispatch`) and automated checks on pull requests modifying server files (`Dockerfile`, `requirements.txt`, `runCerf.sh`, `manage.py`, `cerfServer/**`, `calibration/**`, `gunicorn_conf.py`, `compose.yaml`).
* **Runner Environment:** Pinned to `ubuntu-24.04`.
* **Registry Policy:** By default, builds remain local to the runner. When `push_images=true` is dispatched, only `:podman-test` and `:<sha>-podman-test` tags are published to GHCR. Production aliases (`:latest`, release tags) are never touched.
