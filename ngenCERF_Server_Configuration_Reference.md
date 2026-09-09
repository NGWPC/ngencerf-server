# Configuration Reference

## ngenCERF Server

### Scope

This reference covers configuration owned or consumed by the `cerfServer` repository, excluding the separately packaged `cli` application. It includes:

- Django and ngenCERF runtime environment variables and settings.
- Server startup variables and flags from `runCerf.sh` and the server environment files.
- AWS/ECS runtime inputs from `django.tf`.
- Image build arguments from `Dockerfile.production-pw`.
- Hardcoded settings that define externally relevant behavior.

Values supplied only by AWS/ECS itself are identified as platform-provided. Source file paths and line numbers were accurate for the supplied source snapshot, but line numbers may drift as the source files change.

### Configuration precedence

For Django settings, existing process environment variables take precedence. `cerfServer/settings.py` then loads `cerfServer/.env`, followed by `version.env`, using `python-dotenv` without overriding values already present. For local development (the non-Docker path in `runCerf.sh`), the script sources `cerfserver.env`, then `cerfServer/.env`, then `cerfServer/.env-override`; later files can override earlier shell values. In AWS production, `django.tf` supplies environment variables and secret references through the ECS task definition.

### Legend

- **Required:** The server or the named feature cannot operate correctly without a valid value.
- **Conditional:** Required only when the associated feature or execution mode is enabled.
- **Optional:** A usable default exists or the feature is intentionally disabled when omitted.
- **Runtime change:** Environment-only means the container/process must be restarted but the image does not need rebuilding. Build-time means the image must be rebuilt. Code means a source change and redeployment are required.

## Django runtime environment variables

### Core application and security

#### `DJANGO_DEBUG`

Enables Django debug behavior and controls the default for file logging.

| Attribute | Value |
|---|---|
| Type | Boolean string |
| Default Value | `true` |
| Whether It Is Required or Optional | Optional; must be `false` in production |
| Example Values | `false` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:40` |
| What Breaks If It Is Missing | Server starts in debug mode, exposing unsafe development behavior. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default is hardcoded in `settings.py`; AWS sets `False` in `django.tf`. |

#### `CERF_SERVER_SECRET_KEY`

Django cryptographic signing key.

| Attribute | Value |
|---|---|
| Type | String |
| Default Value | `not-so-secret-key` |
| Whether It Is Required or Optional | Required in every deployed environment |
| Example Values | Random high-entropy string |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | **Secret** |
| Where It Is Read in Code | `cerfServer/settings.py:68` |
| What Breaks If It Is Missing | Server starts with a known insecure key; signed data and tokens are unsafe. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Insecure fallback is hardcoded in `settings.py`; AWS injects a Secrets Manager value. |

#### `ALLOWED_HOSTS`

Comma-separated hostnames accepted in the HTTP `Host` header.

| Attribute | Value |
|---|---|
| Type | CSV string |
| Default Value | `.localhost,127.0.0.1` |
| Whether It Is Required or Optional | Required outside local development |
| Example Values | `api.example.gov,internal-alb.example` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:129-136` |
| What Breaks If It Is Missing | Requests for unlisted hosts return HTTP 400 `DisallowedHost`. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Local defaults are hardcoded; AWS adds the ALB name and configured hosts. |

#### `ECS_CONTAINER_METADATA_URI_V4`

ECS-provided metadata endpoint used to add the task private IPv4 address to `ALLOWED_HOSTS`.

| Attribute | Value |
|---|---|
| Type | URL |
| Default Value | None |
| Whether It Is Required or Optional | Optional; platform-provided on ECS |
| Example Values | `http://169.254.170.2/v4/...` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | Sensitive infrastructure metadata |
| Where It Is Read in Code | `cerfServer/settings.py:142-155` |
| What Breaks If It Is Missing | Startup continues; direct ALB health checks may fail if the task IP is not otherwise allowed. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Platform-managed |
| Whether It Is Hardcoded Anywhere; If So, Where? | Behavior and one-second timeout are hardcoded. |

#### `CORS_ALLOWED_ORIGINS`

Comma-separated browser origins permitted by Django CORS middleware.

| Attribute | Value |
|---|---|
| Type | CSV of absolute origins |
| Default Value | `http://localhost:3000` |
| Whether It Is Required or Optional | Required when UI origin differs from local default |
| Example Values | `https://cerf.example.gov` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:158-165` |
| What Breaks If It Is Missing | The localhost development allowlist is used. Cross-origin browser requests from any other UI origin are blocked. The current same-origin AWS deployment is unaffected. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Local UI origin is hardcoded. Not set in the supplied `django.tf`. |

#### `CSRF_TRUSTED_ORIGINS`

Comma-separated origins trusted for state-changing browser requests such as administrative or session-based POST requests.

| Attribute | Value |
|---|---|
| Type | CSV of absolute origins |
| Default Value | Empty list |
| Whether It Is Required or Optional | Conditional; required when the application is exposed through a public HTTPS origin that differs from Django's direct request origin |
| Example Values | `https://ngencerf.example.gov` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:171-178` |
| What Breaks If It Is Missing | Django rejects affected state-changing browser requests from an untrusted public origin. Environments without a separate public HTTPS origin are unaffected. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | The empty default is hardcoded. `django.tf` conditionally sets the configured public URL when `var.public_url` is not empty. |

#### `TRUST_X_FORWARDED_PROTO`

Makes Django trust a front-end proxy's `X-Forwarded-Proto` header and treat requests marked as HTTPS as secure.

| Attribute | Value |
|---|---|
| Type | Boolean string |
| Default Value | `false` |
| Whether It Is Required or Optional | Conditional; required when TLS terminates at a trusted proxy and Django receives HTTP from that proxy |
| Example Values | `true` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | Security-sensitive |
| Where It Is Read in Code | `cerfServer/settings.py:180-188` |
| What Breaks If It Is Missing | Django may generate HTTP redirects or absolute URLs and may not treat proxied requests as secure. Direct HTTP and non-proxied environments are unaffected. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | The `false` default and trusted header mapping are hardcoded. `django.tf` conditionally sets `true` when `var.public_url` is not empty. |

#### `MFA_ENABLED`

Enables mandatory MFA policy and enrollment flow.

| Attribute | Value |
|---|---|
| Type | Boolean string |
| Default Value | `false` |
| Whether It Is Required or Optional | Optional |
| Example Values | `true` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | Security-sensitive |
| Where It Is Read in Code | `cerfServer/settings.py:190`; `calibration/auth_mfa/policy.py` |
| What Breaks If It Is Missing | Password-only authentication remains enabled. Existing MFA data remains stored but is not globally required. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default is hardcoded; AWS conditionally sets `true`. |

#### `ACTIVE_DIRECTORY_ENABLED`

Enables Active Directory authentication.

| Attribute | Value |
|---|---|
| Type | Boolean string |
| Default Value | `false` |
| Whether It Is Required or Optional | Optional |
| Example Values | `true` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | Security-sensitive |
| Where It Is Read in Code | `cerfServer/settings.py:192`; AD authentication backend |
| What Breaks If It Is Missing | Authentication falls back to local Django users. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default is hardcoded; AWS conditionally sets `true`. |

#### `PORT`

Server port and implicit port appended to `NGENCERF_BASE_URL`.

| Attribute | Value |
|---|---|
| Type | Integer, 1-65535 |
| Default Value | `8000` |
| Whether It Is Required or Optional | Required by `runCerf.sh`; optional to Django alone |
| Example Values | `8000`, `443` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:770`; `runCerf.sh:43,93-96,1098` |
| What Breaks If It Is Missing | Django uses 8000, but startup script exits if its environment file leaves it empty. Invalid values stop startup. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default 8000 is present in `settings.py`, `cerfserver.env`, ECS port mapping, and load balancer configuration. |

#### `NGENCERF_BASE_URL`

Public/internal API base used for Slurm and manager callbacks. Missing scheme is normalized to HTTP; missing port uses `PORT`.

| Attribute | Value |
|---|---|
| Type | URL |
| Default Value | `localhost:8000/api` |
| Whether It Is Required or Optional | Conditional; required and externally reachable for Slurm callbacks |
| Example Values | `http://internal-alb:80/api` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:772-777`; generated input and Slurm callback code |
| What Breaks If It Is Missing | Local default is used; remote jobs cannot call back successfully. Invalid URL stops startup. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Local URL is hardcoded; AWS constructs ALB URL with `/api`. |


### Release and UI metadata

#### `NGENCERF_VERSION`

Server release version displayed by the landing/about API.

| Attribute | Value |
|---|---|
| Type | String |
| Default Value | `<unknown>`; supplied `version.env` contains `2.0.0` |
| Whether It Is Required or Optional | Optional operational metadata |
| Example Values | `2.0.0` |
| Whether It Is Environment-Specific | No |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:42`; landing view |
| What Breaks If It Is Missing | UI/API reports an unknown version. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only, or rebuild if baked into image |
| Whether It Is Hardcoded Anywhere; If So, Where? | Fallback is hardcoded; snapshot value is in `version.env`. |

#### `NGENCERF_DATE`

Release date displayed by the landing/about API.

| Attribute | Value |
|---|---|
| Type | Date-like string |
| Default Value | `<unknown>`; supplied `version.env` contains `2026-08-31` |
| Whether It Is Required or Optional | Optional operational metadata |
| Example Values | `2026-08-31` |
| Whether It Is Environment-Specific | No |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:43`; landing view |
| What Breaks If It Is Missing | UI/API reports an unknown date. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only, or rebuild if baked into image |
| Whether It Is Hardcoded Anywhere; If So, Where? | Fallback is hardcoded; snapshot value is in `version.env`. |

#### `CONTACT_EMAIL`

Support/contact address displayed by the landing/about API.

| Attribute | Value |
|---|---|
| Type | Email string |
| Default Value | `<unknown>`; empty in supplied `version.env` |
| Whether It Is Required or Optional | Optional, but should be set for users |
| Example Values | `support@example.gov` |
| Whether It Is Environment-Specific | Possibly |
| Whether It Is Secret or Sensitive | Personal/contact information |
| Where It Is Read in Code | `cerfServer/settings.py:44`; landing view |
| What Breaks If It Is Missing | UI displays an unknown or blank contact. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Fallback is hardcoded. |

#### `NGENCERF_UI_TAG`

Tag used to identify the ngenCERF UI Docker image.

