#!/bin/bash

# Function to resolve ~ to the home directory
resolve_path() {
  echo "${1//\~/$HOME}"
}

# Check if required environment variables are set, otherwise exit with an error
if [ -z "$NGEN_CAL_CALIBRATION_SCRIPT" ] || [ -z "$NGEN_CAL_VALIDATION_SCRIPT" ] || [ -z "$NGEN_CAL_VALIDATION_ITERATION_SCRIPT" ]; then
  echo "Error: One or more required environment variables are not set."
  echo "Please set the following environment variables:"
  echo "  NGEN_CAL_CALIBRATION_SCRIPT"
  echo "  NGEN_CAL_VALIDATION_SCRIPT"
  echo "  NGEN_CAL_VALIDATION_ITERATION_SCRIPT"
  exit 1
fi

# Get the script paths from the environment variables, resolving ~ to the home directory
CALIB_SCRIPT=$(resolve_path "$NGEN_CAL_CALIBRATION_SCRIPT")
VALID_SCRIPT=$(resolve_path "$NGEN_CAL_VALIDATION_SCRIPT")
VALID_ITERATION_SCRIPT=$(resolve_path "$NGEN_CAL_VALIDATION_ITERATION_SCRIPT")

# Function to display help message
show_help() {
  echo "Usage: $(basename "$0") <command> <output_file> <input_file> [worker_name iteration_number] [venv_path]"
  echo ""
  echo "COMMAND:"
  echo "  calibration          Run calibration script."
  echo "  validation           Run validation script."
  echo "  validation_iteration Run validation iteration script (requires worker_name and iteration_number)."
  echo ""
  echo "OUTPUT_FILE: Path to the output file where the script's output will be saved."
  echo "INPUT_FILE:  Path to the input file required by the script."
  echo "WORKER_NAME: (Required for validation_iteration) Name of the worker."
  echo "ITERATION_NUMBER: (Required for validation_iteration) Iteration number."
  echo "VENV_PATH: Optional path to the Python virtual environment."
  echo ""
  echo "Examples:"
  echo "  $(basename "$0") calibration /path/to/output.log /path/to/input.csv"
  echo "  $(basename "$0") validation /path/to/output.log /path/to/input.csv"
  echo "  $(basename "$0") validation_iteration /path/to/output.log /path/to/input.csv worker1 5 /path/to/venv"
  echo ""
  exit 1
}

# Show help if the user requests it with --help or -h
if [[ "$1" == "--help" || "$1" == "-h" ]]; then
  show_help
fi

# Check if the command for the script is provided as the first argument
if [ -z "$1" ]; then
  echo "Error: No script command provided. Use 'calibration', 'validation', or 'validation_iteration'."
  show_help
fi

# Get the script command and select the corresponding script path
SCRIPT_COMMAND=$1
case "$SCRIPT_COMMAND" in
  "calibration")
    SCRIPT_PATH=$CALIB_SCRIPT
    REQUIRED_ARGS=1
    ;;
  "validation")
    SCRIPT_PATH=$VALID_SCRIPT
    REQUIRED_ARGS=1
    ;;
  "validation_iteration")
    SCRIPT_PATH=$VALID_ITERATION_SCRIPT
    REQUIRED_ARGS=3
    ;;
  *)
    echo "Error: Invalid script command. Use 'calibration', 'validation', or 'validation_iteration'."
    show_help
    ;;
esac

# Check if the Python output file path is provided as the second argument
if [ -z "$2" ]; then
  echo "Error: No Python output file provided."
  show_help
fi

# Get the Python output file path from the second argument
PYTHON_OUTPUT_FILE=$2
echo "           Python output file: $PYTHON_OUTPUT_FILE"

# Get the directory for the output file and create it if it doesn't exist
OUTPUT_DIR=$(dirname "$PYTHON_OUTPUT_FILE")
if [ ! -d "$OUTPUT_DIR" ]; then
  mkdir -p "$OUTPUT_DIR"
fi

# Shift the first two arguments to get the remaining inputs
shift 2

# Check if the correct number of arguments are provided for the selected command
if [ $# -lt $REQUIRED_ARGS ]; then
  echo "Error: Insufficient arguments. $SCRIPT_COMMAND requires $REQUIRED_ARGS arguments."
  show_help
fi

# Get the inputs for the command
INPUT_FILE=$1
shift 1

# Additional inputs for validation_iteration (worker_name and iteration)
if [ "$SCRIPT_COMMAND" == "validation_iteration" ]; then
  WORKER_NAME=$1
  ITERATION_NUMBER=$2
  echo "           Worker name: $WORKER_NAME"
  echo "     Iteration number: $ITERATION_NUMBER"
  shift 2
fi

# Get the virtual environment path from the optional last argument
VENV_PATH=""
if [ -n "$1" ]; then
  VENV_PATH=$1
  echo "          Virtual environment: $VENV_PATH"
fi

# Activate the virtual environment if provided
if [ -n "$VENV_PATH" ]; then
  if [ -d "$VENV_PATH/bin" ]; then
    source "$VENV_PATH/bin/activate"
  else
    echo "Error: Virtual environment path '$VENV_PATH' is invalid."
    exit 1
  fi
else
  echo "No virtual environment provided, running with default Python environment."
fi

# Run the Python script, redirecting its output to the specified file
echo "   Running $(basename "$SCRIPT_PATH") with input file: $INPUT_FILE"
if [ "$SCRIPT_COMMAND" == "validation_iteration" ]; then
  python "$SCRIPT_PATH" "$INPUT_FILE" "$WORKER_NAME" "$ITERATION_NUMBER" > "$PYTHON_OUTPUT_FILE" 2>&1
else
  python "$SCRIPT_PATH" "$INPUT_FILE" > "$PYTHON_OUTPUT_FILE" 2>&1
fi
python_exit_code=$?

if [ $python_exit_code -ne 0 ]; then
  echo "$(basename "$SCRIPT_PATH") exited with code $python_exit_code"
fi

echo "Output from running $(basename "$SCRIPT_PATH")"
echo "-------------- start of $PYTHON_OUTPUT_FILE -----------------------------"
cat "$PYTHON_OUTPUT_FILE"
echo "---------------- end of $PYTHON_OUTPUT_FILE -----------------------------"

echo "Done running $(basename "$SCRIPT_PATH")"

exit $python_exit_code
