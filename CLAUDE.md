# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Kegomatic is a Raspberry Pi kiosk application that monitors up to 5 office keg taps. It displays real-time pour data (flow rate, pour amount, cost, keg fill level) via a PyQt6 fullscreen GUI. Hardware is interfaced via GPIO (flowmeters, temperature sensor, pushbutton, LED strip) and serial (TV power control).

## Running the Application

```bash
# From the repository root, use the start script
bash start_keg.sh

# Or run directly from the src directory
cd src
python main.py --autostart --fullscreen

# Or run from anywhere
python /path/to/kegomatic/src/main.py --autostart --fullscreen
```

All paths are now relative to the script location, so the app can be run from any directory.

## Architecture

### Process/Thread Model

The app uses `multiprocessing.Queue` objects to pass data between hardware worker processes and the UI. The main thread runs PyQt6. A `gatherDataThread` (QThread) polls all the queues every 100ms and emits Qt signals to update UI widgets.

Hardware workers communicate via queues:
- `keg_data{1-5}` — flow data dicts from each keg's flowmeter process
- `keg_message{1-5}` — log message strings for the scrolling log box
- `pb_data` — pushbutton state (wakes TV)
- `led_data` — commands to the LED controller
- `temp_sensor_data` — DS18B temperature readings
- `tv_message_m2t` / `tv_message_t2m` — main↔TV serial thread messages

### Key Files

- `src/main.py` — PyQt6 `MainWindow`, `gatherDataThread`, and all hardware process/thread spawning at the bottom
- `src/flowmeter.py` — `FlowMeter` class: converts GPIO pulse interrupts into Hz → L/s → pour volume (liters or pints)
- `src/config/kegs.config` — INI-style config (see below)
- `src/logos/` — brewery logo PNGs referenced by keg config entries

### FlowMeter Math

Flow rate: `hertz = 1000 / clickDelta_ms`, then `flow_L_per_s = hertz / (60 * 7.5)`. Pulses with `clickDelta >= 1000ms` are ignored (flow stopped). Pour volume accumulates incrementally: `instPour = flow * (clickDelta / 1000)`.

## Updating Kegs

Edit `src/config/kegs.config` (INI format):

1. Add a new keg section with a unique 2-letter ID at the bottom:
   ```ini
   [XY]
   Name: Beer Name
   Brewery: Brewery Name
   Type: Style
   ABV: 5.0
   IBU: 30
   CostOfKeg: 100
   KegSizeL: 20
   PurchaseDate: MMDDYYYY
   Logo: logo_file.png
   ```

2. Update `[Active]` to point the desired tap at the new ID:
   ```ini
   [Active]
   keg1: XY
   ```

3. Reboot the Pi.

The `[TV]` section configures the serial port used for TV power control (`/dev/ttyUSB0` by default).

## Dependencies

Python packages: `PyQt6`, `gpiozero`, `mysql-connector-python`, `numpy`, `pyserial`

Runs on Raspberry Pi OS. GPIO pins 2/3 have hardware pull-ups (I2C) and cannot be reconfigured. Pin 4 is reserved for 1-wire (temperature sensor).

## Database

Pour data is written to a local MySQL database (`host=localhost`, `user=kegomatic`, `database=keg`). See `src/scripts/zeroEmptyKeg.py` for an example of direct DB interaction.