| Attribute | Value |
|---|---|
| Type | String |
| Default Value | `latest` |
| Whether It Is Required or Optional | Optional |
| Example Values | `2.0.0`, `sha-abc123` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:48`; Git-information utility |
| What Breaks If It Is Missing | Mutable `latest` tag is assumed when this setting is used. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default `latest` is hardcoded. It is not set in the supplied `django.tf`. |

#### `NGENCERF_UI_URL`

Base URL of the running UI service, used to locate UI build metadata.

| Attribute | Value |
|---|---|
| Type | URL |
| Default Value | `http://localhost:3000` |
| Whether It Is Required or Optional | Conditional; needed for UI Git information in Slurm/Fargate mode |
| Example Values | `http://internal-alb` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:52-55`; `calibration/util/git_util.py` |
| What Breaks If It Is Missing | UI Git information cannot be retrieved remotely; local URL is attempted. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Local URL is hardcoded; AWS uses ALB default route. |

#### `NGENCERF_UI_GIT_INFO_URL`

Direct URL of the UI build-time Git-information JSON file.

| Attribute | Value |
|---|---|
| Type | URL |
| Default Value | `${NGENCERF_UI_URL}/ngencerf-ui_git_info.json` |
| Whether It Is Required or Optional | Optional override |
| Example Values | `https://ui.example/ngencerf-ui_git_info.json` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:59-62`; `calibration/util/git_util.py` |
| What Breaks If It Is Missing | Derived URL is used. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Filename and derivation are hardcoded. |


### Active Directory and LDAP

#### `LDAP_DOMAIN`

AD DNS domain and fallback LDAP host source.

| Attribute | Value |
|---|---|
| Type | DNS name |
| Default Value | `nextgenwaterprediction.com` |
| Whether It Is Required or Optional | Conditional when AD enabled |
| Example Values | `corp.example.gov` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | Sensitive infrastructure data |
| Where It Is Read in Code | `cerfServer/settings.py:195` |
| What Breaks If It Is Missing | Default NOAA domain is used and may point to the wrong directory. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default is hardcoded. |

#### `LDAP_SERVER_URI`

LDAP/LDAPS service URI.

| Attribute | Value |
|---|---|
| Type | URI |
| Default Value | `ldap://${LDAP_DOMAIN}` |
| Whether It Is Required or Optional | Required when AD enabled |
| Example Values | `ldaps://ad.example.gov` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | Sensitive infrastructure data |
| Where It Is Read in Code | `cerfServer/settings.py:198`; AD service |
| What Breaks If It Is Missing | AD login fails if the derived or supplied endpoint is unreachable. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | URI derivation is hardcoded; AWS conditionally supplies it. |

#### `LDAP_USER_SEARCH_BASE_DN`

Base distinguished name for user searches.

| Attribute | Value |
|---|---|
| Type | LDAP DN |
| Default Value | `DC=nextgenwaterprediction,DC=com` |
| Whether It Is Required or Optional | Required when AD enabled |
| Example Values | `DC=corp,DC=example,DC=gov` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | Sensitive directory structure |
| Where It Is Read in Code | `cerfServer/settings.py:201-204`; AD service |
| What Breaks If It Is Missing | Users outside the default DN cannot be found. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | NOAA DN is hardcoded; supplied AWS file does not override it. |

#### `LDAP_BIND_DN`

Service account DN used for LDAP searches.

| Attribute | Value |
|---|---|
| Type | LDAP DN |
| Default Value | Empty |
| Whether It Is Required or Optional | Conditional; required when anonymous bind is not allowed |
| Example Values | `CN=svc-ngencerf,OU=Service Accounts,DC=...` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | Sensitive identifier |
| Where It Is Read in Code | `cerfServer/settings.py:206`; AD service |
| What Breaks If It Is Missing | Directory bind/search fails in typical AD configurations. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Empty fallback is hardcoded; AWS conditionally supplies it. |

#### `LDAP_BIND_PASSWORD`

Password for the LDAP bind account.

| Attribute | Value |
|---|---|
| Type | String |
| Default Value | Empty |
| Whether It Is Required or Optional | Conditional; required with `LDAP_BIND_DN` |
| Example Values | Secret value |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | **Secret** |
| Where It Is Read in Code | `cerfServer/settings.py:207`; AD service |
| What Breaks If It Is Missing | LDAP bind and AD authentication fail. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Empty fallback is hardcoded; AWS injects Secrets Manager JSON key `password`. |

#### `LDAP_USE_SSL`

Enables LDAP SSL behavior. Must agree with `LDAP_SERVER_URI`.

| Attribute | Value |
|---|---|
| Type | Boolean string |
| Default Value | `false` |
| Whether It Is Required or Optional | Optional but security-critical |
| Example Values | `true` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | Security-sensitive |
| Where It Is Read in Code | `cerfServer/settings.py:211`; AD service |
| What Breaks If It Is Missing | Unencrypted LDAP behavior is used. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default false is hardcoded. |

#### `LDAP_TIMEOUT`

LDAP network timeout in seconds.

| Attribute | Value |
|---|---|
| Type | Integer |
| Default Value | `10` |
| Whether It Is Required or Optional | Optional |
| Example Values | `5`, `30` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:213`; AD service |
| What Breaks If It Is Missing | Ten-second timeout is used; invalid integer stops startup. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default is hardcoded. |

#### `LDAP_SYSTEM_NAME`

Environment name used to derive authorized AD group names.

| Attribute | Value |
|---|---|
| Type | Lowercase string |
| Default Value | `local` |
| Whether It Is Required or Optional | Required when AD enabled |
| Example Values | `dev`, `uat`, `prod` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | Sensitive authorization configuration |
| Where It Is Read in Code | `cerfServer/settings.py:215-217`; AD service |
| What Breaks If It Is Missing | Required groups become `ngencerf-local-users` and `ngencerf-local-admins`, likely denying intended users. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Group patterns are hardcoded as `ngencerf-{system}-users/admins`. |


### Database and cache

#### `CERF_SERVER_DATABASE_NAME`

PostgreSQL database name.

| Attribute | Value |
|---|---|
| Type | String |
| Default Value | `postgres` |
| Whether It Is Required or Optional | Required outside default local database |
| Example Values | `ngencerf` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:962` |
| What Breaks If It Is Missing | Connects to database `postgres`; application migrations/data may be absent. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default in settings/local settings; AWS sets `ngencerf`. |

#### `CERF_SERVER_DATABASE_USER`

PostgreSQL login role.

| Attribute | Value |
|---|---|
| Type | String |
| Default Value | `postgres` |
| Whether It Is Required or Optional | Required outside local development |
| Example Values | `ngencerf` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | Sensitive identifier |
| Where It Is Read in Code | `cerfServer/settings.py:963` |
| What Breaks If It Is Missing | Attempts privileged/default `postgres` login and normally fails. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default in settings/local settings; AWS sets `ngencerf`. |

#### `CERF_SERVER_DATABASE_PASSWORD`

PostgreSQL password.

| Attribute | Value |
|---|---|
| Type | String |
| Default Value | `postgres` |
| Whether It Is Required or Optional | Required outside local development |
| Example Values | Secret value |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | **Secret** |
| Where It Is Read in Code | `cerfServer/settings.py:964` |
| What Breaks If It Is Missing | Authentication normally fails; insecure default may work locally. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Insecure fallback exists in source; AWS injects a Secrets Manager value. |

#### `CERF_SERVER_DATABASE_HOST`

PostgreSQL hostname.

| Attribute | Value |
|---|---|
| Type | Hostname/IP |
| Default Value | `localhost` |
| Whether It Is Required or Optional | Required when database is remote |
| Example Values | RDS endpoint |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | Sensitive infrastructure data |
| Where It Is Read in Code | `cerfServer/settings.py:965` |
| What Breaks If It Is Missing | Attempts local PostgreSQL and fails in normal containers. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default is hardcoded; AWS supplies RDS address. |

#### `CERF_SERVER_DATABASE_PORT`

PostgreSQL TCP port.

| Attribute | Value |
|---|---|
| Type | Integer |
| Default Value | `5432` |
| Whether It Is Required or Optional | Optional |
| Example Values | `5432` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:966` |
| What Breaks If It Is Missing | Standard PostgreSQL port is used; invalid integer stops startup. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default is hardcoded. |

#### `CERF_SERVER_DATABASE_CONN_MAX_AGE`

Django persistent connection lifetime in seconds.

| Attribute | Value |
|---|---|
| Type | Integer |
| Default Value | `60` |
| Whether It Is Required or Optional | Optional |
| Example Values | `0`, `60`, `300` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:967` |
| What Breaks If It Is Missing | Connections persist for 60 seconds; invalid integer stops startup. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default is hardcoded. |

#### `CERF_SERVER_DATABASE_CONNECT_TIMEOUT`

PostgreSQL connection timeout in seconds.

| Attribute | Value |
|---|---|
| Type | Integer |
| Default Value | `10` |
| Whether It Is Required or Optional | Optional |
| Example Values | `5`, `30` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:946` |
| What Breaks If It Is Missing | Ten-second timeout is used; invalid integer stops startup. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default is hardcoded. |

#### `CERF_SERVER_DATABASE_OPTIONS`

libpq connection options; default applies a statement timeout.

| Attribute | Value |
|---|---|
| Type | String |
| Default Value | `-c statement_timeout=10000ms` |
| Whether It Is Required or Optional | Optional |
| Example Values | `-c statement_timeout=30000ms` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:947-950` |
| What Breaks If It Is Missing | Queries retain ten-second statement timeout. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default is hardcoded. |

#### `CERF_SERVER_DATABASE_SSLMODE`

PostgreSQL SSL mode.

| Attribute | Value |
|---|---|
| Type | libpq SSL mode string |
| Default Value | `require` |
| Whether It Is Required or Optional | Optional; should remain secure in production |
| Example Values | `verify-full`, `require`, `disable` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | Security-sensitive |
| Where It Is Read in Code | `cerfServer/settings.py:951` |
| What Breaks If It Is Missing | TLS is required but server identity is not verified. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default `require` is hardcoded. |

#### `CERF_SERVER_DATABASE_SSLROOTCERT`

Path to trusted PostgreSQL/RDS CA bundle.

