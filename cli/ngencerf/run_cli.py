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
    Custom ArgumentParser that correctly formats subcommand usage without duplicating the full command list.

    This subclass provides better error messages for unknown commands and
    automatically registers subparsers to avoid duplication.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._subparsers: None | argparse._SubParsersAction = None

    def set_subparsers(self, subparsers_action: argparse._SubParsersAction) -> None:
        """
        Store a reference to the subparsers action for later use in error handling.

        This method is necessary because argparse does not directly expose the subparsers
        once created, making it difficult to provide custom error handling for unknown commands.

        :param subparsers_action: The argparse._SubParsersAction object created by add_subparsers().
        :raises TypeError: If the provided action is not an instance of argparse._SubParsersAction.
        """
        if not isinstance(subparsers_action, argparse._SubParsersAction):
            raise TypeError(f"Expected _SubParsersAction, got {type(subparsers_action)}")
        self._subparsers = subparsers_action  # type: ignore

    def format_usage(self):
        """
        Customize the usage message to show only the subcommand syntax.

        This makes the usage message more concise by stripping the full program path
        and showing only the relevant subcommand syntax.
        """
        usage = super().format_usage()
        prog = self.prog.split()[-1]  # Only keep the subcommand part
        if prog:
            usage = usage.replace(self.prog, prog, 1)
        return usage.strip()

    def error(self, message):
        """
        Override the default error handling to provide more user-friendly messages.

        This method handles unknown commands gracefully, displaying a concise error
        message without the full traceback.
        """
        # Extract the command name if present
        cmd = sys.argv[1] if len(sys.argv) > 1 else None

        # Handle unknown commands
        if self._subparsers and cmd not in self._subparsers._name_parser_map:
            print(f"\nerror: unknown command '{cmd}'\n", flush=True)
            self.print_help()
            self.exit(2)

        # Default error handling for known commands
        print(f"\nerror: {message}\n", flush=True)
        self.print_help()
        self.exit(2)


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


