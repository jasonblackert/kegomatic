#!/usr/bin/env python
"""
Kegomatic Web Main Entry Point
Starts hardware workers, Flask server, and pywebview window
"""
import os
import sys
import time
import logging
import argparse
import threading
import multiprocessing
import configparser
import signal
import inspect

# Add current directory to path for imports
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# Import hardware workers and utilities (no GUI dependencies)
from hardware import (
    read_keg_data, monitor_temp_sensor, manage_tv_power,
    monitor_push_button, led_control, ConfigSectionMap, Config
)

# Import web server
from web_server import create_app, DataGatherer


def launch_browser_fullscreen(url, fullscreen=False):
    """Launch browser in fullscreen mode using command-line arguments"""
    import webbrowser
    import subprocess
    import shutil

    print(f"launch_browser_fullscreen called: url={url}, fullscreen={fullscreen}")

    # If fullscreen not requested, use default browser
    if not fullscreen:
        print("Fullscreen not requested, using default browser")
        webbrowser.open(url)
        return

    # Try to launch Chromium/Chrome in fullscreen kiosk mode
    chrome_paths = [
        '/usr/bin/chromium-browser',
        '/usr/bin/chromium',
        '/usr/bin/google-chrome',
        '/usr/bin/chrome',
        shutil.which('chromium-browser'),
        shutil.which('chromium'),
        shutil.which('google-chrome'),
        shutil.which('chrome')
    ]

    print(f"Checking Chrome paths: {chrome_paths}")

    chrome_cmd = None
    for path in chrome_paths:
        if path and os.path.exists(path):
            chrome_cmd = path
            print(f"✓ Found Chrome/Chromium at: {chrome_cmd}")
            break

    if not chrome_cmd:
        print("Chrome/Chromium not found in any expected location")

    if chrome_cmd:
        try:
            print(f"Attempting to launch Chromium/Chrome: {chrome_cmd}")
            # Use kiosk mode which forces fullscreen correctly on Raspberry Pi
            subprocess.Popen([
                chrome_cmd,
                '--kiosk',
                '--noerrdialogs',
                '--disable-infobars',
                url
            ])
            print(f"✓ Launched Chromium/Chrome in fullscreen mode: {chrome_cmd}")
            return
        except Exception as e:
            print(f"Warning: Could not launch Chromium/Chrome in fullscreen: {e}")
            print(f"Falling back to Firefox...")

    # Try Firefox as fallback
    firefox_paths = [
        '/usr/bin/firefox',
        '/usr/bin/firefox-esr',
        shutil.which('firefox'),
        shutil.which('firefox-esr')
    ]

    firefox_cmd = None
    for path in firefox_paths:
        if path and os.path.exists(path):
            firefox_cmd = path
            break

    if firefox_cmd:
        try:
            subprocess.Popen([
                firefox_cmd,
                '--kiosk',
                url
            ])
            print(f"✓ Launched Firefox in fullscreen mode: {firefox_cmd}")
            return
        except Exception as e:
            print(f"Warning: Could not launch Firefox in fullscreen: {e}")

    # Fallback to default browser
    print("Chrome/Firefox not found, using default browser (press F11 for fullscreen)")
    webbrowser.open(url)


def stop_workers(workers):
    """
    Stop all hardware worker processes cleanly
    Reuses logic from MainWindow.stop_getting_data()
    """
    print("Stopping all hardware workers...")

    for name, proc in workers:
        try:
            print(f"Shutting down {name}...")
            proc.shutdown()
            proc.join(timeout=5)
            if proc.is_alive():
                print(f"Warning: {name} did not exit cleanly, terminating...")
                proc.terminate()
                proc.join(timeout=2)
                if proc.is_alive():
                    print(f"Error: {name} still alive after terminate")
                else:
                    print(f"{name} stopped successfully")
            else:
                print(f"{name} stopped successfully")
        except Exception as e:
            print(f"Error stopping {name}: {e}")

    print("All hardware workers stopped.")