| Attribute | Value |
|---|---|
| Type | File path |
| Default Value | None |
| Whether It Is Required or Optional | Conditional for `verify-ca`/`verify-full` |
| Example Values | `/ngencerf/aws_cert/global-bundle.pem` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:954-957` |
| What Breaks If It Is Missing | No CA path is passed; behavior depends on SSL mode/system trust. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only if file already exists; otherwise image or mount change |
| Whether It Is Hardcoded Anywhere; If So, Where? | RDS certificate directory is baked into production image. |

#### `REDIS_URL`

Django Redis cache connection URL and database number.

| Attribute | Value |
|---|---|
| Type | Redis URL |
| Default Value | `redis://127.0.0.1:6379/1` |
| Whether It Is Required or Optional | Required when Redis is remote |
| Example Values | `rediss://cache.example:6379/1` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | May contain credentials; sensitive |
| Where It Is Read in Code | `cerfServer/settings.py:242-250` |
| What Breaks If It Is Missing | Attempts local Redis; cache-backed operations fail if unavailable. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Local URL is hardcoded; AWS uses ElastiCache TLS URL. |


### Enterprise data and object storage

#### `ENTERPRISE_DATA_URL`

Base URL for hydrofabric, streamflow observations, and module metadata services.

| Attribute | Value |
|---|---|
| Type | URL |
| Default Value | None |
| Whether It Is Required or Optional | Required for gage/data-service workflows |
| Example Values | `https://edfs.example.gov/` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | Sensitive infrastructure data |
| Where It Is Read in Code | `cerfServer/settings.py:315`; `calibration/views/data_services.py` |
| What Breaks If It Is Missing | Data service URL construction/fetches fail; supplied Terraform notes an invalid-environment error. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Endpoint suffixes are hardcoded in `settings.py`; AWS supplies base URL. |

#### `ENTERPRISE_DATA_ENV`

MSWM enterprise-data environment selector.

| Attribute | Value |
|---|---|
| Type | Enum-like string |
| Default Value | None |
| Whether It Is Required or Optional | Required for data-service workflows |
| Example Values | `test`, `oe` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:316`; `calibration/views/data_services.py` |
| What Breaks If It Is Missing | Environment validation or downstream MSWM requests fail. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | No fallback; AWS supplies Terraform variable. |

#### `NGENCERF_ARCHIVE_S3_PATH`

S3 URI/prefix holding archived run directories.

| Attribute | Value |
|---|---|
| Type | S3 URI/prefix |
| Default Value | None |
| Whether It Is Required or Optional | Required for archive/restore features |
| Example Values | `s3://bucket/env/archives/` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | Sensitive infrastructure data |
| Where It Is Read in Code | `cerfServer/settings.py:326`; landing/archive views |
| What Breaks If It Is Missing | Server starts, but archive listing, archive, restore, and cleanup features fail or report not configured. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | No application default; AWS supplies Terraform variable. |

#### `NGENCERF_ZIPS_S3_PATH`

S3 URI/prefix holding generated downloadable ZIP files.

| Attribute | Value |
|---|---|
| Type | S3 URI/prefix |
| Default Value | None |
| Whether It Is Required or Optional | Required for S3-backed download ZIPs |
| Example Values | `s3://bucket/env/zips/` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | Sensitive infrastructure data |
| Where It Is Read in Code | `cerfServer/settings.py:329`; download/cloud utilities |
| What Breaks If It Is Missing | ZIP upload/download workflow fails or cannot provide URLs. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | No application default; AWS supplies Terraform variable. |

#### `NGENCERF_RW_PROFILE`

Optional named AWS profile for read/write S3 operations. Empty selects the default AWS credential chain/task role.

| Attribute | Value |
|---|---|
| Type | String |
| Default Value | None |
| Whether It Is Required or Optional | Optional; normally omitted on ECS |
| Example Values | `ngwpc-sandbox` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | Sensitive identifier |
| Where It Is Read in Code | `cerfServer/settings.py:333`; cloud utilities |
| What Breaks If It Is Missing | Default credential chain is used. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | `None` behavior is hardcoded. |


### Data paths, execution mode, and Slurm

#### `HOST_DATA_ROOT`

Host/compute-node path corresponding to container `/ngencerf/data`; used for Docker mounts and Slurm path translation.

| Attribute | Value |
|---|---|
| Type | Directory path |
| Default Value | `/ngencerf/data` |
| Whether It Is Required or Optional | Conditional; required when host path differs, especially PCS |
| Example Values | `/ngencerf-app/data/ngen-cal-data` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | Sensitive infrastructure path |
| Where It Is Read in Code | `cerfServer/settings.py:364`; execution adapters |
| What Breaks If It Is Missing | Local-equivalent path is used; jobs cannot find shared input/output when host mount differs. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Container root is hardcoded; AWS supplies compute-node path. |

#### `JOB_EXECUTION_MODE`

Selects job adapter. Accepted names are defined by `JobExecutionMode` (including `DOCKER`, `SLURM`, and `SLURM_MOCK`).

| Attribute | Value |
|---|---|
| Type | Enum name, case-sensitive |
| Default Value | `DOCKER` |
| Whether It Is Required or Optional | Required to use Slurm |
| Example Values | `SLURM` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:555-568` |
| What Breaks If It Is Missing | Docker adapter is used. Invalid value exits startup; `SLURM_MOCK` with debug false raises an error. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default is hardcoded; AWS derives value from `enable_pcs`. |

#### `SLURM_NODE_TYPE_RULES`

Ordered JSON rules mapping maximum catchment count to Slurm partition/node type. Final rule must use `-1`.

| Attribute | Value |
|---|---|
| Type | JSON array of `[int,string]` pairs |
| Default Value | `[[500,"c5n-9xlarge"],[-1,"r8a-12xlarge"]]` |
| Whether It Is Required or Optional | Conditional for Slurm sizing |
| Example Values | `[[250,"small"],[-1,"large"]]` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:381-438`; input builder |
| What Breaks If It Is Missing | Invalid JSON/rules stop startup. Missing uses AWS-instance-type defaults that may not match cluster partitions. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default partitions are hardcoded; not set in supplied `django.tf`. |

#### `MPI_NODE_RULES`

Ordered JSON rules mapping maximum catchment count to MPI node count. Final rule must use `-1`.

| Attribute | Value |
|---|---|
| Type | JSON array of `[int,int]` pairs |
| Default Value | `[[15,1],[50,2],[250,4],[500,6],[1000,10],[1500,12],[-1,18]]` |
| Whether It Is Required or Optional | Conditional for job sizing |
| Example Values | `[[100,1],[-1,4]]` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:487-550`; input builder |
| What Breaks If It Is Missing | Invalid JSON/rules stop startup; missing uses hardcoded scaling values. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | The default rule set is hardcoded in `settings.py`. AWS overrides it in `django.tf`, changing the 251-500 catchment band from 6 nodes to 5. |

#### `SLURM_REST_ENDPOINT`

Base URL of `slurmrestd`.

| Attribute | Value |
|---|---|
| Type | URL |
| Default Value | Empty |
| Whether It Is Required or Optional | Required when `JOB_EXECUTION_MODE=SLURM` |
| Example Values | `http://10.0.0.10:6820` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | Sensitive infrastructure data |
| Where It Is Read in Code | `cerfServer/settings.py:461`; `job_executor_slurm.py` |
| What Breaks If It Is Missing | Slurm submissions, queries, and cancellations fail. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Empty fallback; AWS derives from PCS endpoint. |

#### `SLURM_API_VERSION`

Slurm REST API version included in request paths.

