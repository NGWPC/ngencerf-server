#!/usr/bin/env python3
"""
ngencerf CLI entry point.

Supports import, export, show, run, delete, cancel, register, and download commands
for managing calibration jobs via a REST API.
"""

import argparse
import os
import sys

from ngencerf.cli_functions import (
    import_job,
    update_job,
    run_job,
    delete_job,
    cancel_job,
    handle_export_display,
    list_jobs,
    upload_observational_data,
    upload_forcing_data,
    upload_geopackage_data,
    download_zip,
)
from ngencerf.cli_user import ngen_login, ngen_register


class SmartArgumentParser(argparse.ArgumentParser):
    """
    Custom ArgumentParser that prints subparser-specific help if available
    when a command is missing required arguments or is invalid.
    """

    def error(self, message):
        if len(sys.argv) > 1:
            cmd = sys.argv[1]
            subcommands = [
                action.choices.keys()
                for action in self._subparsers._group_actions
                if isinstance(action, argparse._SubParsersAction)
            ]
            subcommands = list(subcommands[0]) if subcommands else []

            if cmd in subcommands:
                self.parse_args([cmd, "--help"])
                self.exit(2, f"\nerror: {message}\n")
            else:
                self.exit(
                    2,
                    f"\nerror: unknown command '{cmd}'\n"
                    f"       available commands: {', '.join(subcommands)}\n\n"
                    f"Try '{self.prog} <command> --help' for more info.\n"
                )

        super().error(message)


