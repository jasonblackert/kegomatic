#!/bin/bash
# Kegomatic Web UI Launcher
# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/src"

# Use mock GPIO pins for development (no hardware required)
export GPIOZERO_PIN_FACTORY=mock

# Launch web version
echo "=========================================="
echo " Kegomatic Web UI"
echo "=========================================="
echo ""

python main.py "$@"
