#!/bin/bash
# Kegomatic Web UI Launcher
# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/src"

# Define log file path
LOG_FILE="$SCRIPT_DIR/kegomatic.log"

# IMPORTANT: Comment out the line below when running on Raspberry Pi with real hardware!
# Use mock GPIO pins for development (no hardware required)
# export GPIOZERO_PIN_FACTORY=mock

# Check if running on Raspberry Pi
if [ -d "/sys/class/gpio" ] && [ -f "/proc/device-tree/model" ]; then
    echo "Detected Raspberry Pi - using real GPIO"
else
    echo "Not running on Raspberry Pi - using mock GPIO for development"
    export GPIOZERO_PIN_FACTORY=mock
fi

# Blank out the log file (start fresh each run)
> "$LOG_FILE"

# Launch web version
echo "=========================================="
echo " Kegomatic Web UI"
echo "=========================================="
echo ""
echo "Logging all output to: $LOG_FILE"
echo ""

# Parse command line arguments
VERBOSE=false
ARGS=""

for arg in "$@"; do
    if [ "$arg" = "-v" ] || [ "$arg" = "--verbose" ]; then
        VERBOSE=true
    else
        ARGS="$ARGS $arg"
    fi
done

# Set logging level based on verbose flag
if [ "$VERBOSE" = true ]; then
    echo "Verbose mode enabled (--info logging)"
    # Check if user already specified --debug, otherwise add --info
    if [[ ! "$ARGS" =~ "--debug" ]]; then
        ARGS="--info $ARGS"
    fi
else
    echo "Normal mode (errors and warnings only, use -v for verbose)"
    # Don't add any log level flag - will default to WARNING
fi

# Run Python app with all output (stdout and stderr) piped to both terminal and log file
# The 2>&1 redirects stderr to stdout, then tee duplicates to both terminal and log file
python main.py $ARGS 2>&1 | tee -a "$LOG_FILE"