| Attribute | Value |
|---|---|
| Type | Version string |
| Default Value | `v0.0.43` |
| Whether It Is Required or Optional | Conditional for Slurm |
| Example Values | `v0.0.43` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:462`; Slurm adapter |
| What Breaks If It Is Missing | Default is used; mismatch causes REST 404/schema failures. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default is hardcoded and repeated in AWS config. |

#### `SLURM_JWT_SECRET_ARN`

Secrets Manager ARN of PCS Slurm JWT signing key.

| Attribute | Value |
|---|---|
| Type | ARN |
| Default Value | Empty |
| Whether It Is Required or Optional | Required for PCS Slurm authentication |
| Example Values | `arn:aws:secretsmanager:...:secret:...` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | **Secret reference/sensitive** |
| Where It Is Read in Code | `cerfServer/settings.py:463`; Slurm adapter |
| What Breaks If It Is Missing | JWT cannot be signed; Slurm REST calls fail authentication. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Empty fallback; AWS derives from PCS cluster. |

#### `SLURM_REST_USER`

POSIX username claim placed in Slurm JWT/header.

| Attribute | Value |
|---|---|
| Type | String |
| Default Value | `root` |
| Whether It Is Required or Optional | Conditional for Slurm |
| Example Values | `root`, `ngencerf` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | Security-sensitive |
| Where It Is Read in Code | `cerfServer/settings.py:464`; Slurm adapter |
| What Breaks If It Is Missing | Default root identity is used. Incorrect value causes authorization or ownership problems. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default root is hardcoded and repeated in AWS. |

#### `SLURM_REST_UID`

POSIX UID claim used for Slurm REST requests.

| Attribute | Value |
|---|---|
| Type | Integer |
| Default Value | `0` |
| Whether It Is Required or Optional | Conditional for Slurm |
| Example Values | `0`, `1001` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | Security-sensitive |
| Where It Is Read in Code | `cerfServer/settings.py:465`; Slurm adapter |
| What Breaks If It Is Missing | UID 0 is used; invalid integer stops startup. Incorrect value causes authorization/ownership problems. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default is hardcoded and repeated in AWS. |

#### `SLURM_REST_GID`

POSIX GID claim used for Slurm REST requests.

| Attribute | Value |
|---|---|
| Type | Integer |
| Default Value | `0` |
| Whether It Is Required or Optional | Conditional for Slurm |
| Example Values | `0`, `1001` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | Security-sensitive |
| Where It Is Read in Code | `cerfServer/settings.py:466`; Slurm adapter |
| What Breaks If It Is Missing | GID 0 is used; invalid integer stops startup. Incorrect value causes authorization/ownership problems. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default is hardcoded and repeated in AWS. |

#### `SLURM_REST_TOKEN_TTL_SECONDS`

Lifetime of each signed Slurm REST token.

| Attribute | Value |
|---|---|
| Type | Integer seconds |
| Default Value | `600` |
| Whether It Is Required or Optional | Optional Slurm tuning |
| Example Values | `300`, `600` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | Security-sensitive |
| Where It Is Read in Code | `cerfServer/settings.py:467`; Slurm adapter |
| What Breaks If It Is Missing | Ten-minute tokens are used; invalid integer stops startup. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default is hardcoded; omitted from supplied AWS task config. |

#### `SLURM_REST_JOB_ENVIRONMENT`

JSON array of `KEY=VALUE` strings exported to Slurm jobs; must be non-empty for `slurmrestd`.

| Attribute | Value |
|---|---|
| Type | JSON string array |
| Default Value | Standard system `PATH` and `HOME=/root` |
| Whether It Is Required or Optional | Conditional for Slurm |
| Example Values | `["PATH=/opt/aws/pcs/...:/bin","HOME=/root"]` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | Can be sensitive if secrets are added |
| Where It Is Read in Code | `cerfServer/settings.py:468-473`; Slurm adapter |
| What Breaks If It Is Missing | Default environment is used; malformed JSON stops startup. Missing required scheduler path can prevent commands from running. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default is hardcoded; AWS overrides PATH for PCS 25.11. |

#### `NWM_CAL_MGR_SINGULARITY_CONTAINER_PATH`

Compute-node path to calibration manager SIF.

| Attribute | Value |
|---|---|
| Type | File path |
| Default Value | None |
| Whether It Is Required or Optional | Required for calibration/validation in Slurm mode |
| Example Values | `/ngencerf-app/singularity/nwm-cal-mgr.sif` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | Sensitive infrastructure path |
| Where It Is Read in Code | `cerfServer/settings.py:605-607` |
| What Breaks If It Is Missing | Generated command contains `None`; calibration and validation jobs fail. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only if image exists |
| Whether It Is Hardcoded Anywhere; If So, Where? | No default; AWS supplies this value. |

#### `NWM_FCST_MGR_SINGULARITY_CONTAINER_PATH`

Compute-node path to forecast manager SIF.

| Attribute | Value |
|---|---|
| Type | File path |
| Default Value | None |
| Whether It Is Required or Optional | Required for cold-start, forecast, and hindcast in Slurm mode |
| Example Values | `/ngencerf-app/singularity/nwm-fcst-mgr.sif` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | Sensitive infrastructure path |
| Where It Is Read in Code | `cerfServer/settings.py:609-611` |
| What Breaks If It Is Missing | Generated command contains `None`; forecast-family jobs fail. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only if image exists |
| Whether It Is Hardcoded Anywhere; If So, Where? | No application default; AWS supplies the stable SIF symlink path. |

#### `NWM_EVAL_SINGULARITY_CONTAINER_PATH`

Compute-node path to evaluation manager SIF.

| Attribute | Value |
|---|---|
| Type | File path |
| Default Value | None |
| Whether It Is Required or Optional | Required for verification in Slurm mode |
| Example Values | `/ngencerf-app/singularity/nwm-eval-mgr.sif` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | Sensitive infrastructure path |
| Where It Is Read in Code | `cerfServer/settings.py:613-615` |
| What Breaks If It Is Missing | Generated command contains `None`; verification jobs fail. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only if image exists |
| Whether It Is Hardcoded Anywhere; If So, Where? | No application default; AWS supplies the stable SIF symlink path. |

### Logging

All log-level variables accept only `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`, case-insensitively. An invalid value stops startup.

#### `NGENCERF_ROOT_LOG_LEVEL`

Root Python logger threshold.

| Attribute | Value |
|---|---|
| Type | Log-level enum |
| Default Value | `INFO` |
| Whether It Is Required or Optional | Optional |
| Example Values | `WARNING` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:797` |
| What Breaks If It Is Missing | INFO threshold is used. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default hardcoded. |

#### `NGENCERF_LOG_LEVEL`

Default handler threshold and fallback for calibration/server loggers.

| Attribute | Value |
|---|---|
| Type | Log-level enum |
| Default Value | `DEBUG` |
| Whether It Is Required or Optional | Optional |
| Example Values | `INFO` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:798` |
| What Breaks If It Is Missing | DEBUG handler threshold is used, potentially producing verbose logs. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default hardcoded. |

#### `NGENCERF_DJANGO_LOG_LEVEL`

Django, Djoser, SimpleJWT, and DB retry logger level.

| Attribute | Value |
|---|---|
| Type | Log-level enum |
| Default Value | `INFO` |
| Whether It Is Required or Optional | Optional |
| Example Values | `WARNING` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:799` |
| What Breaks If It Is Missing | INFO threshold is used. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default hardcoded. |

#### `NGENCERF_DJANGO_REQUEST_LOG_LEVEL`

`django.request` logger level.

| Attribute | Value |
|---|---|
| Type | Log-level enum |
| Default Value | Value of `NGENCERF_DJANGO_LOG_LEVEL` |
| Whether It Is Required or Optional | Optional |
| Example Values | `ERROR` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:800` |
| What Breaks If It Is Missing | Django logger level is inherited. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Derivation hardcoded. |

#### `NGENCERF_DATABASE_LOG_LEVEL`

Django database backend logger and database log-file level.

| Attribute | Value |
|---|---|
| Type | Log-level enum |
| Default Value | `WARNING` |
| Whether It Is Required or Optional | Optional |
| Example Values | `ERROR` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:801` |
| What Breaks If It Is Missing | WARNING threshold is used. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default hardcoded. |

#### `NGENCERF_CALIBRATION_LOG_LEVEL`

`calibration` and `cerfServer` application logger level.

| Attribute | Value |
|---|---|
| Type | Log-level enum |
| Default Value | Value of `NGENCERF_LOG_LEVEL` |
| Whether It Is Required or Optional | Optional |
| Example Values | `INFO` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:802` |
| What Breaks If It Is Missing | Default handler level is inherited. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Derivation hardcoded. |

#### `NGENCERF_LOG_TO_FILE`

Enables local `logs/ngencerf.log` and `logs/ngencerf_db.log` in addition to console logging.

| Attribute | Value |
|---|---|
| Type | Boolean string |
| Default Value | Same as `DJANGO_DEBUG` |
| Whether It Is Required or Optional | Optional |
| Example Values | `false` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:810-812` |
| What Breaks If It Is Missing | File logging follows debug setting. In production, console-only output is expected for CloudWatch. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default relationship and file paths are hardcoded. |

#### `GUNICORN_LOGLEVEL`

Gunicorn/Uvicorn logger threshold after handlers are attached to Django logging.

| Attribute | Value |
|---|---|
| Type | Gunicorn log-level string |
| Default Value | `info` |
| Whether It Is Required or Optional | Optional |
| Example Values | `warning`, `debug` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `gunicorn_conf.py:43` |
| What Breaks If It Is Missing | INFO is used. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default hardcoded. |


## Startup environment variables and command flags

In `runCerf.sh`, **Docker** means the production server is running inside the Docker container built by `Dockerfile.production-pw`. **Non-Docker** means a local development environment. Development-only controls such as the local virtual-environment path, required local Python version, and Python executable are not production deployment inputs; the production image establishes those values and dependencies during the Docker build. `Dockerfile.production-pw` copies `cerfserver-docker.env` into the image as `cerfserver.env` and uses `runCerf.sh` as the container entry point.

### `CERF_VENV`

Local development virtual-environment base path. In production, `Dockerfile.production-pw` installs the Python environment and copies a server environment file that sets this value to the literal `Docker`; operators do not configure a virtual environment at container startup.

| Attribute | Value |
|---|---|
| Type | Path or enum string |
| Default Value | `./.venv-cerf` in `cerfserver.env`; `Docker` in Docker env |
| Whether It Is Required or Optional | Required for local development. Preconfigured by the production Docker image. |
| Example Values | `./.venv-cerf`, `Docker` |
| Whether It Is Environment-Specific | Yes; development path versus production Docker marker |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `runCerf.sh:44-45,98-131` |
| What Breaks If It Is Missing | In development, virtual-environment setup fails or startup exits. In production, omitting the image-provided `Docker` value makes `runCerf.sh` follow the development setup path inside the container. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Development: environment file. Production: supplied by the image and should be changed through the Docker build. |
| Whether It Is Hardcoded Anywhere; If So, Where? | Development default is in `cerfserver.env`. `Dockerfile.production-pw` copies `cerfserver-docker.env`, where the value is `Docker`, into the production image. |

### `REQUIRED_PYTHON`

Required Python major/minor version for local development startup. Production Python is installed by `Dockerfile.production-pw`; this variable is not used to select or install Python in the running production container.

| Attribute | Value |
|---|---|
| Type | Version string |
| Default Value | `3.12` |
| Whether It Is Required or Optional | Required for development only |
| Example Values | `3.12`, `python3.12` |
| Whether It Is Environment-Specific | Development only |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `runCerf.sh:46,107-130` |
| What Breaks If It Is Missing | Local development startup derives an invalid interpreter name and fails. Production is unaffected because Docker startup skips local interpreter validation. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Development: environment file. Production Python changes require rebuilding the image. |
| Whether It Is Hardcoded Anywhere; If So, Where? | Snapshot value in `cerfserver.env`. |

### `PYTHON_BIN`

Optional explicit Python executable for local development. Production uses the Python executable installed into the image by `Dockerfile.production-pw`.

| Attribute | Value |
|---|---|
| Type | Executable name/path |
| Default Value | `python${REQUIRED_PYTHON}` |
| Whether It Is Required or Optional | Optional development override |
| Example Values | `/usr/bin/python3.12` |
| Whether It Is Environment-Specific | Development only |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `runCerf.sh:110-130` |
| What Breaks If It Is Missing | Development derives the executable from `REQUIRED_PYTHON`; startup fails if that executable is unavailable or has the wrong version. Production is unaffected. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Development: environment-only. Production Python executable changes require rebuilding the image. |
| Whether It Is Hardcoded Anywhere; If So, Where? | Derivation hardcoded. |

### `RUN_CERF_FLAG_DIRECTORY`

Persistent directory for initialization, fingerprint, and dependency SHA marker files.

| Attribute | Value |
|---|---|
| Type | Directory path |
| Default Value | `./`; Docker uses `/ngencerf/ngencerf-server/.init` |
| Whether It Is Required or Optional | Required for persistent, predictable initialization state |
| Example Values | `/ngencerf/ngencerf-server/.init` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `runCerf.sh:220-258` |
| What Breaks If It Is Missing | Defaults to current directory; startup exits if directory cannot be created. Ephemeral path causes repeated initialization. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only/mount change |
| Whether It Is Hardcoded Anywhere; If So, Where? | Defaults and marker filenames are hardcoded. |