class HardwareWorkerManager:
    """Own hardware processes and safely reload keg workers from config."""

    REQUIRED_KEG_KEYS = ('name', 'costofkeg', 'kegsizel', 'keg_id')

    def __init__(self, config_path, keg_configs, queues, tv_dict, keg_pins):
        self.config_path = config_path
        # Keep an internal active snapshot separate from the web layer's dict.
        # Web routes update their dict immediately after writing disk; retaining
        # our own snapshot lets the mtime watcher detect and apply that change.
        self.keg_configs = {str(number): dict(config)
                            for number, config in keg_configs.items()}
        self._published_configs = keg_configs
        self.queues = queues
        self.tv_dict = tv_dict
        self.keg_pins = keg_pins
        self.workers = {}
        self._config_mtime = None
        self._lock = threading.RLock()
        self._stop_watcher = threading.Event()
        self._watcher = threading.Thread(target=self._watch_config, daemon=True,
                                          name='keg-config-watcher')

    def register(self, name, worker):
        self.workers[name] = worker

    def start_watcher(self):
        self._config_mtime = os.path.getmtime(self.config_path)
        self._watcher.start()

    def _load_snapshot(self):
        parser = configparser.ConfigParser()
        if not parser.read(self.config_path):
            raise ValueError(f'Unable to read config file: {self.config_path}')
        snapshot = {}
        for number in range(1, 6):
            key = f'keg{number}'
            if not parser.has_option('Active', key):
                raise ValueError(f'Missing Active.{key}')
            keg_id = parser.get('Active', key).strip()
            if not parser.has_section(keg_id):
                raise ValueError(f'Missing keg section {keg_id}')
            values = dict(parser.items(keg_id))
            values['keg_id'] = keg_id
            for required in self.REQUIRED_KEG_KEYS:
                if not values.get(required, '').strip():
                    raise ValueError(f'Missing {required} for keg {number} ({keg_id})')
            try:
                if float(values['costofkeg']) < 0 or float(values['kegsizel']) <= 0:
                    raise ValueError('cost or size is out of range')
            except (TypeError, ValueError) as exc:
                raise ValueError(f'Invalid numeric values for keg {number}: {exc}')
            snapshot[str(number)] = values
        return snapshot

    def _new_keg_worker(self, number, keg_config):
        """Create a worker using the stable queue and GPIO assignment for a tap."""
        return read_keg_data(
            self.queues[f'keg_data{number}'], self.queues[f'keg_message{number}'],
            dict(keg_config), self.keg_pins[number], self.queues['tv_message_m2t'],
            self.queues['led_data'])

    @staticmethod
    def _stop_worker(worker):
        if worker is None:
            return
        worker.shutdown()
        worker.join(timeout=5)
        if worker.is_alive():
            worker.terminate()
            worker.join(timeout=2)

    def reload_keg(self, keg_number, keg_config=None):
        """Reload one tap; invalid config leaves the current worker untouched."""
        number = str(keg_number)
        if number not in self.keg_pins:
            raise ValueError(f'Invalid keg number: {keg_number}')
        with self._lock:
            snapshot = self._load_snapshot()
            new_config = dict(keg_config or snapshot[number])
            old_config = dict(self.keg_configs[number])
            name = f'keg_thread{number}'
            old_worker = self.workers.get(name)
            # GPIO cannot be claimed by two processes simultaneously. Stop the
            # existing worker before starting its replacement, then recreate it
            # if replacement startup fails.
            self._stop_worker(old_worker)
            replacement = self._new_keg_worker(number, new_config)
            try:
                replacement.start()
            except Exception:
                rollback = self._new_keg_worker(number, old_config)
                try:
                    rollback.start()
                except Exception:
                    logging.critical('Unable to restore keg worker %s', number,
                                     exc_info=True)
                    raise
                self.workers[name] = rollback
                raise
            self.workers[name] = replacement
            self.keg_configs[number] = dict(new_config)
            self._published_configs[number] = dict(new_config)
            logging.info('Reloaded keg worker %s (%s)', number, new_config['keg_id'])
            return new_config

    def _reload_snapshot(self, snapshot):
        """Apply a validated snapshot, restoring prior workers if one fails."""
        changed = [number for number, config in snapshot.items()
                   if config != self.keg_configs.get(number)]
        previous = {number: dict(self.keg_configs[number]) for number in changed}
        applied = []
        try:
            for number in changed:
                self.reload_keg(number, snapshot[number])
                applied.append(number)
        except Exception:
            logging.error('Reload failed; rolling back changed keg workers', exc_info=True)
            for number in reversed(applied):
                try:
                    self.reload_keg(number, previous[number])
                except Exception:
                    logging.critical('Unable to roll back keg worker %s', number,
                                     exc_info=True)
            raise

    def _watch_config(self):
        while not self._stop_watcher.wait(1.0):
            try:
                mtime = os.path.getmtime(self.config_path)
                if mtime == self._config_mtime:
                    continue
                # Validate the complete snapshot before touching any worker.
                snapshot = self._load_snapshot()
                with self._lock:
                    self._reload_snapshot(snapshot)
                self._config_mtime = mtime
            except Exception:
                logging.error('Config change was rejected; retaining active workers', exc_info=True)

    def shutdown(self):
        self._stop_watcher.set()
        if self._watcher.is_alive():
            self._watcher.join(timeout=2)
        stop_workers(list(self.workers.items()))

    def callback(self, keg_number, *args, **kwargs):
        return self.reload_keg(keg_number)


