# Kegomatic

A Raspberry Pi kiosk application that monitors up to 5 office keg taps in real time. It displays beer info, pour volume, pour cost, instantaneous flow rate, and keg fill level for each tap via a web-based UI with real-time WebSocket updates. Pour history is persisted to a local MySQL database.

---

## Hardware

### Raspberry Pi GPIO Wiring

| GPIO (BCM) | Connected To |
|---|---|
| 17 | Keg 1 flowmeter pulse |
| 27 | Keg 2 flowmeter pulse |
| 22 | Keg 3 flowmeter pulse |
| 23 | Keg 4 flowmeter pulse |
| 24 | Keg 5 flowmeter pulse |
| 25 | Wake pushbutton |
| 18 | LED strip (PWM) |
| 4  | DS18B20 temperature sensor (1-wire) |
| 2, 3 | Reserved — hardwired I2C pull-ups, cannot be reconfigured |

**TV:** Connected via RS-232C USB adapter at `/dev/ttyUSB0` (9600 baud). The app sends Panasonic RS-232C commands (`RSPW1`, `POWR1`, `POWR0`) to control TV power.

**Flowmeters:** Hall-effect pulse-output type (YF-S201 style). Each pulse from the sensor is counted; flow rate is derived from pulse frequency at 7.5 pulses/L/min.

**Temperature sensor:** DS18B20 on 1-wire bus. Detected automatically via `/sys/bus/w1/devices/28*`.

---

## Software Dependencies

### System Packages (Raspberry Pi OS)

Install system dependencies first:

```bash
# Update package list
sudo apt-get update

# Required for pywebview GUI window
sudo apt-get install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.0
sudo apt-get install pkg-config libgtk-3-dev libwebkit2gtk-4.0-dev
```

### Python Packages

```bash
pip install Flask Flask-SocketIO python-socketio pywebview gpiozero mysql-connector-python numpy pyserial
```

**Note:** If you have trouble installing `pywebview` or don't need the standalone window, you can skip it and run with the `--no-window` flag to use your browser instead.

Runs on Raspberry Pi OS. The `gpiozero` library requires either running as root or the user being in the `gpio` group.

---

## Database Setup

The app connects to a local MySQL instance:

- **Host:** localhost
- **User:** kegomatic
- **Password:** *(set in `src/config/config.env` — see `config.env.example`)*
- **Database:** keg

The `pours` table is expected to exist with at least columns for date, time, keg ID, and pour volume in liters. The app queries total volume poured per keg ID to calculate how much is left in the keg.

---

## Running the Application

```bash
# Start the kiosk (fullscreen pywebview window)
cd ~/src
python main.py --fullscreen

# Or via the convenience script
bash start_keg.sh

# Run with browser only (no pywebview window)
python main.py --no-window

# Specify custom port (default is 5000)
python main.py --port 8080

# Debug / development flags
python main.py --fullscreen --debug   # DEBUG log level
python main.py --fullscreen --info    # INFO log level
# Default (no flag) is WARNING level only
```

The app can be run from any directory as all paths are resolved relative to the script location.

---

## Updating Kegs

Kegs can be updated via the web UI settings menu or by editing the config file directly.

### Via Web UI (Recommended)

1. Click the settings button (⚙️) in the bottom-right corner of the display
2. For each tap, use the action buttons:
   - **Edit Current** — Modify keg details (name, brewery, type, ABV, IBU, cost, size, date, logo)
   - **Empty Keg** — Mark keg as empty by setting size to the amount poured (calculated from database)
   - **Replace Keg** — Swap in a new keg, preserving the old keg data in the config
3. Changes require restarting the application to take effect

### Via Config File

Edit `src/config/kegs.config` (INI format), then **restart the application**.

### Step 1 — Add a new keg entry

Append a new section with a unique 2-letter ID at the bottom of the file:

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
Logo: logo_filename.png
```

- `KegSizeL`: total keg volume in liters (e.g. `20` for a half-barrel, `30` for a full barrel)
- `CostOfKeg`: used to calculate cost-per-liter; displayed pour cost includes a **25% markup**
- `Logo`: filename from `src/logos/` — use `empty_keg.png` for a placeholder
- Keg ID `AC` is hardcoded as the "empty/no keg" placeholder — any tap pointing at `AC` will show as empty

### Step 2 — Point a tap at the new keg

Update the `[Active]` section:

```ini
[Active]
keg1: XY
keg2: AC
keg3: AC
keg4: AC
keg5: AC
```

### Step 3 — Restart the Application

```bash
# Restart the application to load the new config
pkill -f main.py
python main.py --fullscreen
```

---

## Adding a Brewery Logo

Drop a PNG into `src/logos/` and reference the filename in the keg's `Logo:` field. The image is displayed as-is (not resized by the app), so size it appropriately for the display resolution beforehand.

---

## Architecture

### Process/Thread Model

The app uses `multiprocessing.Process` for all hardware I/O, with `multiprocessing.Queue` objects passing data to the web server. Each queue has a small max size (5–10 items); items are dropped with a warning log if a queue is full.

```
[read_keg_data x5]      ──keg_data_q──▶
[monitor_temp_sensor]   ──temp_q──────▶  DataGatherer (Thread)  ──WebSocket──▶  Browser UI
[monitor_push_button]   ──pb_q────────▶  (Flask-SocketIO)                       (JavaScript)
[led_control]           ◀──led_q──────
[manage_tv_power]       ◀──tv_m2t_q───
                        ──tv_t2m_q────▶
```

- **`DataGatherer`** thread polls all queues every 100ms and emits WebSocket messages (via Flask-SocketIO) to update the browser UI in real-time.
- **`read_keg_data`** — one process per tap. Listens for GPIO pulses via `gpiozero.Button`, updates a `FlowMeter` instance, writes completed pours to MySQL, and emits log message strings.
- **`manage_tv_power`** — controls TV sleep/wake via RS-232C. The TV auto-sleeps after `SleepTimeSec` (from `[TV]` config). A pour event or pushbutton press wakes it.
- **`led_control`** — sinusoidal PWM pulse when idle (sleep state); steady 1Hz blink when active.
- **`monitor_temp_sensor`** — polls DS18B20 every 0.5s. Silently does nothing if no 1-wire sensor is found.

### FlowMeter (`src/flowmeter.py`)

Converts GPIO pulses into flow data:

- `hertz = 1000 / clickDelta_ms` (instantaneous pulse frequency)
- `flow_L_per_s = hertz / (60 × 7.5)`
- Pulses with `clickDelta ≥ 1000ms` are ignored (sensor stopped)
- Pour volume accumulates per-pulse: `instPour += flow × (clickDelta / 1000)`
- After 4 seconds of inactivity with `thisPour > 0.01L`, the pour is committed to the DB and `thisPour` is reset

### Pour State Machine (per keg)

| State | Condition |
|---|---|
| `Ready` | Keg has beer, no flow |
| `Pour Active` | `flow > 0` |
| `Pour Wait` | `thisPour > 0.01L` and no pulse for 500ms |
| `Keg Empty` | DB tally ≥ keg size, or keg ID is `AC` |
