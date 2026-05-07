#!/usr/bin/env python
"""
Kegomatic Web Server
Flask + SocketIO backend for real-time keg monitoring
"""
import os
import time
import threading
import logging
import configparser
from flask import Flask, render_template, jsonify, send_from_directory, request
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

@app.route('/api/logos')
def get_logos():
    """Return list of available logo files"""
    logos_path = os.path.join(SCRIPT_DIR, 'logos')
    try:
        if os.path.exists(logos_path):
            logos = [f for f in os.listdir(logos_path) if f.endswith(('.png', '.jpg', '.jpeg', '.gif'))]
            return jsonify({'logos': sorted(logos)})
        else:
            return jsonify({'logos': []})
    except Exception as e:
        logging.error(f"Error listing logos: {e}")
        return jsonify({'logos': [], 'error': str(e)})

@app.route('/api/keg/edit', methods=['POST'])
def edit_keg():
    """Edit existing keg configuration"""
    try:
        data = request.get_json()
        keg_number = data.get('keg_number')
        keg_data = data.get('keg_data')

        if not keg_number or not keg_data:
            return jsonify({'success': False, 'error': 'Missing keg_number or keg_data'})

        config_path = os.path.join(SCRIPT_DIR, 'config', 'kegs.config')

        # Read config
        config = configparser.ConfigParser()
        config.read(config_path)

        # Get current keg ID for this tap
        active_section = 'Active'
        keg_key = f'keg{keg_number}'

        if not config.has_option(active_section, keg_key):
            return jsonify({'success': False, 'error': f'Tap {keg_number} not found in config'})

        current_keg_id = config.get(active_section, keg_key)

        # Update the existing keg section
        if not config.has_section(current_keg_id):
            return jsonify({'success': False, 'error': f'Keg section {current_keg_id} not found'})

        # Get old keg size to check if it changed
        old_keg_size = float(config.get(current_keg_id, 'KegSizeL', fallback=20))
        new_keg_size = float(keg_data.get('kegsizel', 20))

        config.set(current_keg_id, 'Name', keg_data.get('name', ''))
        config.set(current_keg_id, 'Brewery', keg_data.get('brewery', ''))
        config.set(current_keg_id, 'Type', keg_data.get('type', ''))
        config.set(current_keg_id, 'ABV', str(keg_data.get('abv', '')))
        config.set(current_keg_id, 'IBU', str(keg_data.get('ibu', '')))
        config.set(current_keg_id, 'CostOfKeg', str(keg_data.get('costofkeg', 0)))
        config.set(current_keg_id, 'KegSizeL', str(new_keg_size))
        config.set(current_keg_id, 'PurchaseDate', keg_data.get('purchasedate', ''))
        config.set(current_keg_id, 'Logo', keg_data.get('logo', ''))

        # Write config back to file
        with open(config_path, 'w') as configfile:
            config.write(configfile)

        # Update global keg configs
        _keg_configs[str(keg_number)] = dict(config.items(current_keg_id))
        _keg_configs[str(keg_number)]['keg_id'] = current_keg_id

        # If keg size changed, recalculate beer remaining and fill percentage
        recalculated_data = None
        if old_keg_size != new_keg_size:
            # Get current beer remaining from the keg data queue (last known state)
            # We'll need to calculate: pouredOz = (oldMax - oldRemaining)
            # then: newRemaining = newMax - pouredOz

            # Constants
            OZ_PER_LITER = 33.814

            old_max_oz = old_keg_size * OZ_PER_LITER
            new_max_oz = new_keg_size * OZ_PER_LITER

            # Try to get current beer remaining from queue or use max as fallback
            # For now, we'll send a message to the hardware thread to do the recalculation
            # since it has the authoritative state

            message = {
                'type': 'recalculate_size',
                'old_size_l': old_keg_size,
                'new_size_l': new_keg_size,
                'old_max_oz': old_max_oz,
                'new_max_oz': new_max_oz
            }

            if f'keg_message{keg_number}' in _queues:
                try:
                    _queues[f'keg_message{keg_number}'].put(message)
                    logging.info(f"Keg {keg_number} size changed: {old_keg_size}L -> {new_keg_size}L. Recalculating beer remaining.")
                except Exception as e:
                    logging.error(f"Error sending keg size change message: {e}")

        logging.info(f"Edited keg {keg_number} (ID: {current_keg_id})")

        return jsonify({'success': True, 'keg_id': current_keg_id})

    except Exception as e:
        logging.error(f"Error editing keg: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/keg/replace', methods=['POST'])
def replace_keg():
    """Replace keg with new configuration (creates new keg ID)"""
    try:
        data = request.get_json()
        keg_number = data.get('keg_number')
        keg_data = data.get('keg_data')

        if not keg_number or not keg_data:
            return jsonify({'success': False, 'error': 'Missing keg_number or keg_data'})

        config_path = os.path.join(SCRIPT_DIR, 'config', 'kegs.config')

        # Read config
        config = configparser.ConfigParser()
        config.read(config_path)

        # Get current keg ID for this tap
        active_section = 'Active'
        keg_key = f'keg{keg_number}'

        if not config.has_option(active_section, keg_key):
            return jsonify({'success': False, 'error': f'Tap {keg_number} not found in config'})

        current_keg_id = config.get(active_section, keg_key)

        # Generate new keg ID (increment last letter)
        new_keg_id = generate_next_keg_id(current_keg_id, config)

        # Create new keg section
        config.add_section(new_keg_id)
        config.set(new_keg_id, 'Name', keg_data.get('name', ''))
        config.set(new_keg_id, 'Brewery', keg_data.get('brewery', ''))
        config.set(new_keg_id, 'Type', keg_data.get('type', ''))
        config.set(new_keg_id, 'ABV', str(keg_data.get('abv', '')))
        config.set(new_keg_id, 'IBU', str(keg_data.get('ibu', '')))
        config.set(new_keg_id, 'CostOfKeg', str(keg_data.get('costofkeg', 0)))
        config.set(new_keg_id, 'KegSizeL', str(keg_data.get('kegsizel', 0)))
        config.set(new_keg_id, 'PurchaseDate', keg_data.get('purchasedate', ''))
        config.set(new_keg_id, 'Logo', keg_data.get('logo', ''))

        # Update Active section
        config.set(active_section, keg_key, new_keg_id)

        # Write config back to file
        with open(config_path, 'w') as configfile:
            config.write(configfile)

        # Update global keg configs
        _keg_configs[str(keg_number)] = dict(config.items(new_keg_id))
        _keg_configs[str(keg_number)]['keg_id'] = new_keg_id

        logging.info(f"Replaced keg {keg_number}: {current_keg_id} -> {new_keg_id}")

        return jsonify({'success': True, 'old_keg_id': current_keg_id, 'new_keg_id': new_keg_id})

    except Exception as e:
        logging.error(f"Error replacing keg: {e}")
        return jsonify({'success': False, 'error': str(e)})

def generate_next_keg_id(current_id, config):
    """Generate next keg ID by incrementing letters"""
    if len(current_id) == 2:
        first, second = current_id[0], current_id[1]

        # Try incrementing second letter first
        if second != 'Z':
            next_second = chr(ord(second) + 1)
            new_id = first + next_second
        else:
            # Second is Z, increment first and reset second to A
            if first != 'Z':
                next_first = chr(ord(first) + 1)
                new_id = next_first + 'A'
            else:
                # Both are Z, wrap to AA (or use AAA for 3 letters)
                new_id = 'AA'

        # Check if ID already exists, if so keep incrementing
        while config.has_section(new_id):
            if len(new_id) == 2:
                first, second = new_id[0], new_id[1]
                if second != 'Z':
                    new_id = first + chr(ord(second) + 1)
                elif first != 'Z':
                    new_id = chr(ord(first) + 1) + 'A'
                else:
                    new_id = 'AAA'  # Extend to 3 letters
            else:
                # If we ever get 3+ letters, just increment last
                new_id = new_id[:-1] + chr(ord(new_id[-1]) + 1)

        return new_id

    # Fallback for unexpected format
    return 'ZZ'


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