def main():
    """
    Main entry point for the ngencerf CLI.

    Parses command-line arguments, handles authentication,
    and dispatches to the appropriate command handler.
    """
    parser = SmartArgumentParser(
        prog="ngencerf",
        description="ngencerf CLI tool",
        formatter_class=argparse.HelpFormatter,
        conflict_handler='resolve',
        usage="ngencerf [command] [options]"
    )

    # Register subparsers and set the reference on the main parser
    subparsers = parser.add_subparsers(
        dest="command",
        title="commands",
        metavar="",
        required=True
    )

    # Attach the subparsers to the main parser
    parser.set_subparsers(subparsers)

    def add_parser(name, help_text):
        """
        Create a subparser for a specific command.

        :param name: The name of the subcommand (e.g., 'import', 'update').
        :param help_text: The description text for the subcommand.
        :return: The created subparser.
        """
        # Create the subparser without the default help action
        subparser = parser._subparsers.add_parser(
            name,
            help=help_text,
            add_help=False,  # Prevent the default -h/--help conflict
            description=help_text,
            formatter_class=argparse.HelpFormatter,
            conflict_handler='resolve',  # Avoid conflict when adding the help action
            usage=f"{parser.prog} {name} [-h] [--flags] <args>"
        )

        # Remove any pre-existing -h/--help actions (if present)
        help_actions = [a for a in subparser._actions if isinstance(a, argparse._HelpAction)]
        for action in help_actions:
            subparser._remove_action(action)

        # Add the custom help action back
        subparser.add_argument(
            '-h', '--help',
            action='help',
            help='show this help message and exit'
        )

        # Ensure the subparser is properly registered
        if isinstance(parser._subparsers, argparse._SubParsersAction):
            subparser_action = parser._subparsers
            subparser_action.choices[name] = subparser

        return subparser

    # Registering all the subcommands
    import_parser = add_parser("import", "Import JSON job file")
    import_parser.add_argument("input_file", help="Path to the JSON file")
    import_parser.set_defaults(func=lambda args: import_job(job_file=args.input_file))

    update_parser = add_parser("update", "Update job from a JSON file")
    update_parser.add_argument("run_id", help="Calibration run ID")
    update_parser.add_argument("input_file", help="Path to the JSON file")
    update_parser.set_defaults(func=lambda args: update_job(calibration_run_id=args.run_id, job_file=args.input_file))

    observation_parser = add_parser("upload-obs", "Upload observational data CSV for a calibration run")
    observation_parser.add_argument("run_id", help="Calibration run ID")
    observation_parser.add_argument("csv_file", help="Path to the observational CSV file")
    observation_parser.set_defaults(func=lambda args: upload_observational_data(args.csv_file, args.run_id))

    forcing_parser = add_parser("upload-forcing", "Upload a directory of forcing files for a calibration run")
    forcing_parser.add_argument("run_id", help="Calibration run ID")
    forcing_parser.add_argument("forcing_dir", help="Path to directory containing forcing files")
    forcing_parser.set_defaults(func=lambda args: upload_forcing_data(args.forcing_dir, args.run_id))

    gpkg_parser = add_parser("upload-geopkg", "Upload a GPKG file for a calibration run")
    gpkg_parser.add_argument("run_id", help="Calibration run ID")
    gpkg_parser.add_argument("gpkg_file", help="Path to the geopackage (.gpkg) file")
    gpkg_parser.set_defaults(func=lambda args: upload_geopackage_data(args.gpkg_file, args.run_id))

    export_parser = add_parser("export", "Export job to JSON")
    export_parser.add_argument("run_id", help="Calibration run ID")
    export_parser.add_argument("--output", help="Path to save file or directory")
    export_parser.add_argument("--show", action=ParseBoolAction, nargs="?", default=False, help="Also display the job")
    export_parser.set_defaults(func=lambda args: handle_export_display(
        calibration_run_id=args.run_id,
        output=args.output or DEFAULT_DOWNLOAD_DIR,
        display=args.show,
    ))

    show_parser = add_parser("show", "Display job details")
    show_parser.add_argument("run_id", help="Calibration run ID")
    show_parser.add_argument("--output", help="Path to save file or directory")
    show_parser.add_argument("--export", action=ParseBoolAction, nargs="?", default=False, help="Also export the job")
    show_parser.set_defaults(func=lambda args: handle_export_display(
        calibration_run_id=args.run_id,
        output=args.output if args.output or args.export else None,
        display=True,
    ))

    run_parser = add_parser("run", "Submit calibration run")
    run_parser.add_argument("run_id", help="Calibration run ID")
    run_parser.set_defaults(func=lambda args: run_job(args.run_id))

    delete_parser = add_parser("delete", "Delete job")
    delete_parser.add_argument("run_id", help="Calibration run ID")
    delete_parser.set_defaults(func=lambda args: delete_job(args.run_id))

    cancel_parser = add_parser("cancel", "Cancel job")
    cancel_parser.add_argument("run_id", help="Calibration run ID")
    cancel_parser.set_defaults(func=lambda args: cancel_job(args.run_id))

    jobs_parser = add_parser("jobs", "List jobs")
    jobs_parser.set_defaults(func=lambda args: list_jobs())

    download_parser = add_parser("download", "Download ZIP file for calibration run")
    download_parser.add_argument("run_id", help="Calibration run ID")
    download_parser.add_argument("--output", help="Path to save ZIP file or directory")
    download_parser.set_defaults(func=lambda args: download_zip(args.run_id, output_path=args.output or DEFAULT_DOWNLOAD_DIR))

    register_parser = add_parser("register", "Register new user")
    register_parser.add_argument("email", nargs="?", help="Email address")
    register_parser.set_defaults(func=lambda args: ngen_register(args.email))

    # Parse arguments and execute the selected command
    args = parser.parse_args()

    # Authenticate if needed
    if args.command not in COMMANDS_AUTH_EXEMPT and "ACCESS_TOKEN" not in os.environ:
        ngen_login()

    # Call the appropriate handler
    if hasattr(args, "func"):
        args.func(args)
    else:
        print(f"No handler found for command: {args.command}")
        parser.print_help()
        parser.exit(1)


if __name__ == "__main__":
    main()
