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
  echo "Usage: $(basename "$0") <command> <input_file> [worker_name iteration_number] [output_file] [venv_path]"
  echo ""
  echo "COMMAND:"
  echo "  calibration          Run calibration script."
  echo "  validation           Run validation script."
  echo "  validation_iteration Run validation iteration script (requires worker_name and iteration_number)."
  echo ""
  echo "INPUT_FILE: Path to the input file required by the script."
  echo "WORKER_NAME: (Required for validation_iteration) Name of the worker."
  echo "ITERATION_NUMBER: (Required for validation_iteration) Iteration number."
  echo "OUTPUT_FILE (optional): Path to the output file where the script's output will be saved.  Used when running in the LOCAL or DOCKER environment"
  echo "VENV_PATH (optional): Path to the Python virtual environment.  Used when running in the LOCAL or DOCKER environment."
  echo ""
  echo "Examples:"
  echo "  $(basename "$0") calibration /path/to/input.csv"
  echo "  $(basename "$0") validation /path/to/input.csv"
  echo "  $(basename "$0") validation_iteration /path/to/input.csv worker1 5 /path/to/output.log /path/to/venv"
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
shift 1

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

# Check if the correct number of arguments are provided for the selected command
if [ $# -lt $REQUIRED_ARGS ]; then
  echo "Error: Insufficient arguments. $SCRIPT_COMMAND requires $REQUIRED_ARGS arguments."
  show_help
fi

# Get the input file and additional parameters for validation_iteration
INPUT_FILE=$1
shift 1
echo "             Input file: $INPUT_FILE"

if [ "$SCRIPT_COMMAND" == "validation_iteration" ]; then
  WORKER_NAME=$1
  ITERATION_NUMBER=$2
  echo "           Worker name: $WORKER_NAME"
  echo "     Iteration number: $ITERATION_NUMBER"
  shift 2
fi

# Check if the output file and venv path are provided (both must be specified if provided)
PYTHON_OUTPUT_FILE=""
VENV_PATH=""

if [ $# -eq 2 ]; then
  PYTHON_OUTPUT_FILE=$1
  VENV_PATH=$2
  echo "           Output file: $PYTHON_OUTPUT_FILE"
  echo "        Virtual environment: $VENV_PATH"

  # Create output directory if it doesn't exist
  OUTPUT_DIR=$(dirname "$PYTHON_OUTPUT_FILE")
  if [ ! -d "$OUTPUT_DIR" ]; then
    mkdir -p "$OUTPUT_DIR"
  fi
elif [ $# -ne 0 ]; then
  echo "Error: Both output_file and venv_path must be specified together or omitted."
  show_help
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

# Run the Python script, redirecting its output if an output file is provided
echo "   Running $(basename "$SCRIPT_PATH") with input file: $INPUT_FILE"
if [ "$SCRIPT_COMMAND" == "validation_iteration" ]; then
  if [ -z "$PYTHON_OUTPUT_FILE" ]; then
    python "$SCRIPT_PATH" "$INPUT_FILE" "$WORKER_NAME" "$ITERATION_NUMBER"
  else
    python "$SCRIPT_PATH" "$INPUT_FILE" "$WORKER_NAME" "$ITERATION_NUMBER" > "$PYTHON_OUTPUT_FILE" 2>&1
  fi
else
  if [ -z "$PYTHON_OUTPUT_FILE" ]; then
    python "$SCRIPT_PATH" "$INPUT_FILE"
  else
    python "$SCRIPT_PATH" "$INPUT_FILE" > "$PYTHON_OUTPUT_FILE" 2>&1
  fi
fi

python_exit_code=$?

if [ $python_exit_code -ne 0 ]; then
  echo "$(basename "$SCRIPT_PATH") exited with code $python_exit_code"
fi

# Display output if redirected to a file
if [ -n "$PYTHON_OUTPUT_FILE" ]; then
  echo "Output from running $(basename "$SCRIPT_PATH")"
  echo "-------------- start of $PYTHON_OUTPUT_FILE -----------------------------"
  cat "$PYTHON_OUTPUT_FILE"
  echo "---------------- end of $PYTHON_OUTPUT_FILE -----------------------------"
fi

echo "Done running $(basename "$SCRIPT_PATH")"

exit $python_exit_code
