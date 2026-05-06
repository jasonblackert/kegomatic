#!/bin/bash
# Development mode - runs without real hardware
# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/src"

# Use mock GPIO pins (no hardware required)
export GPIOZERO_PIN_FACTORY=mock

# Disable autostart so hardware threads don't run
python main.py --fullscreen

echo ""
echo "Note: Hardware processes may fail without GPIO/serial/database."
echo "This is expected when running on a development machine."
