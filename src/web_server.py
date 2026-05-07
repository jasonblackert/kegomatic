#!/usr/bin/env python
"""
Kegomatic Web Server
Flask + SocketIO backend for real-time keg monitoring
"""
import os
import time
import threading
import logging
from flask import Flask, render_template, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
from queue import Empty

# Get script directory for paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Initialize Flask app
app = Flask(__name__,
            static_folder='static',
            template_folder='templates')
app.config['SECRET_KEY'] = 'kegomatic-secret-key-change-in-production'

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Global references to queues (set by web_main.py)
_queues = {}
_keg_configs = {}

def set_queues(queues):
    """Set queue references from main application"""
    global _queues
    _queues = queues

def set_keg_configs(configs):
    """Set keg configuration dictionaries"""
    global _keg_configs
    _keg_configs = configs


class DataGatherer(threading.Thread):
    """
    Background thread that polls hardware queues and emits WebSocket events
    Similar to gatherDataThread from main.py but emits to SocketIO
    """
    def __init__(self, socketio, queues):
        super().__init__(daemon=True)
        self.socketio = socketio
        self.queues = queues
        self.running = True
        self.counter = 0

    def run(self):
        """Main polling loop - runs every 100ms"""
        logging.info("DataGatherer thread started")
        time.sleep(2)  # Wait for workers to initialize

        while self.running:
            try:
                self.counter += 1

                # Poll all keg data queues
                for keg_num in range(1, 6):
                    keg_key = f'keg_data{keg_num}'
                    msg_key = f'keg_message{keg_num}'

                    if keg_key in self.queues:
                        try:
                            keg_data = self.queues[keg_key].get_nowait()
                            if keg_data:
                                # Emit keg update via WebSocket
                                self.socketio.emit('keg_update', {
                                    'keg_id': keg_num,
                                    'data': keg_data
                                })
                        except Empty:
                            pass

                    # Poll keg message queues
                    if msg_key in self.queues:
                        try:
                            message = self.queues[msg_key].get_nowait()
                            if message:
                                self.socketio.emit('log_message', {
                                    'message': str(message),
                                    'keg_id': keg_num
                                })
                        except Empty:
                            pass

                # Poll temperature sensor
                if 'temp_sensor_data' in self.queues:
                    try:
                        temp_data = self.queues['temp_sensor_data'].get_nowait()
                        if temp_data and 'TempF' in temp_data:
                            self.socketio.emit('temp_update', temp_data)
                    except Empty:
                        pass

                # Poll TV status
                if 'tv_message_t2m' in self.queues:
                    try:
                        tv_data = self.queues['tv_message_t2m'].get_nowait()
                        if tv_data and 'SleepTimer' in tv_data:
                            self.socketio.emit('tv_status', tv_data)
                    except Empty:
                        pass

                # Every 100 iterations (~10 seconds), emit time/date
                if self.counter % 100 == 0:
                    current_time = time.strftime("%H:%M:%S")
                    # Format date to match client-side: M/D/YYYY
                    now = time.localtime()
                    current_date = f"{now.tm_mon}/{now.tm_mday}/{now.tm_year}"
                    self.socketio.emit('time_update', {
                        'time': current_time,
                        'date': current_date
                    })

                time.sleep(0.1)  # 100ms polling interval

            except Exception as e:
                logging.error(f"Error in DataGatherer: {e}")
                time.sleep(0.1)

    def stop(self):
        """Stop the data gatherer thread"""
        self.running = False


# Flask Routes

@app.route('/')
def index():
    """Serve main HTML page"""
    return send_from_directory(os.path.join(SCRIPT_DIR, 'static'), 'index.html')

@app.route('/api/config')
def get_config():
    """Return keg configurations as JSON"""
    return jsonify({
        'kegs': _keg_configs,
        'version': '2.0-web'
    })

@app.route('/api/kegs')
def get_kegs():
    """Return current keg status (useful for initial page load)"""
    # This would need to be populated by the DataGatherer
    # For now, return basic structure
    return jsonify({
        'keg1': {},
        'keg2': {},
        'keg3': {},
        'keg4': {},
        'keg5': {}
    })

@app.route('/logos/<path:filename>')
def serve_logo(filename):
    """Serve logo images"""
    logos_path = os.path.join(SCRIPT_DIR, 'logos')
    return send_from_directory(logos_path, filename)


# SocketIO Events

@socketio.on('connect')
def handle_connect():
    """Client connected"""
    logging.info(f"Client connected")
    # Send initial config on connect
    emit('config', {
        'kegs': _keg_configs
    })

@socketio.on('disconnect')
def handle_disconnect():
    """Client disconnected"""
    logging.info(f"Client disconnected")


def create_app(queues, keg_configs):
    """Initialize and return the Flask app with SocketIO"""
    set_queues(queues)
    set_keg_configs(keg_configs)
    return app, socketio


if __name__ == '__main__':
    # For testing only
    print("Warning: Run via web_main.py instead")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
