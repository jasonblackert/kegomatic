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

    # If fullscreen not requested, use default browser
    if not fullscreen:
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

    chrome_cmd = None
    for path in chrome_paths:
        if path and os.path.exists(path):
            chrome_cmd = path
            break

    if chrome_cmd:
        try:
            subprocess.Popen([
                chrome_cmd,
                '--kiosk',
                '--start-fullscreen',
                '--disable-infobars',
                '--noerrdialogs',
                '--disable-session-crashed-bubble',
                url
            ])
            print(f"✓ Launched browser in fullscreen mode: {chrome_cmd}")
            return
        except Exception as e:
            print(f"Warning: Could not launch Chrome in fullscreen: {e}")

    # Fallback to default browser
    print("Chrome not found, using default browser (press F11 for fullscreen)")
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


def main():
    """Main entry point for web version"""
    parser = argparse.ArgumentParser(description='Kegomatic Web UI')
    parser.add_argument("--debug", help="Debug level log output", action="store_true")
    parser.add_argument("--info", help="Info level log output", action="store_true")
    parser.add_argument("--fullscreen", help="Fullscreen window", action="store_true")
    parser.add_argument("--port", help="Flask port", type=int, default=5000)
    parser.add_argument("--no-window", help="Run Flask only, no pywebview", action="store_true")
    args = parser.parse_args()

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

    # Collect workers for cleanup
    workers = [
        ('keg_thread1', keg_thread1),
        ('keg_thread2', keg_thread2),
        ('keg_thread3', keg_thread3),
        ('keg_thread4', keg_thread4),
        ('keg_thread5', keg_thread5),
        ('tv_thread', tv_thread),
        ('pb_thread', pb_thread),
        ('led_thread', led_thread),
        ('temp_sensor_thread', temp_sensor_thread)
    ]

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

    app, socketio = create_app(queues, keg_configs)

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
    stop_workers(workers)

    print("✓ Shutdown complete")
    sys.exit(0)


if __name__ == '__main__':
    main()