class ParseBoolAction(argparse.Action):
    """
    Custom argparse action to parse boolean flags.

    Supports usage like:
        --flag              → True
        --flag true         → True
        --flag false        → False
    """

    def __init__(self, option_strings, dest, nargs=None, **kwargs):
        if nargs is not None and nargs != '?':
            raise ValueError("nargs must be '?' to allow optional value")
        super().__init__(option_strings, dest, nargs='?', **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        if values is None:
            setattr(namespace, self.dest, True)
        else:
            val = values.lower()
            if val in {"true", "1", "yes", "y"}:
                setattr(namespace, self.dest, True)
            elif val in {"false", "0", "no", "n"}:
                setattr(namespace, self.dest, False)
            else:
                raise argparse.ArgumentError(self, f"Invalid boolean value: '{values}'")


# Commands that do not require authentication
COMMANDS_AUTH_EXEMPT = {"register"}

# Default download directory (fallbacks to cwd if ~/Downloads is missing)
DEFAULT_DOWNLOAD_DIR = os.path.expanduser("~/Downloads")
if not os.path.isdir(DEFAULT_DOWNLOAD_DIR):
    DEFAULT_DOWNLOAD_DIR = os.getcwd()

# Command handler map (command → function(args))
COMMAND_HANDLERS = {
    "import": lambda args: import_job(job_file=args.input_file),
    "update": lambda args: update_job(calibration_run_id=args.run_id, job_file=args.input_file),
    "upload-obs": lambda args: upload_observational_data(args.csv_file, args.run_id),
    "upload-forcing": lambda args: upload_forcing_data(args.forcing_dir, args.run_id),
    "upload-geopkg": lambda args: upload_geopackage_data(args.gpkg_file, args.run_id),
    "export": lambda args: handle_export_display(
        calibration_run_id=args.run_id,
        output=args.output or DEFAULT_DOWNLOAD_DIR,
        display=args.show,
    ),
    "show": lambda args: handle_export_display(
        calibration_run_id=args.run_id,
        output=args.output if args.output or args.export else None,
        display=True,
    ),
    "run": lambda args: run_job(args.run_id),
    "delete": lambda args: delete_job(args.run_id),
    "cancel": lambda args: cancel_job(args.run_id),
    "jobs": lambda args: list_jobs(),
    "download": lambda args: download_zip(args.run_id, output_path=args.output or DEFAULT_DOWNLOAD_DIR),
    "register": lambda args: ngen_register(args.email),
}


def main():
    """
    Main entry point for the ngencerf CLI.

    Parses command-line arguments, handles authentication,
    and dispatches to the appropriate command handler.
    """
    # Store subparser references for help fallback
    subparser_map = {}

    usage = f"%(prog)s [{'|'.join(COMMAND_HANDLERS.keys())}] <args> [--flags]"
    parser = SmartArgumentParser(
        description="ngencerf CLI tool",
        usage=usage
    )
    parser.subparser_map = subparser_map

    subparsers = parser.add_subparsers(
        dest="command",
        title="commands",
        metavar="",
        required=True
    )

    # Register each subcommand parser
    def add_parser(name, *args, **kwargs):
        p = subparsers.add_parser(name, *args, **kwargs)
        subparser_map[name] = p
        return p

    # ───────────── Subcommand Definitions ─────────────

    import_parser = add_parser("import", help="Import JSON job file")
    import_parser.add_argument("input_file", help="Path to the JSON file")

    update_parser = add_parser("update", help="Update job from a JSON file")
    update_parser.add_argument("run_id", help="Calibration run ID")
    update_parser.add_argument("input_file", help="Path to the JSON file")

    observation_parser = add_parser("upload-obs", help="Upload observational data CSV for a calibration run")
    observation_parser.add_argument("run_id", help="Calibration run ID")
    observation_parser.add_argument("csv_file", help="Path to the observational CSV file")

    forcing_parser = add_parser("upload-forcing", help="Upload a directory of forcing files for a calibration run")
    forcing_parser.add_argument("run_id", help="Calibration run ID")
    forcing_parser.add_argument("forcing_dir", help="Path to directory containing forcing files")

    gpkg_parser = add_parser("upload-geopkg", help="Upload a GPKG file for a calibration run")
    gpkg_parser.add_argument("run_id", help="Calibration run ID")
    gpkg_parser.add_argument("gpkg_file", help="Path to the geopackage (.gpkg) file")

    export_parser = add_parser("export", help="Export job to JSON")
    export_parser.add_argument("run_id", help="Calibration run ID")
    export_parser.add_argument("--output", help="Path to save file or directory")
    export_parser.add_argument(
        "--show",
        action=ParseBoolAction,
        nargs="?",
        default=False,
        help="Also display the job (true/false, default: false)",
    )

    show_parser = add_parser("show", help="Display job details")
    show_parser.add_argument("run_id", help="Calibration run ID")
    show_parser.add_argument("--output", help="Path to save file or directory")
    show_parser.add_argument(
        "--export",
        action=ParseBoolAction,
        nargs="?",
        default=False,
        help="Also export the job to a file (true/false, default: false)",
    )

    run_parser = add_parser("run", help="Submit calibration run")
    run_parser.add_argument("run_id", help="Calibration run ID")

    delete_parser = add_parser("delete", help="Delete job")
    delete_parser.add_argument("run_id", help="Calibration run ID")

    cancel_parser = add_parser("cancel", help="Cancel job")
    cancel_parser.add_argument("run_id", help="Calibration run ID")

    jobs_parser = add_parser("jobs", help="List jobs")

    download_parser = add_parser("download", help="Download ZIP file for calibration run")
    download_parser.add_argument("run_id", help="Calibration run ID")
    download_parser.add_argument("--output", help="Path to save ZIP file or directory")

    register_parser = add_parser("register", help="Register new user")
    register_parser.add_argument("email", nargs="?", help="Email address")

    # ───────────── Show help if only a subcommand is provided ─────────────
    if len(sys.argv) == 2:
        cmd = sys.argv[1]
        if cmd in subparser_map:
            subparser_map[cmd].print_help()
            sys.exit(1)

    # Parse full arguments
    args = parser.parse_args()

    # Authenticate if needed
    if args.command not in COMMANDS_AUTH_EXEMPT and "ACCESS_TOKEN" not in os.environ:
        ngen_login()

    # Call appropriate handler
    handler = COMMAND_HANDLERS.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