### `DJANGO_SUPERUSER_EMAIL`

Email for automatically bootstrapped Django administrator.

| Attribute | Value |
|---|---|
| Type | Email string |
| Default Value | `admin@nextgenwaterprediction.com` in supplied env files |
| Whether It Is Required or Optional | Optional bootstrap input |
| Example Values | `admin@example.gov` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | Sensitive identifier |
| Where It Is Read in Code | `runCerf.sh:549-567` |
| What Breaks If It Is Missing | Automatic superuser creation is skipped. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only; only affects creation when account absent |
| Whether It Is Hardcoded Anywhere; If So, Where? | **A production-looking default account name is committed.** |

### `DJANGO_SUPERUSER_PASSWORD`

Password for automatically bootstrapped Django administrator.

| Attribute | Value |
|---|---|
| Type | String |
| Default Value | `admin` in supplied env files |
| Whether It Is Required or Optional | Optional in code, but secret if bootstrap is used |
| Example Values | Secret value |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | **Secret** |
| Where It Is Read in Code | `runCerf.sh:550-567` |
| What Breaks If It Is Missing | Automatic superuser creation is skipped. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only; only affects creation when account absent |
| Whether It Is Hardcoded Anywhere; If So, Where? | **Insecure plaintext default `admin` is committed in two env files.** |

### `CERF_ASGI`

When `1`, starts Gunicorn with Uvicorn workers.

| Attribute | Value |
|---|---|
| Type | `0`/`1` |
| Default Value | `0` in Docker env; AWS sets `1` |
| Whether It Is Required or Optional | Optional |
| Example Values | `1` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `runCerf.sh:1073-1080` |
| What Breaks If It Is Missing | Falls back to production flag or Django development server. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default in Docker env. |

### `CERF_PRODUCTION`

General production indicator; when `1`, selects ASGI/Gunicorn startup.

| Attribute | Value |
|---|---|
| Type | `0`/`1` |
| Default Value | `0` in Docker env; AWS sets `1` |
| Whether It Is Required or Optional | Optional |
| Example Values | `1` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `runCerf.sh:1074-1080` |
| What Breaks If It Is Missing | Development server may be selected unless `CERF_ASGI=1`. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default in Docker env. |

### `GUNICORN_WORKERS`

Number of Gunicorn worker processes.

| Attribute | Value |
|---|---|
| Type | Positive integer |
| Default Value | Calculated as `min(max((CPU*2)+1,2),8)`; Docker/AWS set `24` |
| Whether It Is Required or Optional | Optional |
| Example Values | `8`, `24` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `runCerf.sh:1082-1095` |
| What Breaks If It Is Missing | The calculated value, with a minimum of 2 and maximum of 8, is used. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Docker/AWS hardcode 24. |

### `GUNICORN_TIMEOUT`

Worker timeout in seconds.

| Attribute | Value |
|---|---|
| Type | Integer seconds |
| Default Value | `120` |
| Whether It Is Required or Optional | Optional |
| Example Values | `120`, `300` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `runCerf.sh:1097,1108` |
| What Breaks If It Is Missing | 120 seconds is used. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default hardcoded; not supplied by AWS. |

### `GUNICORN_BIND`

Gunicorn bind address.

| Attribute | Value |
|---|---|
| Type | Host:port string |
| Default Value | `0.0.0.0:${PORT}` |
| Whether It Is Required or Optional | Optional |
| Example Values | `127.0.0.1:8000`, `0.0.0.0:8000` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `runCerf.sh:1098,1107` |
| What Breaks If It Is Missing | All interfaces on `PORT` are used. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Binding behavior hardcoded. |

### `GUNICORN_MAX_REQUESTS`

Requests handled before recycling a worker.

| Attribute | Value |
|---|---|
| Type | Integer |
| Default Value | `300` |
| Whether It Is Required or Optional | Optional |
| Example Values | `1000` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `runCerf.sh:1104` |
| What Breaks If It Is Missing | Workers recycle after 300 requests. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default hardcoded and repeated in AWS/Docker env. |

### `GUNICORN_MAX_REQUESTS_JITTER`

Random jitter added to worker recycle threshold.

| Attribute | Value |
|---|---|
| Type | Integer |
| Default Value | `100` |
| Whether It Is Required or Optional | Optional |
| Example Values | `50`, `100` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `runCerf.sh:1105` |
| What Breaks If It Is Missing | Up to 100 requests of jitter is used. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default hardcoded and repeated in AWS/Docker env. |

### `GUNICORN_GRACEFUL_TIMEOUT`

Grace period for workers to finish during restart/shutdown.

| Attribute | Value |
|---|---|
| Type | Integer seconds |
| Default Value | Application fallback `30`; AWS production value `120` |
| Whether It Is Required or Optional | Optional |
| Example Values | `120` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `runCerf.sh:1109` |
| What Breaks If It Is Missing | Gunicorn uses the 30-second application fallback. AWS production supplies 120 seconds. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | The 30-second fallback is hardcoded in `runCerf.sh`; `django.tf` explicitly supplies the 120-second AWS production value. |

### `FORCE_REINSTALL_VCS`

Forces reinstall of Git-sourced Python packages during local development startup. Production dependencies are installed by `Dockerfile.production-pw`, so this variable does not alter an already-built production container.

| Attribute | Value |
|---|---|
| Type | `0`/`1` |
| Default Value | `0` |
| Whether It Is Required or Optional | Optional development control |
| Example Values | `1` |
| Whether It Is Environment-Specific | Development only |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `runCerf.sh:682+` |
| What Breaks If It Is Missing | Nothing; development SHA-marker logic decides whether to reinstall. Production is unaffected. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default hardcoded. |

### `AWS_PROFILE`, `AWS_REGION`, standard AWS credential variables

Standard AWS SDK/CLI credential and region inputs used indirectly by boto3/AWS CLI outside ECS task-role operation.

| Attribute | Value |
|---|---|
| Type | Strings |
| Default Value | Standard AWS provider chain |
| Whether It Is Required or Optional | Conditional for local AWS access |
| Example Values | `AWS_PROFILE=ngwpc-sandbox`, `AWS_REGION=us-east-1` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | **Credentials are secret when explicit keys/tokens are used** |
| Where It Is Read in Code | `calibration/util/cloud_util.py`; early `aws sts` check in `runCerf.sh` |
| What Breaks If It Is Missing | Local S3/Secrets operations fail when no usable profile/credentials/region can be resolved. ECS uses task role and platform region. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Environment-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Names/precedence belong to AWS SDK; no explicit profile/region is set in supplied AWS task. |

### `--load-gages`

Forces `init_gages` and refreshes its marker/fingerprint.

| Attribute | Value |
|---|---|
| Type | Startup CLI flag |
| Default Value | Off |
| Whether It Is Required or Optional | Optional |
| Example Values | `./runCerf.sh --load-gages` |
| Whether It Is Environment-Specific | No |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `runCerf.sh:653-662,875-978` |
| What Breaks If It Is Missing | Gages initialize only when marker is absent or fingerprint changes. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Invocation-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Flag name and marker behavior hardcoded. |

### `auto_reload`

Enables Django development auto-reloader.

| Attribute | Value |
|---|---|
| Type | Startup positional flag |
| Default Value | Off |
| Whether It Is Required or Optional | Optional development flag |
| Example Values | `./runCerf.sh auto_reload` |
| Whether It Is Environment-Specific | Development only |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `runCerf.sh:653-662,1114-1119` |
| What Breaks If It Is Missing | Server runs with `--noreload` in development. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Invocation-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Token spelling hardcoded. |

### `activate`

Sources/activates the selected local virtual environment and returns.

| Attribute | Value |
|---|---|
| Type | Startup subcommand |
| Default Value | None |
| Whether It Is Required or Optional | Optional development subcommand |
| Example Values | `source ./runCerf.sh activate` |
| Whether It Is Environment-Specific | Development only |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `runCerf.sh:28-29,66-69,188-191` |
| What Breaks If It Is Missing | Normal startup proceeds. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Invocation-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Subcommand hardcoded. |

### `manage`

Runs a Django management command through the configured environment.

| Attribute | Value |
|---|---|
| Type | Startup subcommand |
| Default Value | None |
| Whether It Is Required or Optional | Optional |
| Example Values | `./runCerf.sh manage migrate` |
| Whether It Is Environment-Specific | No |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `runCerf.sh:30-32,631-636` |
| What Breaks If It Is Missing | Normal startup proceeds. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Invocation-only |
| Whether It Is Hardcoded Anywhere; If So, Where? | Subcommand hardcoded. |


## Hardcoded Django and application settings

These values define behavior externally but currently cannot be configured through environment variables.

### `EMAIL_BACKEND`

Django email delivery backend.

| Attribute | Value |
|---|---|
| Type | Import path |
| Default Value | Console backend |
| Whether It Is Required or Optional | Required for email features |
| Example Values | SMTP backend |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:25` |
| What Breaks If It Is Missing | Django default SMTP behavior could be attempted; current console backend means mail is logged, not delivered. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes. |

### `TOKEN_MODEL`

Disables DRF token model in favor of JWT/stateless use.

| Attribute | Value |
|---|---|
| Type | Null/import path |
| Default Value | `None` |
| Whether It Is Required or Optional | Required by selected auth design |
| Example Values | Token model path |
| Whether It Is Environment-Specific | No |
| Whether It Is Secret or Sensitive | Security-sensitive |
| Where It Is Read in Code | `cerfServer/settings.py:93` |
| What Breaks If It Is Missing | Authentication semantics change. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes. |

### `REST_FRAMEWORK`

Default authentication, permission, and schema classes.

| Attribute | Value |
|---|---|
| Type | Mapping |
| Default Value | Authenticated-only; JWT then token auth |
| Whether It Is Required or Optional | Required |
| Example Values | Django REST Framework settings |
| Whether It Is Environment-Specific | No |
| Whether It Is Secret or Sensitive | Security-sensitive |
| Where It Is Read in Code | `cerfServer/settings.py:95-102` |
| What Breaks If It Is Missing | Framework defaults may expose or reject endpoints differently. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes. |

### `SPECTACULAR_SETTINGS`

OpenAPI title, description, version, and schema serving behavior.

| Attribute | Value |
|---|---|
| Type | Mapping |
| Default Value | Title `NgenCerf`; version `1.0.0`; schema excluded from served docs |
| Whether It Is Required or Optional | Optional metadata |
| Example Values | OpenAPI metadata |
| Whether It Is Environment-Specific | No |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:104-109` |
| What Breaks If It Is Missing | drf-spectacular defaults apply. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes. API version is independent of `NGENCERF_VERSION`. |