def main():
    """Main entry point for web version"""
    parser = argparse.ArgumentParser(description='Kegomatic Web UI')
    parser.add_argument("--debug", help="Debug level log output", action="store_true")
    parser.add_argument("--info", help="Info level log output", action="store_true")
    parser.add_argument("--windowed", help="Run in windowed mode (default is fullscreen)", action="store_true")
    parser.add_argument("--port", help="Flask port", type=int, default=5000)
    parser.add_argument("--no-window", help="Run Flask only, no pywebview", action="store_true")
    args = parser.parse_args()

    # Fullscreen is default, unless --windowed is specified
    args.fullscreen = not args.windowed

    # Setup logging with more detailed format
    log_format = '%(asctime)s | %(levelname)-8s | %(processName)-20s | %(funcName)-25s | %(message)s'
    if args.debug:
        logging.basicConfig(level=logging.DEBUG, format=log_format)
        print("Logging level: DEBUG (very verbose)")
    elif args.info:
        logging.basicConfig(level=logging.INFO, format=log_format)
        print("Logging level: INFO (verbose)")
    else:
        logging.basicConfig(level=logging.WARNING, format=log_format)
        print("Logging level: WARNING (errors and warnings only)")
        print("Use -v or --verbose flag with start_keg.sh for detailed logs")

    print("="*60)
    print("Kegomatic Web UI Starting...")
    print("="*60)
    print(f"Python version: {sys.version}")
    print(f"Script directory: {SCRIPT_DIR}")
    print("")

    # Load configuration
    try:
        config_path = os.path.join(SCRIPT_DIR, "config", "kegs.config")
        logging.info(f"Loading configuration from {config_path}")
        Config.read(config_path)
        print(f"✓ Loaded config from {config_path}")
        logging.info(f"✓ Configuration loaded successfully")
    except Exception as e:
        logging.error(f"✗ CRITICAL: Unable to read config file: {e}")
        logging.error("Full traceback:", exc_info=True)
        print(f"✗ Failed to load configuration: {e}")
        sys.exit(1)

    # Parse keg configurations
    try:
        logging.info("Parsing keg configurations...")
        active_keg1 = ConfigSectionMap("Active")['keg1']
        active_keg2 = ConfigSectionMap("Active")['keg2']
        active_keg3 = ConfigSectionMap("Active")['keg3']
        active_keg4 = ConfigSectionMap("Active")['keg4']
        active_keg5 = ConfigSectionMap("Active")['keg5']

        print(f"✓ Active Kegs: {active_keg1} {active_keg2} {active_keg3} {active_keg4} {active_keg5}")
        logging.info(f"Active kegs: 1={active_keg1}, 2={active_keg2}, 3={active_keg3}, 4={active_keg4}, 5={active_keg5}")

        keg_dict1 = ConfigSectionMap(active_keg1)
        keg_dict1['keg_id'] = active_keg1
        keg_dict2 = ConfigSectionMap(active_keg2)
        keg_dict2['keg_id'] = active_keg2
        keg_dict3 = ConfigSectionMap(active_keg3)
        keg_dict3['keg_id'] = active_keg3
        keg_dict4 = ConfigSectionMap(active_keg4)
        keg_dict4['keg_id'] = active_keg4
        keg_dict5 = ConfigSectionMap(active_keg5)
        keg_dict5['keg_id'] = active_keg5

        tv_dict = ConfigSectionMap("TV")
        logging.info(f"TV config: port={tv_dict.get('serialport')}, baud={tv_dict.get('baudrate')}")

    except KeyError as ke:
        logging.error(f"✗ CRITICAL: Missing required config key: {ke}")
        logging.error("Full traceback:", exc_info=True)
        print(f"✗ Config file error - missing key: {ke}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"✗ CRITICAL: Config file error: {e}")
        logging.error("Full traceback:", exc_info=True)
        print(f"✗ Config file error: {e}")
        sys.exit(1)

    # Create keg configs dictionary for API
    keg_configs = {
        '1': keg_dict1,
        '2': keg_dict2,
        '3': keg_dict3,
        '4': keg_dict4,
        '5': keg_dict5
    }

    # Setup queues and worker processes
    print("\n" + "="*60)
    print("Starting Hardware Workers...")
    print("="*60)

    # Create TV and LED queues first so they can be passed to keg workers
    tv_message_m2t = multiprocessing.Queue(maxsize=10)
    tv_message_t2m = multiprocessing.Queue(maxsize=10)
    led_data = multiprocessing.Queue(maxsize=5)

    keg_data1 = multiprocessing.Queue(maxsize=5)
    keg_message1 = multiprocessing.Queue(maxsize=10)
    keg_thread1 = read_keg_data(keg_data1, keg_message1, keg_dict1, 17, tv_message_m2t, led_data)

    keg_data2 = multiprocessing.Queue(maxsize=5)
    keg_message2 = multiprocessing.Queue(maxsize=10)
    keg_thread2 = read_keg_data(keg_data2, keg_message2, keg_dict2, 27, tv_message_m2t, led_data)

    keg_data3 = multiprocessing.Queue(maxsize=5)
    keg_message3 = multiprocessing.Queue(maxsize=10)
    keg_thread3 = read_keg_data(keg_data3, keg_message3, keg_dict3, 22, tv_message_m2t, led_data)

    keg_data4 = multiprocessing.Queue(maxsize=5)
    keg_message4 = multiprocessing.Queue(maxsize=10)
    keg_thread4 = read_keg_data(keg_data4, keg_message4, keg_dict4, 23, tv_message_m2t, led_data)

    keg_data5 = multiprocessing.Queue(maxsize=5)
    keg_message5 = multiprocessing.Queue(maxsize=10)
    keg_thread5 = read_keg_data(keg_data5, keg_message5, keg_dict5, 24, tv_message_m2t, led_data)

    tv_thread = manage_tv_power(tv_message_m2t, tv_message_t2m, tv_dict)

    pb_data = multiprocessing.Queue(maxsize=5)
    pb_thread = monitor_push_button(pb_data, 25)

    temp_sensor_data = multiprocessing.Queue(maxsize=5)
    temp_sensor_thread = monitor_temp_sensor(temp_sensor_data)

    led_thread = led_control(led_data, 18)

    # Collect all queues for Flask app
    queues = {
        'keg_data1': keg_data1,
        'keg_message1': keg_message1,
        'keg_data2': keg_data2,
        'keg_message2': keg_message2,
        'keg_data3': keg_data3,
        'keg_message3': keg_message3,
        'keg_data4': keg_data4,
        'keg_message4': keg_message4,
        'keg_data5': keg_data5,
        'keg_message5': keg_message5,
        'tv_message_m2t': tv_message_m2t,
        'tv_message_t2m': tv_message_t2m,
        'pb_data': pb_data,
        'led_data': led_data,
        'temp_sensor_data': temp_sensor_data
    }

    # Hardware manager owns workers and supports validated live keg reloads.
    manager = HardwareWorkerManager(
        config_path, keg_configs, {
            'keg_data1': keg_data1, 'keg_message1': keg_message1,
            'keg_data2': keg_data2, 'keg_message2': keg_message2,
            'keg_data3': keg_data3, 'keg_message3': keg_message3,
            'keg_data4': keg_data4, 'keg_message4': keg_message4,
            'keg_data5': keg_data5, 'keg_message5': keg_message5,
            'tv_message_m2t': tv_message_m2t, 'tv_message_t2m': tv_message_t2m,
            'pb_data': pb_data, 'led_data': led_data,
            'temp_sensor_data': temp_sensor_data
        }, tv_dict, {'1': 17, '2': 27, '3': 22, '4': 23, '5': 24})
    for name, worker in [
        ('keg_thread1', keg_thread1), ('keg_thread2', keg_thread2),
        ('keg_thread3', keg_thread3), ('keg_thread4', keg_thread4),
        ('keg_thread5', keg_thread5), ('tv_thread', tv_thread),
        ('pb_thread', pb_thread), ('led_thread', led_thread),
        ('temp_sensor_thread', temp_sensor_thread)]:
        manager.register(name, worker)
    workers = list(manager.workers.items())

    # Start all worker processes
    print("\nStarting hardware worker processes...")
    print("="*60)
    started_workers = []
    failed_workers = []

    for name, worker in workers:
        try:
            worker.start()
            print(f"✓ Started {name} (PID: {worker.pid})")
            logging.info(f"Started hardware worker: {name} (PID: {worker.pid})")
            started_workers.append(name)
        except Exception as e:
            print(f"✗ Failed to start {name}: {e}")
            logging.error(f"Failed to start hardware worker: {name}")
            logging.error(f"Exception: {e}", exc_info=True)
            failed_workers.append((name, str(e)))

    # Wait a moment for workers to initialize
    time.sleep(1)

    # Print startup summary
    print("\n" + "="*60)
    print("HARDWARE INITIALIZATION SUMMARY")
    print("="*60)
    print(f"Successfully started: {len(started_workers)}/{len(workers)} workers")
    if started_workers:
        print("\nStarted workers:")
        for name in started_workers:
            print(f"  ✓ {name}")
    if failed_workers:
        print("\nFailed workers:")
        for name, error in failed_workers:
            print(f"  ✗ {name}: {error}")
    print("\nNote: Check logs above for detailed hardware initialization status.")
    print("Some hardware failures are normal in development environments.")
    print("="*60)

    # Create Flask app
    print("\n" + "="*60)
    print("Starting Flask Server...")
    print("="*60)

    # Older web_server versions do not accept a callback; keep compatibility
    # without modifying that module.
    if 'reload_callback' in inspect.signature(create_app).parameters:
        app, socketio = create_app(queues, keg_configs, reload_callback=manager.callback)
    else:
        app, socketio = create_app(queues, keg_configs)
    manager.start_watcher()

    # Create and start DataGatherer thread
    data_gatherer = DataGatherer(socketio, queues)
    data_gatherer.start()
    print("✓ DataGatherer thread started")

    # Start Flask in background thread
    flask_thread = threading.Thread(
        target=lambda: socketio.run(app, host='0.0.0.0', port=args.port, debug=False, use_reloader=False, allow_unsafe_werkzeug=True),
        daemon=True
    )
    flask_thread.start()
    print(f"✓ Flask server starting on port {args.port}")

    # Wait for Flask to start
    time.sleep(2)

    url = f"http://localhost:{args.port}"
    print(f"\n✓ Server ready at {url}")

    # Launch pywebview window or run headless
    if args.no_window:
        print("\nRunning in headless mode (no window)")
        print("Press Ctrl+C to stop")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nKeyboard interrupt received")
    else:
        print("\n" + "="*60)
        print("Launching pywebview window...")
        print("="*60)

        try:
            import webview

            # Create window
            window_config = {
                'title': 'Kegomatic',
                'url': url,
                'fullscreen': args.fullscreen,
                'frameless': False,  # Keep frame for easy testing
                'width': 1920 if not args.fullscreen else None,
                'height': 1080 if not args.fullscreen else None
            }

            print("✓ Opening window...")
            webview.create_window(**window_config)
            webview.start()

        except ImportError as e:
            print(f"Warning: pywebview not available: {e}")
            print("Opening browser instead...")
            launch_browser_fullscreen(url, args.fullscreen)
            print("\nPress Ctrl+C to stop")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\nKeyboard interrupt received")
        except Exception as e:
            print(f"Error launching pywebview window: {e}")
            print(f"Python version: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")

            # Check if it's a Python 3.13+ compatibility issue
            if sys.version_info >= (3, 13):
                print("\nNote: pywebview may not be compatible with Python 3.13+")
                print("Consider using Python 3.9-3.12, or run with --no-window flag")

            print("\nOpening browser as fallback...")
            launch_browser_fullscreen(url, args.fullscreen)
            print("\nPress Ctrl+C to stop")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\nKeyboard interrupt received")
        except Exception as e:
            print(f"Error launching window: {e}")

    # Cleanup on exit
    print("\n" + "="*60)
    print("Shutting down...")
    print("="*60)

    data_gatherer.stop()
    manager.shutdown()

    print("✓ Shutdown complete")
    sys.exit(0)


if __name__ == '__main__':
    main()
