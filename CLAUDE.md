# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Kegomatic is a Raspberry Pi kiosk application that monitors up to 5 office keg taps. It displays real-time pour data (flow rate, pour amount, cost, keg fill level) via a web-based UI using Flask, Flask-SocketIO, and pywebview. Hardware is interfaced via GPIO (flowmeters, temperature sensor, pushbutton, LED strip) and serial (TV power control).

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

The app uses `multiprocessing.Queue` objects to pass data between hardware worker processes and the web UI. The main thread runs Flask/Flask-SocketIO. A `DataGatherer` thread polls all the queues every 100ms and emits WebSocket messages to update the browser UI in real-time.

Hardware workers communicate via queues:
- `keg_data{1-5}` — flow data dicts from each keg's flowmeter process
- `keg_message{1-5}` — log message strings for the activity log
- `pb_data` — pushbutton state (wakes TV)
- `led_data` — commands to the LED controller
- `temp_sensor_data` — DS18B temperature readings
- `tv_message_m2t` / `tv_message_t2m` — main↔TV serial thread messages

### Key Files

- `src/main.py` — Entry point that spawns hardware worker processes, starts Flask server, and launches pywebview window
- `src/web_server.py` — Flask/Flask-SocketIO server with REST API and WebSocket handlers; `DataGatherer` thread
- `src/hardware.py` — Hardware worker functions (flowmeters, temperature, LED, TV control, pushbutton)
- `src/flowmeter.py` — `FlowMeter` class: converts GPIO pulse interrupts into Hz → L/s → pour volume (liters or pints)
- `src/static/index.html` — Main web UI with keg display table and settings modal
- `src/static/app.js` — WebSocket client, real-time UI updates, settings management
- `src/static/style.css` — UI styling with 7-segment display font and dark theme
- `src/config/kegs.config` — INI-style config (see below)
- `src/logos/` — brewery logo PNGs referenced by keg config entries

### FlowMeter Math

Flow rate: `hertz = 1000 / clickDelta_ms`, then `flow_L_per_s = hertz / (60 * 7.5)`. Pulses with `clickDelta >= 1000ms` are ignored (flow stopped). Pour volume accumulates incrementally: `instPour = flow * (clickDelta / 1000)`.

## Updating Kegs

Kegs can be updated via the web UI settings menu (⚙️ button) or by editing `src/config/kegs.config` (INI format):

### Via Web UI (Preferred)
1. Click the settings button (⚙️) in the bottom-right corner
2. For each tap, choose:
   - **Edit Current** — Modify keg details (name, brewery, type, ABV, IBU, cost, size, date, logo)
   - **Empty Keg** — Mark keg as empty by setting size to the amount poured (calculated from database)
   - **Replace Keg** — Swap in a new keg, preserving the old keg data in the config
3. Restart the application for changes to take effect

### Via Config File
Edit `src/config/kegs.config`:

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

3. Restart the application.

The `[TV]` section configures the serial port used for TV power control (`/dev/ttyUSB0` by default), baud rate, and sleep timer.

## Dependencies

### Important Note for Python 3.13+
**pywebview may not be compatible with Python 3.13+**. It works well on Python 3.9-3.12. If using Python 3.13+:
- The app will automatically fall back to browser mode
- Or use `--no-window` flag explicitly
- Or downgrade to Python 3.9-3.12 if you need the window feature

### System Packages (Raspberry Pi OS)

**Option 1: GTK Backend (try first)**
```bash
sudo apt-get install python3-gi python3-gi-cairo gir1.2-gtk-3.0
sudo apt-get install pkg-config libgtk-3-dev

# Try to install webkit2gtk (package name varies by OS version)
sudo apt-get install gir1.2-webkit2-4.1  # or gir1.2-webkit2-4.0
```

**Option 2: QT Backend (if GTK doesn't work)**
```bash
sudo apt-get install python3-pyqt5 python3-pyqt5.qtwebengine
```

**Option 3: Skip GUI Window Entirely (recommended for Python 3.13)**
Run with `--no-window` flag to use browser instead of pywebview window.

### Python Packages
`Flask`, `Flask-SocketIO`, `python-socketio`, `gpiozero`, `mysql-connector-python`, `numpy`, `pyserial`

**Note:** `pywebview` is optional and **not compatible with Python 3.13**. The app will automatically fall back to opening a browser if pywebview fails. Use `--no-window` flag for explicit browser-only mode.

Runs on Raspberry Pi OS. GPIO pins 2/3 have hardware pull-ups (I2C) and cannot be reconfigured. Pin 4 is reserved for 1-wire (temperature sensor).

## Database

Pour data is written to a local MySQL database (`host=localhost`, `user=kegomatic`, `database=keg`). See `src/scripts/zeroEmptyKeg.py` for an example of direct DB interaction.
