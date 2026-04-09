# Kegomatic

A Raspberry Pi kiosk application that monitors up to 5 office keg taps in real time. It displays beer info, pour volume, pour cost, instantaneous flow rate, and keg fill level for each tap on a fullscreen PyQt6 GUI. Pour history is persisted to a local MySQL database.

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

```bash
pip install PyQt6 gpiozero mysql-connector-python numpy pyserial
```

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
# Start the kiosk (fullscreen, auto-start polling)
cd ~/src
python main.py --autostart --fullscreen

# Or via the convenience script
bash start_keg.sh

# Debug / development flags
python main.py --autostart --fullscreen --debug   # DEBUG log level
python main.py --autostart --fullscreen --info    # INFO log level
# Default (no flag) is WARNING level only
```

The app must be run from `src/` because it resolves paths to `config/kegs.config` and `logos/` relative to the working directory.

---

## Updating Kegs

Edit `src/config/kegs.config` (INI format), then **reboot the Pi**.

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

### Step 3 — Reboot

```bash
sudo reboot
```

---

## Adding a Brewery Logo

Drop a PNG into `src/logos/` and reference the filename in the keg's `Logo:` field. The image is displayed as-is (not resized by the app), so size it appropriately for the display resolution beforehand.

---

## Architecture

### Process/Thread Model

The app uses `multiprocessing.Process` for all hardware I/O, with `multiprocessing.Queue` objects passing data to the UI. Each queue has a small max size (5–10 items); items are dropped with a warning log if a queue is full.

```
[read_keg_data x5]  ──keg_data_q──▶
[monitor_temp_sensor] ──temp_q────▶  gatherDataThread (QThread)  ──Qt signals──▶  MainWindow (PyQt6)
[monitor_push_button] ──pb_q──────▶
[led_control]       ◀──led_q──────
[manage_tv_power]   ◀──tv_m2t_q──
                    ──tv_t2m_q──▶
```

- **`gatherDataThread`** polls all queues every 100ms and emits Qt signals to update LCD displays, progress bars, and labels in `MainWindow`.
- **`read_keg_data`** — one process per tap. Listens for GPIO pulses via `gpiozero.Button`, updates a `FlowMeter` instance, writes completed pours to MySQL, and emits a log message string.
- **`manage_tv_power`** — controls TV sleep/wake via RS-232C. The TV auto-sleeps after `SleepTimeSec` (from `[TV]` config). A pour event or pushbutton press wakes it. **Note:** the wake-on-pour code path has a bug (`if wake_tv == "Help me"` is never true); the TV currently only wakes from a button press.
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