### `DJOSER`

User/password-reset behavior and serializers.

| Attribute | Value |
|---|---|
| Type | Mapping |
| Default Value | No activation/confirmation email; password retype; update last login |
| Whether It Is Required or Optional | Required for auth behavior |
| Example Values | Djoser settings |
| Whether It Is Environment-Specific | No |
| Whether It Is Secret or Sensitive | Security-sensitive |
| Where It Is Read in Code | `cerfServer/settings.py:254-265` |
| What Breaks If It Is Missing | Djoser defaults change account and reset behavior. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes. |

### `SIMPLE_JWT.ACCESS_TOKEN_LIFETIME`

JWT access-token lifetime.

| Attribute | Value |
|---|---|
| Type | Duration |
| Default Value | 15 minutes |
| Whether It Is Required or Optional | Required |
| Example Values | `5 minutes`, `1 hour` |
| Whether It Is Environment-Specific | Possibly |
| Whether It Is Secret or Sensitive | Security-sensitive |
| Where It Is Read in Code | `cerfServer/settings.py:268-276` |
| What Breaks If It Is Missing | SimpleJWT default applies if removed. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes. |

### `SIMPLE_JWT.REFRESH_TOKEN_LIFETIME`

JWT refresh-token lifetime.

| Attribute | Value |
|---|---|
| Type | Duration |
| Default Value | 1 day |
| Whether It Is Required or Optional | Required |
| Example Values | `1 day`, `7 days` |
| Whether It Is Environment-Specific | Possibly |
| Whether It Is Secret or Sensitive | Security-sensitive |
| Where It Is Read in Code | `cerfServer/settings.py:268-276` |
| What Breaks If It Is Missing | SimpleJWT default applies if removed. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes. |

### `AUTH_PASSWORD_VALIDATORS`

Django password validation policy.

| Attribute | Value |
|---|---|
| Type | List of validator paths |
| Default Value | Similarity, minimum length, common, numeric validators |
| Whether It Is Required or Optional | Required for local-password policy |
| Example Values | Django validators |
| Whether It Is Environment-Specific | No |
| Whether It Is Secret or Sensitive | Security-sensitive |
| Where It Is Read in Code | `cerfServer/settings.py:280-285` |
| What Breaks If It Is Missing | Weak passwords may be accepted depending on call path. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes. |

### `LANGUAGE_CODE`

Default application language.

| Attribute | Value |
|---|---|
| Type | Locale string |
| Default Value | `en-us` |
| Whether It Is Required or Optional | Optional |
| Example Values | `en-gb` |
| Whether It Is Environment-Specific | Possibly |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:288` |
| What Breaks If It Is Missing | Django default language applies. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes. |

### `TIME_ZONE`

Django application timezone.

| Attribute | Value |
|---|---|
| Type | IANA timezone |
| Default Value | `UTC` |
| Whether It Is Required or Optional | Required for consistent timestamps |
| Example Values | `America/New_York` |
| Whether It Is Environment-Specific | Possibly |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:289` |
| What Breaks If It Is Missing | Django default timezone applies and timestamps may be interpreted differently. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes. |

### `USE_I18N`

Enables Django internationalization.

| Attribute | Value |
|---|---|
| Type | Boolean |
| Default Value | `true` |
| Whether It Is Required or Optional | Optional |
| Example Values | `false` |
| Whether It Is Environment-Specific | No |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:290` |
| What Breaks If It Is Missing | Translation support changes. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes. |

### `USE_TZ`

Enables timezone-aware datetimes.

| Attribute | Value |
|---|---|
| Type | Boolean |
| Default Value | `true` |
| Whether It Is Required or Optional | Required for current datetime handling |
| Example Values | `false` |
| Whether It Is Environment-Specific | No |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:291` |
| What Breaks If It Is Missing | Datetime semantics change and comparisons may fail. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes. |

### `STATIC_URL`

URL prefix for server static files/downloads.

| Attribute | Value |
|---|---|
| Type | URL path |
| Default Value | `/api/static/` |
| Whether It Is Required or Optional | Required for published static/download routes |
| Example Values | `/static/` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:294` |
| What Breaks If It Is Missing | Django default `/static/` may not match ALB/API routing. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes. |

### `STATICFILES_DIRS`

Additional static source directories.

| Attribute | Value |
|---|---|
| Type | Path list |
| Default Value | `${BASE_DIR}/downloads` |
| Whether It Is Required or Optional | Required for executable downloads |
| Example Values | Other directories |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:296-298` |
| What Breaks If It Is Missing | Download artifacts are not collected/served as static files. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes, derived path. |

### `STATIC_ROOT`

`collectstatic` destination.

| Attribute | Value |
|---|---|
| Type | Directory path |
| Default Value | `${BASE_DIR}/staticfiles` |
| Whether It Is Required or Optional | Required for deployment static collection |
| Example Values | `/var/www/static` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:300` |
| What Breaks If It Is Missing | Django cannot collect static files to intended destination. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes, derived path. |

### `HYDROFABRIC_SOURCE`

Source identifier passed to enterprise data services.

| Attribute | Value |
|---|---|
| Type | String |
| Default Value | `nhf` |
| Whether It Is Required or Optional | Required for gage data workflows |
| Example Values | `nhf` |
| Whether It Is Environment-Specific | Possibly |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:310`; data services |
| What Breaks If It Is Missing | Requests omit/use wrong hydrofabric source. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes. |

### `ENTERPRISE_DATA_MODULE_METADATA_ENDPOINT`

Relative module metadata endpoint.

| Attribute | Value |
|---|---|
| Type | URL path |
| Default Value | `api/v1/modules/parameter_metadata/` |
| Whether It Is Required or Optional | Required for metadata fetch |
| Example Values | API-relative path |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:311`; data services |
| What Breaks If It Is Missing | Metadata fetch URL cannot be built correctly. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes. |

### `ENTERPRISE_DATA_OBSERVATION_DATA_INFO_ENDPOINT`

Relative streamflow information endpoint template.

| Attribute | Value |
|---|---|
| Type | URL path template |
| Default Value | `api/v1/streamflow_observations/{gage_id}/info` |
| Whether It Is Required or Optional | Required for observation metadata |
| Example Values | API-relative path |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:312`; data services |
| What Breaks If It Is Missing | Observation availability/info fetch fails. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes. |

### `ENTERPRISE_DATA_OBSERVATION_DATA_ENDPOINT`

Relative streamflow CSV endpoint template.

| Attribute | Value |
|---|---|
| Type | URL path template |
| Default Value | `api/v1/streamflow_observations/{gage_id}/csv` |
| Whether It Is Required or Optional | Required for observations |
| Example Values | API-relative path |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:313`; data services |
| What Breaks If It Is Missing | Observation data fetch fails. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes. |

### `ZIP_TEMP_DIR`

Local workspace used to build ZIP downloads.

| Attribute | Value |
|---|---|
| Type | Directory path |
| Default Value | `/tmp/ngencerf-zips` |
| Whether It Is Required or Optional | Required for ZIP generation |
| Example Values | `/mnt/tmp/zips` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:336-337`; download views |
| What Breaks If It Is Missing | Startup directory creation or ZIP construction fails. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes. |

### `ZIP_DOWNLOAD_URL_TTL_SECONDS`

Presigned download URL validity.

| Attribute | Value |
|---|---|
| Type | Integer seconds |
| Default Value | `300` |
| Whether It Is Required or Optional | Required for download security/usability |
| Example Values | `900` |
| Whether It Is Environment-Specific | Possibly |
| Whether It Is Secret or Sensitive | Security-sensitive |
| Where It Is Read in Code | `cerfServer/settings.py:340`; download views |
| What Breaks If It Is Missing | URL generation needs a replacement value. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes. |

### `ZIP_RETENTION_SECONDS`

S3 ZIP retention and status-cache period.

| Attribute | Value |
|---|---|
| Type | Integer seconds |
| Default Value | `3600` |
| Whether It Is Required or Optional | Required for cleanup behavior |
| Example Values | `86400` |
| Whether It Is Environment-Specific | Possibly |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:343`; download/cleanup views |
| What Breaks If It Is Missing | Cleanup/status behavior lacks a retention threshold. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes. |

### `REPO_ROOT`

In-container application/repository root.

| Attribute | Value |
|---|---|
| Type | Directory path |
| Default Value | `/ngen-app` |
| Whether It Is Required or Optional | Required by repo path derivations |
| Example Values | `/opt/ngen` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:351` |
| What Breaks If It Is Missing | Derived repository paths break. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code plus image rebuild |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes. |

### `CONTAINER_DATA_ROOT`

Shared data path expected inside server and runtime containers.

| Attribute | Value |
|---|---|
| Type | Directory path |
| Default Value | `/ngencerf/data` |
| Whether It Is Required or Optional | Required |
| Example Values | `/data` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:363`; many modules |
| What Breaks If It Is Missing | Almost all static, work, run, and forcing paths break. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code plus coordinated mount/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes; repeated in Docker/AWS mounts. |

### `SINGULARITY_DIR`

In-container directory used to inspect Singularity images/Git information.

| Attribute | Value |
|---|---|
| Type | Directory path |
| Default Value | `/ngencerf/containers` |
| Whether It Is Required or Optional | Conditional for Slurm |
| Example Values | `/containers` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:367`; Git utility |
| What Breaks If It Is Missing | Singularity metadata/image lookup fails. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code plus coordinated mount/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes; repeated in AWS mount. |

### `INSTALLED_APPS`

Django applications loaded at startup, including DRF, Djoser, SimpleJWT, CORS, OTP, and calibration.

| Attribute | Value |
|---|---|
| Type | Import-path list |
| Default Value | Fixed list in source |
| Whether It Is Required or Optional | Required |
| Example Values | Django application labels |
| Whether It Is Environment-Specific | No |
| Whether It Is Secret or Sensitive | Security-sensitive |
| Where It Is Read in Code | `cerfServer/settings.py:71-89` |
| What Breaks If It Is Missing | Models, middleware integration, authentication, migrations, or APIs fail to load. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes. |

### `MIDDLEWARE`

