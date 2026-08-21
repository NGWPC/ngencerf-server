# ngenCerf Command Line Interface (CLI) Documentation

The `ngenCerf` CLI provides a command-line interface to interact with the ngenCerf server, allowing you to create, update, manage, and run calibration jobs. It offers an alternative to the GUI, enabling automation and scripting capabilities.

## Table of Contents

- [Downloading the CLI](#downloading-the-cli)
- [Building](#building)
- [Login](#login)
- [Two-Factor Authentication](#two-factor-authentication)
- [Admin Users](#admin-users)
- [Subcommands](#subcommands)
  - [about](#about)
  - [archive](#archive)
  - [cancel](#cancel)
  - [change-password](#change-password)
  - [create-local-user](#create-local-user)
  - [delete](#delete)
  - [download](#download)
  - [export](#export)
  - [import](#import)
  - [jobs](#jobs)
  - [lock](#lock)
  - [regionalization](#regionalization)
  - [register](#register)
  - [run](#run)
  - [show](#show)
  - [status](#status)
  - [unarchive](#unarchive)
  - [unlock](#unlock)
  - [update](#update)
  - [url](#url)
  - [version](#version)
- [Output Files](#output-files)
- [Importing and Exporting](#importing-and-exporting)


## Downloading the CLI

Users normally download the prebuilt CLI from the ngenCerf web application. They do not need to build it from source.

1. Log in to the ngenCerf web application.
2. Click your avatar or initials in the upper-right corner of the page.
3. Select **Download CLI** from the menu.
4. On the Download CLI page, choose the download for your operating system.
5. Follow the setup and server URL instructions displayed on the page.

### Windows

Save `ngencerf.exe` in a directory where you keep command-line tools, such as `C:\Users\<your-username>\bin`. You can run it directly from that directory:

```powershell
.\ngencerf.exe
```

You can optionally add the directory to your Windows `PATH` so that you can run `ngencerf` from any directory.

### macOS

Open Terminal in the download directory and make the file executable:

```bash
chmod +x ngencerf
```

You can then run it from that directory using `./ngencerf`, or move it to a directory on your `PATH`, such as `/usr/local/bin`, so that you can run it as `ngencerf` from any directory.

### Linux

Open a terminal in the download directory and make the file executable:

```bash
chmod +x ngencerf
```

You can then run it from that directory using `./ngencerf`, or move it to a directory on your `PATH`, such as `/usr/local/bin`, so that you can run it as `ngencerf` from any directory.

The Download CLI page also provides the command needed to configure the CLI to communicate with the ngenCerf server. Run the displayed `url add` command after downloading the CLI. The command saves the server URL and makes it the active server:

```bash
ngencerf url add SERVER_URL
```

Use the server URL shown on the Download CLI page in place of `SERVER_URL`. For example:

```bash
ngencerf url add https://ngencerf.example.com/api
```

You can confirm the currently selected server with:

```bash
ngencerf url current
```

The server URL is saved for future CLI sessions. It does not normally need to be entered again unless the user wants to connect to a different ngenCerf server. See the [`url`](#url) command for information about saving, listing, selecting, and deleting server URLs.


## Building

**This section is for developers only.** Regular users should download the prebuilt CLI from the ngenCerf web application as described in [Downloading the CLI](#downloading-the-cli).

The CLI executable is platform-specific. Developers must build it on the operating system for which it will be distributed and must use the build program for that operating system.

### Linux

From the `cli` directory, run:

```bash
$ ./build_cli.sh
```

The Linux executable is written to:

```text
../downloads/latest/linux/ngencerf
```

### macOS

From the `cli` directory, run:

```bash
$ ./build_cli.sh
```

The script detects macOS and writes the executable to:

```text
../downloads/latest/macos/ngencerf
```

The macOS build supports both Intel-based Macs and Macs with Apple silicon. The current build program produces an Intel (x86_64) executable, which runs natively on Intel-based Macs and on Macs with Apple silicon through Rosetta. 
When building on a Mac with Apple silicon, use an x86_64 Python environment under Rosetta to produce the Intel-compatible executable.

### Windows

From the `cli` directory, run the PowerShell build program:

```powershell
PS> .\build_cli.ps1
```

The Windows executable is written to:

```text
../downloads/latest/windows/ngencerf.exe
```

Do not use `build_cli.sh` on Windows or `build_cli.ps1` on Linux or macOS. A binary built for one operating system cannot be used on another operating system.

After building on Linux or macOS, developers can optionally copy the executable to a directory in their `PATH`, such as `~/.local/bin` or `/usr/local/bin`:

```bash
$ sudo cp ../downloads/latest/linux/ngencerf /usr/local/bin
```

## Login

The first time you run a command that requires authentication, the CLI prompts for your email address and password. Depending on how the server is configured, these may be Active Directory credentials or credentials managed directly by ngenCerf.

The credentials and authentication tokens are saved in `~/.ngencerf_env`. Once saved, the CLI automatically reads them. If two-factor authentication is enabled on the server, the CLI also prompts for an authenticator or recovery code as described below.

## Two-Factor Authentication

If two-factor authentication is enabled on the ngenCerf server, the CLI requires a second authentication step in addition to the user's email address and password.

The first time a user logs in after two-factor authentication is enabled, the CLI guides the user through the setup process:

1. The CLI displays a QR code.
2. Scan the QR code with an authenticator application, such as Microsoft Authenticator, Google Authenticator, or another application that supports time-based one-time passwords (TOTP).
3. Enter the six-digit code generated by the authenticator application to confirm the setup.
4. The server generates recovery codes. Save these codes in a secure location before continuing. Each recovery code can be used only once.
5. After setup is complete, the CLI restarts the login process.

For subsequent logins, the CLI prompts for the six-digit code currently displayed by the authenticator application. A recovery code can be entered instead if the authenticator application is unavailable.

Two-factor authentication is associated with the user's ngenCerf account, not with a particular CLI installation. Configuring the CLI on another computer does not require setting up a second authenticator entry for the same account.

## Admin Users

Admin privileges are managed differently depending on whether Active Directory authentication is enabled.

### Active Directory Enabled

When Active Directory authentication is enabled, a user can be designated as an admin through Active Directory. The ngenCerf server uses that designation when the user authenticates.

### Active Directory Not Enabled

When Active Directory authentication is not enabled, the only admin account created automatically is the built-in `admin` user.

Creating another user with the `register` or `create-local-user` command does not make that user an admin. To grant admin privileges to another user, the corresponding entry in the `custom_user` database table must be modified to enable the `is_superuser` flag. This is a direct database administration operation and must be performed by someone with authorized access to the ngenCerf database.

## Subcommands

### about

Retrieves release and build information for the CLI and ngenCerf server components and saves it as a JSON file. Unless another location is specified, the file is saved as `about_ngencerf.json` in the current directory.

**Usage:**

```bash
ngencerf about [--output OUTPUT]
```

**Arguments:**

- `--output`, `-o`: (Optional) The file or directory in which to save the output.

**Example:**

```bash
ngencerf about --output ./about.json
```

### archive

Archives one or more calibration jobs, removing them from most operations without permanently deleting them.

**Usage:**

```bash
ngencerf archive run_ids | file_path
```

**Arguments:**

- `run_ids`: A space-separated list of one or more calibration run IDs.
- `file_path`: A Markdown file created by the `jobs` command. The CLI reads the run IDs from the first column.

**Example:**

```bash
ngencerf archive 1 2 3

ngencerf archive calibration_jobs_2025-11-04_1455.md
```

---

### cancel

Cancels a running calibration job.

**Usage:**

```bash
ngencerf cancel run_id
```

**Arguments:**

- `run_id`: The calibration run ID of the job to cancel.

**Example:**

```bash
ngencerf cancel 42
```

---

### change-password

Changes the current user's password or, for an authorized administrator, resets another user's password.

**Usage:**

```bash
ngencerf change-password [--email EMAIL]
```

**Arguments:**

- `--email`: (Optional) The email address of another user whose password should be reset. This requires staff or administrator authorization. If omitted, the current user is prompted for the current password and a new password.

**Behavior:**

After the current user changes their own password, the saved password is removed from `~/.ngencerf_env`. The CLI prompts for the new password at the next login.

**Examples:**

```bash
ngencerf change-password

ngencerf change-password --email user@example.com
```

---

### create-local-user

Creates a local-only ngenCerf user whose account and password are managed directly by ngenCerf rather than by Active Directory. 
This command requires the current CLI user to be authenticated and authorized as staff or an administrator.

This command is primarily intended for creating a user who must be able to log in without having an Active Directory account. 
When Active Directory authentication is enabled, an account created with this command remains separate from Active Directory. 
The user's password is stored and validated by ngenCerf, and changes to the user's Active Directory account or password do not affect the local ngenCerf account.

When Active Directory authentication is not enabled, the command provides an administrator-controlled way to create a user directly. Unlike `register`, which allows a user to register their own account when self-registration is enabled, `create-local-user` allows an authorized administrator to create the account and assign its initial password.

Creating a local user does not make the user an admin. The account is created as a regular ngenCerf user unless its database permissions are changed separately, as described in [Admin Users](#admin-users).

**Usage:**

```bash
ngencerf create-local-user [email]
```

**Arguments:**

- `email`: (Optional) The email address for the new user. If omitted, the CLI prompts for it.

**Behavior:**

The CLI prompts for the user's first name, last name, password, and password confirmation. The new user can then log in with the specified email address and password. 
If two-factor authentication is enabled, the user must configure it during the first login in the same way as any other ngenCerf user.

**Example:**

```bash
ngencerf create-local-user user@example.com
```

---

### delete

Permanently deletes one or more calibration jobs after prompting for confirmation.

**Usage:**

```bash
ngencerf delete run_ids | file_path
```

**Arguments:**

- `run_ids`: A space-separated list of one or more calibration run IDs to delete.
- `file_path`: A Markdown file created by the `jobs` command. The CLI reads the run IDs from the first column.

**Behavior:**

Upon execution, the CLI will display job details (if a single job is specified) and prompt:

```
Type 'delete' to confirm the permanent deletion of calibration jobs [run_ids]:
```

The deletion proceeds only if the user types `delete`.

**Example:**

```bash
ngencerf delete 97 98 99

ngencerf delete calibration_jobs_2025-11-04_1455.md
```

---

### download

Downloads a ZIP archive for a calibration run.

**Usage:**

```bash
ngencerf download run_id [--output OUTPUT]
```

**Arguments:**

- `run_id`: The calibration run ID to download.
- `--output`, `-o`: (Optional) The path to save the downloaded file. Defaults to the current directory.

**Example:**

```bash
ngencerf download 123 --output ~/Downloads/job_123.zip
```

---

### export

Exports a calibration job to a JSON file or displays it on the console.

See also [import](#import) and [Importing and Exporting](#importing-and-exporting)

**Usage:**

```bash
ngencerf export run_id [--output OUTPUT] [--show]
```

**Arguments:**

- `run_id`: The calibration run ID to export.
- `--output`, `-o`: (Optional) The path to save the export file. Defaults to the current directory.
- `--show`, `-s`: (Optional) Display the job in the console.

**Example:**

```bash
ngencerf export 456 --output ./job_456.json --show
```

---

### import

Imports a new job definition from a JSON file, with an optional `--run` flag to immediately start the job.
If `--run` is specified, it overrides `run_after_import` if specified in the Json file

See also [export](#export) and [Importing and Exporting](#importing-and-exporting)

**Usage:**

```bash
ngencerf import input_file [--run true|false]
```

**Arguments:**

- `input_file`: The path to the JSON file containing the job definition.
- `--run`, `-r`: (Optional) Overrides the `run_after_import` field in the JSON file. Defaults to `true` if specified without a value.

**Example:**

```bash
ngencerf import my_job.json --run false
```

---

### jobs

Lists all calibration jobs, optionally saving the output to a markdown file.

**Usage:**

```bash
ngencerf jobs [--output OUTPUT]
              [--filters FILTERS]
              [--sort SORT]
              [--gage-id GAGE_ID]
              [--status STATUS [STATUS ...]]
              [--include-archived true|false]
              [--module-operator and|or]
              [--module-list MODULE [MODULE ...]]
              [--date-operator before|after|between]
              [--date DATE | --date-start DATE --date-end DATE]
              [--id-operator before|after|between]
              [--id ID | --id-start ID --id-end ID]
              [--sort-field FIELD]
              [--sort-direction asc|desc]
```

**Arguments:**

- `--output`, `-o`: (Optional) The path to save the job list as a Markdown file. Defaults to a timestamped filename in the current directory. The resulting file can be supplied to `archive`, `delete`, `lock`, `unarchive`, and `unlock`.
- `--filters`: Reserved for a JSON or YAML filter definition. Although the current parser accepts this option, the current implementation does not apply it. Use the individual filter flags instead.
- `--sort`: (Optional) A JSON or YAML file path, or an inline JSON or YAML string defining the sort order.
- `--gage-id`: (Optional) Filter by an exact gage ID.
- `--status`: (Optional) Filter by one or more statuses, such as `Done`, `Failed`, or `Running`.
- `--include-archived`: (Optional) Include archived jobs. Defaults to `false`.
- `--module-operator`: (Optional) Combine the modules specified by `--module-list` using `and` or `or`. Defaults to `and`.
- `--module-list`: (Optional) Filter by one or more module names.
- `--date-operator`: (Optional) Filter by creation date using `before`, `after`, or `between`.
- `--date`: Date in `YYYY-MM-DD` format for the `before` or `after` date operator.
- `--date-start`, `--date-end`: Start and end dates in `YYYY-MM-DD` format for the `between` date operator.
- `--id-operator`: (Optional) Filter by calibration run ID using `before`, `after`, or `between`.
- `--id`: Calibration run ID for the `before` or `after` ID operator.
- `--id-start`, `--id-end`: Start and end calibration run IDs for the `between` ID operator.
- `--sort-field`: (Optional) Field by which to sort the results. Valid fields are `gage_id`, `user_formulation_name`, `submit_date`, `create_date`, `job_genesis`, `status`, `calibration_start_period`, `calibration_end_period`, and `stop_criteria`.
- `--sort-direction`: (Optional) Sort direction: `asc` or `desc`. Defaults to `desc` when used with `--sort-field`.

The `--sort` option provides the same sorting capability as `--sort-field` and `--sort-direction`. Do not combine the two forms. Until `--filters` is implemented, use the individual filter flags.

**Examples:**

```bash
ngencerf jobs --output ./all_jobs.md

ngencerf jobs \
  --gage-id 01055000 \
  --status Done Failed \
  --module-operator or \
  --module-list "CFE-X" "Noah-OWP-Modular" \
  --date-operator after \
  --date 2025-10-10 \
  --sort-field submit_date \
  --sort-direction desc \
  --output ./recent_jobs.md

ngencerf jobs --gage-id 01055000 \
  --sort '{"field": "submit_date", "direction": "desc"}'
```

---

### lock

Locks one or more calibration jobs, which prevents them from being deleted or archived

**Usage:**
```bash
ngencerf lock run_ids | file_path
```

**Arguments:**

- `run_ids`: A space-separated list of one or more calibration run IDs.
- `file_path`: A Markdown file created by the `jobs` command. The CLI reads the run IDs from the first column.

**Example:**

```bash
ngencerf lock 1 2 3

ngencerf lock calibration_jobs_2025-11-04_1455.md
```

---

### regionalization

Generates regionalization files from one or more calibration jobs.

**Usage:**

```bash
ngencerf regionalization [run_ids ...] [--id-file ID_FILE] [--output OUTPUT]
```

**Arguments:**

- `run_ids`: One or more calibration run IDs.
- `--id-file`: (Optional) The path to a file containing calibration run IDs separated by commas, spaces, or newlines. Use either `run_ids` or `--id-file`.
- `--output`, `-o`: (Optional) The path where the generated files will be saved.

**Examples:**

```bash
ngencerf regionalization 1 2 3

ngencerf regionalization --id-file calibration_ids.txt --output ~/Downloads
```

---

### register

Registers a new user for the ngenCerf server.  The credentials will be saved in ~/.ngencerf_env.  Also see [login](#login)

**Usage:**

```bash
ngencerf register [email]
```

**Arguments:**

- `email`: (Optional) The email address to register.

**Example:**

```bash
ngencerf register user@example.com
```

---

### run

Submits a calibration run for execution.

**Usage:**

```bash
ngencerf run run_id
```

**Arguments:**

- `run_id`: The calibration run ID to submit.

**Example:**

```bash
ngencerf run 789
```

---

### show

Displays the details of a calibration job.

**Usage:**

```bash
ngencerf show run_id [--export [OUTPUT]]
```

**Arguments:**

- `run_id`: The calibration run ID to display.
- `--export`, `-e`: (Optional) Save the exported job definition to a file or directory. If no path is supplied, the default filename is used in the current directory.

The job definition is saved as an export file even when `--export` is omitted; the option allows you to choose its location or filename.

**Example:**

```bash
ngencerf show 456

ngencerf show 456 --export ./job_456.json
```

---

### status

Displays the status of a calibration job and its related jobs.

**Usage:**

```bash
ngencerf status run_id
```

**Arguments:**

- `run_id`: The calibration run ID whose status should be displayed.

**Example:**

```bash
ngencerf status 456
```

---

### unarchive

Unarchives one or more calibration jobs, restoring them to active status.

**Usage:**

```bash
ngencerf unarchive run_ids | file_path
```

**Arguments:**

- `run_ids`: A space-separated list of one or more calibration run IDs.
- `file_path`: A Markdown file created by the `jobs` command. The CLI reads the run IDs from the first column.

**Example:**

```bash
ngencerf unarchive 1 2 3

ngencerf unarchive calibration_jobs_2025-11-04_1455.md
```

---

### unlock

Unlocks one or more calibration jobs, allowing them to be deleted or archived.

**Usage:**

```bash
ngencerf unlock run_ids | file_path
```

**Arguments:**

- `run_ids`: A space-separated list of one or more calibration run IDs.
- `file_path`: A Markdown file created by the `jobs` command. The CLI reads the run IDs from the first column.

**Example:**

```bash
ngencerf unlock 1 2 3

ngencerf unlock calibration_jobs_2025-11-04_1455.md
```

---

### update

Updates an existing calibration job with new parameters from a JSON file.

**Usage:**

```bash
ngencerf update run_id input_file [--run true|false]
```

**Arguments:**

- `run_id`: The calibration run ID to update.
- `input_file`: The path to the JSON file containing the updated job parameters.
- `--run`, `-r`: (Optional) Overrides the `run_after_import` field in the JSON file. If specified without a value, it defaults to `true`.

**Example:**

```bash
ngencerf update 456 updated_job.json --run false
```

---

### url

Manages the saved ngenCerf server URLs. URL management does not require authentication.

#### add

Adds a server URL to the saved URL list and makes it the active server. Existing access and refresh tokens are cleared because tokens are server-specific.

**Usage:**

```bash
ngencerf url add URL
```

**Arguments:**

- `URL`: The ngenCerf server URL.

**Example:**

```bash
ngencerf url add https://ngencerf.example.com/api
```

#### list

Lists the saved server URLs. The active server is marked with an asterisk.

**Usage:**

```bash
ngencerf url list
```

#### current

Displays the currently selected server URL.

**Usage:**

```bash
ngencerf url current
```

#### select

Displays the saved server URLs and prompts you to select the active server by number. Existing access and refresh tokens are cleared when the active server changes.

**Usage:**

```bash
ngencerf url select
```

#### delete

Displays the saved server URLs and prompts you to select a URL to delete by number.

**Usage:**

```bash
ngencerf url delete
```

---

### version

Displays the version and build information for the installed CLI. This is useful when reporting a problem or confirming which CLI build is installed.

**Usage:**

```bash
ngencerf version
```

---

# Output Files

Several subcommands save their output to disk. By default, files are saved to the current working directory using a default name that varies by command.

You can override the default location and/or filename using the `--output` or `--export` option (depending on the command). The behavior is as follows:

- **Directory only**: If you specify a directory (e.g., `--output ~/foo/`), the default filename is used within that directory.
- **Filename only**: If you specify a filename without a directory (e.g., `--output new-file.txt`), the file is saved to the current working directory with the given name.
- **Full path**: If you specify a full path (e.g., `--output ~/foo/new-file.txt`), the file is saved exactly at that location.

**Examples:**

- `--output ~/` → saves to `~/my-default.txt`
- `--output ~/foo/` → saves to `~/foo/my-default.txt`
- `--output new-file.txt` → saves to `new-file.txt` in the current working directory
- `--output ~/foo/new-file.txt` → saves to `~/foo/new-file.txt`


# Importing and Exporting

The import/export facility allows you to export the configuration of an existing job and then import it to a new job after making any desired changes

Here is an example of exported data:

```
{
    "metadata": {
        "source_calibration_run_id": 269,
        "source_status": "Done",
        "time_range": {
            "start_time": "2013-01-01T00:00:00+00:00",
            "end_time": "2022-12-31T22:00:00+00:00"
        },
        "job_data_dir": "/ngencerf/data/ngen-cal-work/run_calib/269_peter",
        "num_catchments": 5
    },
    "run_after_import": false,
    "gage_id": "01055000",
    "forcing_source": "AORC",
    "observational_source": "Historical",
    "geopackage_source": "Hydrofabric",
    "modules": [
        "T-Route",
        "CFE-S",
        "Noah-OWP-Modular"
    ],
    "job_name": "noah_cfes_troute_01055000_clone",
    "use_sloth": false,
    "sloth_parameters": [],
    "automatic_validation": true,
    "time_controls": {
        "simulation_start_time": "2014-10-01T00:00:00Z",
        "warmup_duration": 12,
        "calibration_duration": 12,
        "validation_window_gap": 0,
        "validation_window_after_calibration": true,
        "validation_duration": 12
    },
    "threshold_categorical": 3.88,
    "threshold_event": null,
    "parameters": [
        {
            "name": "b",
            "minimum": 2.0,
            "maximum": 15.0,
            "initial_value": 4.05,
            "module": "CFE-S"
        }
    ],
    "objective_function": "KGE",
    "optimization_inputs": [
        {
            "name": "r",
            "value": 0.2
        }
    ],
    "optimization": "DDS",
    "save_plot_iteration_frequency": 1,
    "save_output_iteration": false,
    "stop_criteria": 5
}
```


The format for exported and imported data is the same. The metadata section on export contains data that, while useful, is not needed for import.
You can also use the metadata section for your own information, such as comments. It will be ignored on import.

The current format uses `time_controls` to define the simulation, warmup, calibration, and validation periods. The CLI also recognizes legacy files containing `calibration_times` and `validation_times`. 
When it detects that legacy format, it converts the time fields before sending the job to the server and saves the converted JSON beside the original file.

| Field                         | Description                                                                                                                                                            |
|-------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| source_calibration_run_id     | Metadata: ID of the job that was exported.                                                                                                                             |
| time_range                    | Metadata: Intersection of time range from the forcing data and observation data, constraining calibration and validation.                                              |
| errors                        | Metadata: Shows any outstanding errors in the job that would prevent it from running.                                                                                  |
| run_after_import              | Flag indicating whether to submit the job immediately provided all required information is available and there are no errors. Can be overridden by the `--run` option of `import` or `update`. |
| gage_id                       | The gage_id associated with the calibration job.                                                                                                                       |
| forcing_source                | The source of the forcing data.  (e.g., AORC or NWM Retrospective)                                                                                                     |
| observational_source          | The source of the observational data (e.g., Historical).                                                                                                               |
| geopackage_source             | The source of the geopackage data (e.g., Hydrofabric).                                                                                                                 |
| modules                       | The list of modules used for this calibration.                                                                                                                         |
| job_name                      | User-supplied job_name that has no effect on the job.                                                                                                             |
| use_sloth                     | Flag indicating whether the SLoTH model is used. If true, `sloth_parameters` must be provided.                                                                         |
| sloth_parameters              | Required if `use_sloth` is true. The SLoTH parameter definitions. All fields are required for each SLoTH variable.                                                     |
| module_properties             | Module-specific property values. Exported definitions include the module, property name, and effective property value.                                                 |
| automatic_validation          | If true, a validation is run automatically after the calibration run.                                                                                                  |
| time_controls                 | Defines the simulation start, warmup duration, calibration duration, validation gap, validation position, and validation duration. Durations are specified in months.   |
| threshold_categorical         | Required if a categorical objective function is specified. If empty, ngen-cal will not calculate categorical metric.                                                   |
| threshold_event               | Required if an event-based objective function is specified. If empty, ngen-cal will not calculate event-based metric.                                                  |
| parameters                    | Module parameters to use for calibration tuning including name, min, max, and module. All fields are required.                                                         |
| objective_function            | Metric to use for the objective function.                                                                                                                              |
| optimization                  | Optimization algorithm (DDS, GWO, PSO).                                                                                                                                |
| optimization_inputs           | Inputs for the selected optimization.                                                                                                                                  |
| save_plot_iteration_frequency | How often ngen-cal will generate plots during the calibration.                                                                                                         |
| save_output_iteration         | If true, output for each iteration is saved in separate files (not supported by UI).                                                                                   |
| stop_criteria                 | Number of worker iterations to run.                                                                                                                                    |
| logging_config                | ngen logging configuration exported with the job definition.                                                                                                          |


---
