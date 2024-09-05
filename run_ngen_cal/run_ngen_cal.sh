#!/bin/bash

# Check if the virtual environment path is provided as an argument
if [ -z "$1" ]; then
  echo "Error: No virtual environment path provided."
  exit 1
fi

# Check if the Python output file path is provided as an argument
if [ -z "$2" ]; then
  echo "Error: No Python output file provided."
  exit 1
fi

# Check if the script path is provided as an argument
if [ -z "$3" ]; then
  echo "Error: No script path provided."
  exit 1
fi

# Get the virtual environment path from the first argument
VENV_PATH=$1
echo "Virtual environment: $VENV_PATH"

# Get the Python output file path from the second argument
PYTHON_OUTPUT_FILE=$2
echo "Python output file: $PYTHON_OUTPUT_FILE"

# Get the Python script path from the third argument
SCRIPT_PATH=$3
echo "Python script: $SCRIPT_PATH"

# Shift the first three arguments so that the remaining ones are Python script arguments
shift 3

echo "Arguments to Python: $*"

# Activate the virtual environment
source "$VENV_PATH/bin/activate"

# Run the Python script, redirecting its output to the specified file
echo "Running $(basename "$SCRIPT_PATH")"
python "$SCRIPT_PATH" "$@" > "$PYTHON_OUTPUT_FILE" 2>&1