Ordered Django request/response middleware chain.

| Attribute | Value |
|---|---|
| Type | Import-path list |
| Default Value | Fixed list in source |
| Whether It Is Required or Optional | Required |
| Example Values | Django middleware paths |
| Whether It Is Environment-Specific | No |
| Whether It Is Secret or Sensitive | Security-sensitive |
| Where It Is Read in Code | `cerfServer/settings.py:111-126` |
| What Breaks If It Is Missing | Security, sessions, authentication, OTP, CORS, diagnostics, or compression behavior fails or changes. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes; ordering is significant. |

### `ROOT_URLCONF`

Root Django URL configuration module.

| Attribute | Value |
|---|---|
| Type | Import path |
| Default Value | `cerfServer.urls` |
| Whether It Is Required or Optional | Required |
| Example Values | `project.urls` |
| Whether It Is Environment-Specific | No |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:219` |
| What Breaks If It Is Missing | Django cannot resolve application URLs. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes. |

### `TEMPLATES`

Django template engine, directory, app discovery, and context processors.

| Attribute | Value |
|---|---|
| Type | Mapping/list |
| Default Value | DjangoTemplates with `${BASE_DIR}/templates` |
| Whether It Is Required or Optional | Required for admin/template views |
| Example Values | Django template settings |
| Whether It Is Environment-Specific | No |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:221-235` |
| What Breaks If It Is Missing | Admin and template-rendered views fail. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes. |

### `AUTHENTICATION_BACKENDS`

Ordered AD and local authentication backends.

| Attribute | Value |
|---|---|
| Type | Import-path list |
| Default Value | AD backend, then local backend |
| Whether It Is Required or Optional | Required |
| Example Values | Backend import paths |
| Whether It Is Environment-Specific | No |
| Whether It Is Secret or Sensitive | Security-sensitive |
| Where It Is Read in Code | `cerfServer/settings.py:237-240` |
| What Breaks If It Is Missing | Users cannot authenticate through the removed backend; ordering changes fallback behavior. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes. |

### `CACHES`

Django cache backend and Redis client implementation.

| Attribute | Value |
|---|---|
| Type | Mapping |
| Default Value | `django_redis.cache.RedisCache` with `DefaultClient` |
| Whether It Is Required or Optional | Required for caching |
| Example Values | Django cache configuration |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | May contain credentials via `REDIS_URL` |
| Where It Is Read in Code | `cerfServer/settings.py:242-250` |
| What Breaks If It Is Missing | Cache operations fail or use Django defaults if removed. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy except Redis URL |
| Whether It Is Hardcoded Anywhere; If So, Where? | Backend/client are hardcoded; location is environment-driven. |

### `AUTH_USER_MODEL`

Custom Django user model.

| Attribute | Value |
|---|---|
| Type | App/model label |
| Default Value | `calibration.CustomUser` |
| Whether It Is Required or Optional | Required |
| Example Values | `app.User` |
| Whether It Is Environment-Specific | No |
| Whether It Is Secret or Sensitive | Security-sensitive |
| Where It Is Read in Code | `cerfServer/settings.py:252` |
| What Breaks If It Is Missing | Authentication and user foreign keys break; changing after migrations is high risk. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code, migrations, and redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes. |

### `WSGI_APPLICATION`

WSGI application entry point.

| Attribute | Value |
|---|---|
| Type | Import path |
| Default Value | `cerfServer.wsgi.application` |
| Whether It Is Required or Optional | Required for WSGI serving |
| Example Values | Import path |
| Whether It Is Environment-Specific | No |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:278` |
| What Breaks If It Is Missing | WSGI server cannot load the application. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes. |

### `DEFAULT_AUTO_FIELD`

Default Django model primary-key field type.

| Attribute | Value |
|---|---|
| Type | Import path |
| Default Value | `django.db.models.BigAutoField` |
| Whether It Is Required or Optional | Required for migration consistency |
| Example Values | `django.db.models.AutoField` |
| Whether It Is Environment-Specific | No |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:305` |
| What Breaks If It Is Missing | Django default/warnings apply; changing may create migrations and schema differences. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code, migrations, and redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes. |

### Forcing date-range settings

Allowed/available BMI forcing periods for AORC and NWM retrospective domains.

| Attribute | Value |
|---|---|
| Type | DateTimeRange values |
| Default Value | AORC is computed; CONUS `1979-01-01`–`2023-01-31`; Hawaii `1994-01-01`–`2013-12-31`; Alaska `1981-01-01`–`2019-12-31`; Puerto Rico `2008-01-01`–`2023-06-30` |
| Whether It Is Required or Optional | Required for forcing validation |
| Example Values | Updated dataset coverage dates |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:319-323`; tuning views |
| What Breaks If It Is Missing | UI/server cannot validate forcing-date availability correctly. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes, except AORC is returned by `get_aorc_conus_bmi_date_range()`. |

### `NGEN_STATIC_DIR`

Static model/forcing data root.

| Attribute | Value |
|---|---|
| Type | Directory path |
| Default Value | `/ngencerf/data/ngen-static-files` |
| Whether It Is Required or Optional | Required for model inputs |
| Example Values | Derived path |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:646` and consumers |
| What Breaks If It Is Missing | Model templates and static inputs cannot be found. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy or coordinated symlink |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes, derived. |

### `NGEN_CAL_WORK_DIR`

Calibration working root.

| Attribute | Value |
|---|---|
| Type | Directory path |
| Default Value | `/ngencerf/data/ngen-cal-work` |
| Whether It Is Required or Optional | Required |
| Example Values | Derived path |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:647` and consumers |
| What Breaks If It Is Missing | Calibration work files cannot be created/found. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes, derived. |

### `NGEN_VERIFICATION_WORK_DIR`

Verification working root.

| Attribute | Value |
|---|---|
| Type | Directory path |
| Default Value | `/ngencerf/data/verification_work` |
| Whether It Is Required or Optional | Required for verification |
| Example Values | Derived path |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:648` and consumers |
| What Breaks If It Is Missing | Verification work files cannot be created/found. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes, derived. |

### `NGEN_BMI_FORCING_WORK_DIR`

ngen-forcing-owned BMI forcing work root.

| Attribute | Value |
|---|---|
| Type | Directory path |
| Default Value | `/ngencerf/data/bmi_forcing_work` |
| Whether It Is Required or Optional | Required for BMI forcing |
| Example Values | Derived path |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:651` and input builder |
| What Breaks If It Is Missing | Forcing generation and references fail. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes, derived. |

### `NGEN_CAL_RUN_DIR`

Calibration run output root.

| Attribute | Value |
|---|---|
| Type | Directory path |
| Default Value | `/ngencerf/data/ngen-cal-work/run_calib` |
| Whether It Is Required or Optional | Required |
| Example Values | Derived path |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:654` and run models/utilities |
| What Breaks If It Is Missing | Run output cannot be found or stored. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes, derived. |

### Docker runtime commands

Commands/images for calibration, forecast, and evaluation in Docker mode.

