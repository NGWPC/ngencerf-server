# Supporting services

What the ngenCERF server requires from its database and cache. The default
services are PostgreSQL and Redis. This is written for whoever provides them,
whether that is a developer's laptop, the AWS deployment (RDS and ElastiCache,
created by the `nwm-ngencerf-infra` repository), or a Parallel Works cluster
(both run in containers next to the server). In the reference deployments both
services are dedicated to ngenCERF; if an administrator provides shared
instances instead, the requirements below are the complete list.

The environment variables named here are described in full in
`ngenCERF_Server_Configuration_Reference.md`.

# Database

**Required.** PostgreSQL is the default, supported, and tested database.
The backend is selected by `CERF_SERVER_DATABASE_ENGINE`, whose default remains `django.db.backends.postgresql` using the psycopg 3 driver.

SQLite is available for lightweight local development by setting the engine to `django.db.backends.sqlite3`. 
Other Django database backends require their corresponding Python driver and may need additional backend-specific settings.

## PostgreSQL requirements

What the server needs from it:

- Any recent PostgreSQL major version. Development uses 16 (`compose.yaml`),
  AWS runs RDS PostgreSQL 16. Nothing version-specific is used.
- One database and one role that owns it. The server runs Django migrations at
  every start (`runCerf.sh` calls `manage.py migrate`), so the role must be
  able to create and alter tables in that database. No superuser rights.
- No extensions, no raw SQL, no PostgreSQL-only field types: the schema is
  plain Django migrations.
- Network access from the server to the database port, and TLS according to
  `CERF_SERVER_DATABASE_SSLMODE` below.

What is stored there: all application data, user accounts, and Django
sessions (`django.contrib.sessions`, database backend). Redis holds none of
it.

Connection settings, all read from the environment:

| Variable                               | Default                        | Meaning                                                                                                                                   |
| -------------------------------------- | ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `CERF_SERVER_DATABASE_ENGINE`          | `django.db.backends.postgresql` | Django database backend                                                                                                                   |
| `CERF_SERVER_DATABASE_HOST`            | `localhost`                    | Host name of the database server                                                                                                          |
| `CERF_SERVER_DATABASE_PORT`            | `5432`                         | Port                                                                                                                                      |
| `CERF_SERVER_DATABASE_NAME`            | `postgres`                     | Database name                                                                                                                             |
| `CERF_SERVER_DATABASE_USER`            | `postgres`                     | Role the server connects as                                                                                                               |
| `CERF_SERVER_DATABASE_PASSWORD`        | `postgres`                     | Its password (a secret in any real deployment)                                                                                            |
| `CERF_SERVER_DATABASE_SSLMODE`         | `require`                      | libpq `sslmode`. `require` refuses a server without TLS; use `disable` for a local Postgres, `verify-full` with a CA bundle in production |
| `CERF_SERVER_DATABASE_SSLROOTCERT`     | unset                          | CA bundle path for `verify-ca` / `verify-full` (the production image bakes the AWS RDS bundle at `/ngencerf/aws_cert/global-bundle.pem`)  |
| `CERF_SERVER_DATABASE_CONNECT_TIMEOUT` | `10`                           | Seconds to wait for a connection                                                                                                          |
| `CERF_SERVER_DATABASE_OPTIONS`         | `-c statement_timeout=10000ms` | libpq options string; the default aborts any statement longer than 10 seconds                                                             |
| `CERF_SERVER_DATABASE_CONN_MAX_AGE`    | `60`                           | Seconds a connection is reused (Django `CONN_MAX_AGE`)                                                                                    |

First start against an empty database: `runCerf.sh` applies the migrations,
creates the superuser named by `DJANGO_SUPERUSER_EMAIL` /
`DJANGO_SUPERUSER_PASSWORD` if it does not exist, seeds the reference tables
(`manage.py init_sql`), and loads the gage data (`manage.py init_gages`).
Nothing has to be created by hand beyond the empty database and the role.

## SQLite for local development

SQLite does not require a separate database service or credentials. 
Configure it in `cerfServer/.env` with:

```text
CERF_SERVER_DATABASE_ENGINE=django.db.backends.sqlite3
CERF_SERVER_DATABASE_NAME=/absolute/path/to/ngencerf.sqlite3
```

If the name is omitted, the SQLite file defaults to `db.sqlite3` in the repository root. 
The containing directory must exist and be writable by the
server process. PostgreSQL-only connection variables are ignored, including
host, port, user, password, SSL, connect timeout, and libpq options.

`runCerf.sh` applies the normal Django migrations and initialization commands
to SQLite. SQLite is useful for development and basic testing, but it has not
been qualified for production or for the concurrency of a deployed ngenCERF
server. PostgreSQL remains the production database.

# Redis

**Required, as a cache only.** The server uses django-redis for Django's
cache framework and for nothing else: no sessions, no queues, no pub/sub.

What the server needs from it:

- A reachable Redis instance, any recent version. Development runs 7.2
  (`compose.yaml`), AWS runs ElastiCache Redis 7.1. Nothing version-specific
  is used.
- No persistence. The contents are disposable: `runCerf.sh` runs
  `manage.py clear_cache` at every server start, and some cached entries
  (the About page git information, for example) have no expiry, so a restart
  that skips the flush can serve stale values. Turn persistence off or leave
  it on, the server does not care.
- One instance, or at least one database index, per server deployment. Two
  servers sharing an index would share cache keys.
- Optional TLS (`rediss://`) and optional password authentication, both
  expressed in the URL.

Connection setting:

| Variable | Default | Meaning |
|---|---|---|
| `REDIS_URL` | `redis://127.0.0.1:6379/1` | Full connection URL including the database index; `rediss://host:6379/1` for TLS (AWS), `redis://:password@host:6379/1` for password auth |

Configuration files shipped in this repository, for running Redis yourself:

- `redis/redis.conf.dev`: a ready-made configuration for a local
  `redis-server` on a developer machine. Binds to `127.0.0.1` only, protected
  mode on, no persistence (`save ""`, `appendonly no`), no daemon, log to
  stdout.
- `redis/redis.conf.prod`: the same settings but bound to all interfaces with
  protected mode off. It is used by the `redis` service in the development
  `compose.yaml`, which mounts it read-only, and it is only safe on a private
  container network. It is not used on AWS, where ElastiCache is configured by
  the infrastructure repository.

# Other provisioning files in this repository

None of these are needed to configure the database or Redis; they are listed so
that an administrator knows what they are.

- `gunicorn_conf.py`: Gunicorn hooks used when the server starts under
  Gunicorn (`CERF_ASGI=1`); `runCerf.sh` passes it with `--config`.
- `logrotate-ngencerf.dev.template`: a logrotate template for the two
  development log files (`logs/ngencerf.log`, `logs/ngencerf_db.log`).
- `cleanup-archived-pending-delete-cron.prod`: a sample cron line for the
  Parallel Works controller that retries deleting quarantined archived run
  directories. It is a sample only; nothing in this repository installs it.
- `cerfserver.env` and `cerfserver-docker.env`: startup defaults sourced by
  `runCerf.sh` on a host and inside the image respectively (see the
  configuration reference).