| Attribute | Value |
|---|---|
| Type | Command templates |
| Default Value | `nwm-cal-mgr`, `nwm-fcst-mgr`, and `nwm-eval-mgr` |
| Whether It Is Required or Optional | Required in Docker mode |
| Example Values | Docker command strings |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:578-602` |
| What Breaks If It Is Missing | Jobs cannot launch. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes. These are fallback/local runtime commands; AWS uses Slurm when PCS is enabled. |

### Singularity runtime commands

Command templates and bind mount for Slurm mode.

| Attribute | Value |
|---|---|
| Type | Command templates |
| Default Value | `/usr/bin/time -v singularity run -B ...` |
| Whether It Is Required or Optional | Required in Slurm mode |
| Example Values | Singularity command strings |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `cerfServer/settings.py:617-643` |
| What Breaks If It Is Missing | Jobs cannot launch or cannot access shared data. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Code/redeploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Yes. |


## AWS runtime configuration

These inputs configure the ECS container and service rather than being read directly by Django.

### `ngencerf_server_image`

Terraform input selecting the ECS server image.

| Attribute | Value |
|---|---|
| Type | Container image URI |
| Default Value | Defined elsewhere |
| Whether It Is Required or Optional | Required |
| Example Values | `ghcr.io/ngwpc/ngencerf-server:2.0.0` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `django.tf:31` |
| What Breaks If It Is Missing | ECS task definition cannot be created correctly. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | New task definition/deploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Variable referenced; default not present in supplied file. |

### `django_cpu` / `django_memory`

ECS Fargate task CPU and memory.

| Attribute | Value |
|---|---|
| Type | Terraform numbers/strings |
| Default Value | Defined elsewhere |
| Whether It Is Required or Optional | Required |
| Example Values | `4096` / `8192` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `django.tf:22-23` |
| What Breaks If It Is Missing | Terraform plan fails without variable definitions. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | New task definition/deploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | References only in supplied file. |

### ECS `containerPort`

Port exposed to target group.

| Attribute | Value |
|---|---|
| Type | Integer |
| Default Value | `8000` |
| Whether It Is Required or Optional | Required |
| Example Values | `8000` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `django.tf:36-39,296` |
| What Breaks If It Is Missing | ALB cannot reach application if it differs from server bind port. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | New task definition/deploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Hardcoded 8000. |

### ECS service scaling/deployment values

Desired tasks and rolling deployment percentages.

| Attribute | Value |
|---|---|
| Type | Integers |
| Default Value | Desired `1`; min healthy `100`; max `200` |
| Whether It Is Required or Optional | Required operational behavior |
| Example Values | Desired `2` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `django.tf:279-301` |
| What Breaks If It Is Missing | Terraform/provider defaults or invalid service configuration apply. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Terraform apply |
| Whether It Is Hardcoded Anywhere; If So, Where? | Hardcoded. |

### ECS health-check grace period

Time before ECS evaluates target health.

| Attribute | Value |
|---|---|
| Type | Integer seconds |
| Default Value | `600` |
| Whether It Is Required or Optional | Optional tuning |
| Example Values | `120` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `django.tf:299` |
| What Breaks If It Is Missing | ECS default applies and slow startup may cause task cycling. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Terraform apply |
| Whether It Is Hardcoded Anywhere; If So, Where? | Hardcoded. |

### CloudWatch log group/region/stream prefix

awslogs driver destination.

| Attribute | Value |
|---|---|
| Type | Deployment references/string |
| Default Value | Group resource; current AWS region; prefix `django` |
| Whether It Is Required or Optional | Required for centralized logs |
| Example Values | `/aws/ecs/dev/django` |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | Sensitive infrastructure metadata |
| Where It Is Read in Code | `django.tf:223-230` |
| What Breaks If It Is Missing | Container logs are not delivered correctly. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | New task definition/deploy |
| Whether It Is Hardcoded Anywhere; If So, Where? | Prefix hardcoded; group/region derived. |


## Container image build arguments

The following arguments are build-time only. Changing them requires rebuilding and redeploying the server image. This reference treats `Dockerfile.production-pw` as the authoritative production server image definition. The separate `Dockerfile` is used only for development, which is why it is not covered in detail here.

### `GH_ORG`

Default GitHub organization for dependency repositories.

| Attribute | Value |
|---|---|
| Type | String |
| Default Value | `NGWPC` |
| Whether It Is Required or Optional | Required |
| Example Values | `NGWPC` |
| Whether It Is Environment-Specific | Possibly |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `Dockerfile.production-pw`, top-level ARG |
| What Breaks If It Is Missing | Dependency clone URLs are invalid if empty. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Build-time |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default hardcoded. |

### `IMAGE_NAMESPACE`

Namespace used in custom OCI label keys.

| Attribute | Value |
|---|---|
| Type | String |
| Default Value | `ngwpc` |
| Whether It Is Required or Optional | Required for labels |
| Example Values | `ngwpc` |
| Whether It Is Environment-Specific | No |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `Dockerfile.production-pw` |
| What Breaks If It Is Missing | Custom labels are malformed. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Build-time |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default hardcoded. |

### `DATA_ASSIMILATION_ORG`, `EWTS_ORG`, `MSW_MGR_ORG`, `NGEN_ORG`, `NGEN_FORCING_ORG`

GitHub organizations for each source dependency.

| Attribute | Value |
|---|---|
| Type | Strings |
| Default Value | `${GH_ORG}` |
| Whether It Is Required or Optional | Required |
| Example Values | `NGWPC` |
| Whether It Is Environment-Specific | Possibly |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `Dockerfile.production-pw` |
| What Breaks If It Is Missing | Corresponding clone/install fails. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Build-time |
| Whether It Is Hardcoded Anywhere; If So, Where? | Derivation hardcoded. |

### `DATA_ASSIMILATION_REF`, `EWTS_REF`, `MSW_MGR_REF`, `NGEN_REF`, `NGEN_FORCING_REF`

Branch, tag, or commit selected for source dependencies.

| Attribute | Value |
|---|---|
| Type | Git refs |
| Default Value | `development` |
| Whether It Is Required or Optional | Required |
| Example Values | `main`, `v2.0.0`, commit SHA |
| Whether It Is Environment-Specific | Yes |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `Dockerfile.production-pw` |
| What Breaks If It Is Missing | Builds use development refs or fail if ref unavailable. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Build-time |
| Whether It Is Hardcoded Anywhere; If So, Where? | Defaults hardcoded. |

### `*_CACHE_BUST` (`DATA_ASSIMILATION`, `EWTS`, `MSW_MGR`, `NGEN`, `NGEN_FORCING`)

Invalidates Docker cache for dependency fetch/install layers.

| Attribute | Value |
|---|---|
| Type | String/integer |
| Default Value | `1` |
| Whether It Is Required or Optional | Optional |
| Example Values | Timestamp or CI build number |
| Whether It Is Environment-Specific | No |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `Dockerfile.production-pw` |
| What Breaks If It Is Missing | Cached layer may be reused despite upstream branch movement. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Build-time |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default hardcoded. |

### `BASE_REPO`, `BASE_TAG`, `PYTHON_IMAGE_DIGEST`

Base Python image repository, tag, and the digest the tag is pinned to. The `FROM` line uses all three (`repo:tag@digest`), so the digest is what gets pulled; refresh the tag and digest together, in both Dockerfiles and in the `BASE_NAME` value in `.github/workflows/cicd.yml`.

| Attribute | Value |
|---|---|
| Type | Strings |
| Default Value | `python`, `3.12-slim-bookworm`, current index digest of that tag |
| Whether It Is Required or Optional | Required |
| Example Values | `python`, `3.14-slim-bookworm`, `sha256:...` from `docker buildx imagetools inspect python:3.14-slim-bookworm` |
| Whether It Is Environment-Specific | No |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `Dockerfile`, `Dockerfile.production-pw` (image selection block and the `FROM` line) |
| What Breaks If It Is Missing | Base `FROM` is invalid. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Build-time |
| Whether It Is Hardcoded Anywhere; If So, Where? | Defaults hardcoded. |

### `GO_IMAGE`, `GO_IMAGE_DIGEST`

Go toolchain image used by production Singularity build, and the digest its tag is pinned to (`FROM ${GO_IMAGE}@${GO_IMAGE_DIGEST}`). Refresh both together.

| Attribute | Value |
|---|---|
| Type | Image reference, digest |
| Default Value | `golang:1.25.11-bookworm`, current index digest of that tag |
| Whether It Is Required or Optional | Required for production image build |
| Example Values | `golang:1.25.11-bookworm`, `sha256:...` from `docker buildx imagetools inspect golang:1.25.11-bookworm` |
| Whether It Is Environment-Specific | No |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `Dockerfile.production-pw` (image selection block and the `go-toolchain` stage `FROM` line) |
| What Breaks If It Is Missing | Production build stage fails. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Build-time |
| Whether It Is Hardcoded Anywhere; If So, Where? | Defaults hardcoded. |

### `SINGULARITY_VERSION`

SingularityCE source version built into production image.

| Attribute | Value |
|---|---|
| Type | Version string |
| Default Value | `4.4.2` |
| Whether It Is Required or Optional | Required for production image |
| Example Values | `4.4.2` |
| Whether It Is Environment-Specific | No |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `Dockerfile.production-pw:36,185` |
| What Breaks If It Is Missing | Clone/build fails. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Build-time |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default hardcoded. |

### `BOOST_VERSION`

Boost source version built in production image.

| Attribute | Value |
|---|---|
| Type | Version string |
| Default Value | `1.86.0` |
| Whether It Is Required or Optional | Required for EWTS production build |
| Example Values | `1.86.0` |
| Whether It Is Environment-Specific | No |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `Dockerfile.production-pw:197-202` |
| What Breaks If It Is Missing | Download/build fails. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Build-time |
| Whether It Is Hardcoded Anywhere; If So, Where? | Default hardcoded. |

### `BASE_NAME`, `BASE_DIGEST`, `BASE_REVISION`

OCI provenance metadata for base image.

| Attribute | Value |
|---|---|
| Type | Strings |
| Default Value | Derived name (`repo:tag@digest`); `BASE_DIGEST` defaults to `PYTHON_IMAGE_DIGEST`; `BASE_REVISION` `unknown` |
| Whether It Is Required or Optional | Optional metadata |
| Example Values | Image name, digest, Git SHA |
| Whether It Is Environment-Specific | No |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `Dockerfile.production-pw` label block |
| What Breaks If It Is Missing | Image builds but provenance labels are incomplete. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Build-time |
| Whether It Is Hardcoded Anywhere; If So, Where? | Unknown fallbacks hardcoded. |

### `IMAGE_SOURCE`, `IMAGE_VENDOR`, `IMAGE_VERSION`, `IMAGE_REVISION`

OCI source/vendor/version/revision labels.

| Attribute | Value |
|---|---|
| Type | Strings |
| Default Value | `unknown` |
| Whether It Is Required or Optional | Optional but recommended for traceability |
| Example Values | Repository URL, `RTX`, release, SHA |
| Whether It Is Environment-Specific | No |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `Dockerfile.production-pw` label block |
| What Breaks If It Is Missing | Image builds with incomplete provenance. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Build-time |
| Whether It Is Hardcoded Anywhere; If So, Where? | Unknown fallbacks hardcoded. |

### `DATA_ASSIMILATION_REVISION`, `EWTS_REVISION`, `MSW_MGR_REVISION`, `NGEN_REVISION`, `NGEN_FORCING_REVISION`

Resolved dependency revisions recorded in image labels.

| Attribute | Value |
|---|---|
| Type | Git SHA strings |
| Default Value | `unknown` |
| Whether It Is Required or Optional | Optional but recommended |
| Example Values | 40-character SHA |
| Whether It Is Environment-Specific | No |
| Whether It Is Secret or Sensitive | No |
| Where It Is Read in Code | `Dockerfile.production-pw` label block |
| What Breaks If It Is Missing | Image builds but dependency provenance is incomplete. |
| Whether It Can Be Changed Without Rebuilding or Redeploying | Build-time |
| Whether It Is Hardcoded Anywhere; If So, Where? | Unknown fallbacks hardcoded. |


## Known configuration risks and gaps

1. `CERF_SERVER_SECRET_KEY` falls back to a known literal. Production must always inject a unique secret.
2. `DJANGO_SUPERUSER_PASSWORD=admin` is committed in both server environment files. It should not be used outside disposable local development, and production bootstrap credentials should come from a secret store or be disabled entirely.
3. Database username/password fallbacks are `postgres`; the fallback password is committed in source.
4. `DJANGO_DEBUG` defaults to true. A missed production override starts the server with unsafe development behavior and also enables local file logging by default.
5. CORS_ALLOWED_ORIGINS is intentionally not set in AWS because the UI and API share the same origin through the ALB; it is only needed if the UI moves to a different hostname than the API.
6. `SLURM_NODE_TYPE_RULES` and `MPI_NODE_RULES` can both be overridden through environment variables. AWS currently overrides `MPI_NODE_RULES` to use 5 nodes instead of the application default of 6 for 251-500 catchments. AWS does not override `SLURM_NODE_TYPE_RULES`, so its hardcoded default remains in use. Cluster changes can make either rule set invalid or inefficient unless the defaults or AWS overrides are updated accordingly.
7. `SLURM_REST_USER`, UID, and GID default to root/0 and are also explicitly configured that way in AWS. This is security-relevant and should be justified against least-privilege requirements.
8. JWT access and refresh lifetimes are hardcoded rather than environment-configurable.

## Source files reviewed

- `cerfServer/settings.py`
- `cerfServer/.env` templates and server environment files
- `runCerf.sh`
- `gunicorn_conf.py`
- `Dockerfile.production-pw`
- `calibration` source references to Django settings and environment variables
- Supplied `django.tf`
