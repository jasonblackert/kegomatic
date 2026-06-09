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
import tarfile
import tempfile
import subprocess
from datetime import datetime
from flask import Flask, render_template, jsonify, send_from_directory, request, send_file
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

        config.set(current_keg_id, 'Name', keg_data.get('name', ''))
        config.set(current_keg_id, 'Brewery', keg_data.get('brewery', ''))
        config.set(current_keg_id, 'Type', keg_data.get('type', ''))
        config.set(current_keg_id, 'ABV', str(keg_data.get('abv', '')))
        config.set(current_keg_id, 'IBU', str(keg_data.get('ibu', '')))
        config.set(current_keg_id, 'CostOfKeg', str(keg_data.get('costofkeg', 0)))
        config.set(current_keg_id, 'KegSizeL', str(keg_data.get('kegsizel', 0)))
        config.set(current_keg_id, 'PurchaseDate', keg_data.get('purchasedate', ''))
        config.set(current_keg_id, 'Logo', keg_data.get('logo', ''))

        # Write config back to file
        with open(config_path, 'w') as configfile:
            config.write(configfile)

        # Update global keg configs
        _keg_configs[str(keg_number)] = dict(config.items(current_keg_id))
        _keg_configs[str(keg_number)]['keg_id'] = current_keg_id

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


@app.route('/api/tv/settings', methods=['GET'])
def get_tv_settings():
    """Return TV settings from config"""
    try:
        config_path = os.path.join(SCRIPT_DIR, 'config', 'kegs.config')

        # Read config
        config = configparser.ConfigParser()
        config.read(config_path)

        if not config.has_section('TV'):
            return jsonify({'success': False, 'error': 'TV section not found in config'})

        tv_settings = {
            'serialport': config.get('TV', 'serialport', fallback='/dev/ttyUSB0'),
            'baudrate': config.get('TV', 'baudrate', fallback='9600'),
            'sleeptimesec': config.get('TV', 'sleeptimesec', fallback='360')
        }

        return jsonify({'success': True, 'settings': tv_settings})

    except Exception as e:
        logging.error(f"Error getting TV settings: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/tv/settings', methods=['POST'])
def save_tv_settings():
    """Save TV settings to config"""
    try:
        data = request.get_json()
        serialport = data.get('serialport')
        baudrate = data.get('baudrate')
        sleeptimesec = data.get('sleeptimesec')

        if not serialport or not baudrate or not sleeptimesec:
            return jsonify({'success': False, 'error': 'Missing required fields'})

        config_path = os.path.join(SCRIPT_DIR, 'config', 'kegs.config')

        # Read config
        config = configparser.ConfigParser()
        config.read(config_path)

        if not config.has_section('TV'):
            config.add_section('TV')

        # Update TV settings
        config.set('TV', 'serialport', str(serialport))
        config.set('TV', 'baudrate', str(baudrate))
        config.set('TV', 'sleeptimesec', str(sleeptimesec))

        # Write config back to file
        with open(config_path, 'w') as configfile:
            config.write(configfile)

        logging.info(f"TV settings updated: {serialport}, {baudrate}, {sleeptimesec}")

        # Send update message to TV thread to apply settings immediately
        if 'tv_message_m2t' in _queues:
            try:
                _queues['tv_message_m2t'].put({
                    'UpdateSettings': {
                        'sleeptimesec': sleeptimesec
                    }
                })
                logging.info("Sent TV settings update to TV thread")
            except Exception as e:
                logging.error(f"Error sending TV settings update: {e}")

        return jsonify({'success': True})

    except Exception as e:
        logging.error(f"Error saving TV settings: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/backup/export', methods=['POST'])
def export_backup():
    """Create a tar backup of user data"""
    try:
        # Create temporary tar file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        tar_filename = f"kegomatic_backup_{timestamp}.tar"
        tar_path = os.path.join(tempfile.gettempdir(), tar_filename)

        with tarfile.open(tar_path, 'w') as tar:
            # Add specific config files (not .example files)
            config_dir = os.path.join(SCRIPT_DIR, 'config')
            config_files = ['kegs.config', 'config.env']
            for config_file in config_files:
                config_file_path = os.path.join(config_dir, config_file)
                if os.path.exists(config_file_path):
                    tar.add(config_file_path, arcname=f'config/{config_file}')
                    logging.info(f"Added {config_file} to backup")

            # Add logos directory
            logos_dir = os.path.join(SCRIPT_DIR, 'logos')
            if os.path.exists(logos_dir):
                tar.add(logos_dir, arcname='logos')
                logging.info(f"Added logos directory to backup")

            # Export MySQL database to SQL file
            try:
                db_backup_path = os.path.join(tempfile.gettempdir(), 'database_backup.sql')

                # Build mysqldump command
                cmd = [
                    'mysqldump',
                    '-h', os.environ.get('DB_HOST', 'localhost'),
                    '-u', os.environ.get('DB_USER', 'kegomatic')
                ]

                # Add password if present
                db_password = os.environ.get('DB_PASSWORD', '')
                if db_password:
                    cmd.append(f'-p{db_password}')

                # Add database name
                cmd.append(os.environ.get('DB_NAME', 'keg'))

                # Run mysqldump
                with open(db_backup_path, 'w') as f:
                    result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, text=True)

                    if result.returncode != 0:
                        logging.warning(f"mysqldump returned non-zero exit code: {result.stderr}")
                    else:
                        tar.add(db_backup_path, arcname='database.sql')
                        logging.info(f"Added database backup to tar")

                # Clean up temp SQL file
                if os.path.exists(db_backup_path):
                    os.remove(db_backup_path)

            except FileNotFoundError:
                logging.warning("mysqldump not found - skipping database backup")
            except Exception as e:
                logging.warning(f"Could not backup database: {e}")

        logging.info(f"Backup created: {tar_path}")

        # Send file and clean up after
        return send_file(
            tar_path,
            mimetype='application/x-tar',
            as_attachment=True,
            download_name=tar_filename
        )

    except Exception as e:
        logging.error(f"Error creating backup: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/backup/import', methods=['POST'])
def import_backup():
    """Import a tar backup file"""
    try:
        if 'backup' not in request.files:
            return jsonify({'success': False, 'error': 'No backup file provided'})

        file = request.files['backup']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})

        if not file.filename.endswith('.tar'):
            return jsonify({'success': False, 'error': 'File must be a .tar file'})

        # Save uploaded file to temp location
        temp_tar_path = os.path.join(tempfile.gettempdir(), 'kegomatic_import.tar')
        file.save(temp_tar_path)

        # Extract tar file
        with tarfile.open(temp_tar_path, 'r') as tar:
            # Get list of members
            members = tar.getmembers()
            logging.info(f"Backup contains {len(members)} files/directories")

            # Extract config files
            config_members = [m for m in members if m.name.startswith('config/')]
            if config_members:
                for member in config_members:
                    tar.extract(member, SCRIPT_DIR)
                logging.info(f"Restored config files")

            # Extract logos directory
            logo_members = [m for m in members if m.name.startswith('logos/')]
            if logo_members:
                for member in logo_members:
                    tar.extract(member, SCRIPT_DIR)
                logging.info(f"Restored logos directory")

            # Restore database if present
            db_members = [m for m in members if m.name == 'database.sql']
            if db_members:
                try:
                    # Extract SQL file
                    tar.extract(db_members[0], tempfile.gettempdir())
                    db_sql_path = os.path.join(tempfile.gettempdir(), 'database.sql')

                    # Build mysql command
                    cmd = [
                        'mysql',
                        '-h', os.environ.get('DB_HOST', 'localhost'),
                        '-u', os.environ.get('DB_USER', 'kegomatic')
                    ]

                    # Add password if present
                    db_password = os.environ.get('DB_PASSWORD', '')
                    if db_password:
                        cmd.append(f'-p{db_password}')

                    # Add database name
                    cmd.append(os.environ.get('DB_NAME', 'keg'))

                    # Import database using mysql
                    with open(db_sql_path, 'r') as f:
                        result = subprocess.run(cmd, stdin=f, stderr=subprocess.PIPE, text=True)

                        if result.returncode != 0:
                            logging.warning(f"mysql returned non-zero exit code: {result.stderr}")
                        else:
                            logging.info(f"Restored database")

                    # Clean up temp SQL file
                    if os.path.exists(db_sql_path):
                        os.remove(db_sql_path)

                except FileNotFoundError:
                    logging.warning("mysql not found - skipping database restore")
                except Exception as e:
                    logging.warning(f"Could not restore database: {e}")

        # Clean up temp tar file
        os.remove(temp_tar_path)

        # Update global keg configs
        config_path = os.path.join(SCRIPT_DIR, 'config', 'kegs.config')
        if os.path.exists(config_path):
            from hardware import Config, ConfigSectionMap
            Config.read(config_path)

            # Reload keg configs
            for i in range(1, 6):
                try:
                    active_keg_id = ConfigSectionMap("Active")[f'keg{i}']
                    _keg_configs[str(i)] = ConfigSectionMap(active_keg_id)
                    _keg_configs[str(i)]['keg_id'] = active_keg_id
                except:
                    pass

        logging.info("Backup imported successfully")
        return jsonify({'success': True, 'message': 'Backup restored successfully'})

    except Exception as e:
        logging.error(f"Error importing backup: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/keg/<int:keg_number>/calculate-empty', methods=['GET'])
def calculate_empty_keg(keg_number):
    """Calculate what the keg size should be to make it exactly empty based on pours"""
    try:
        config_path = os.path.join(SCRIPT_DIR, 'config', 'kegs.config')

        # Read config
        config = configparser.ConfigParser()
        config.read(config_path)

        # Get current keg ID
        active_section = 'Active'
        keg_key = f'keg{keg_number}'

        if not config.has_option(active_section, keg_key):
            return jsonify({'success': False, 'error': f'Tap {keg_number} not found'})

        current_keg_id = config.get(active_section, keg_key)

        if not config.has_section(current_keg_id):
            return jsonify({'success': False, 'error': f'Keg {current_keg_id} not found'})

        # Get current keg size
        current_size_l = float(config.get(current_keg_id, 'KegSizeL', fallback=20))

        # Calculate total poured from database
        try:
            import mysql.connector
            db = mysql.connector.connect(
                host=os.environ.get('DB_HOST', 'localhost'),
                user=os.environ.get('DB_USER', 'kegomatic'),
                password=os.environ.get('DB_PASSWORD', ''),
                database=os.environ.get('DB_NAME', 'keg')
            )
            cursor = db.cursor()
            cursor.execute('SELECT * FROM pours WHERE kegid = %s', (current_keg_id,))

            poured_l = 0.0
            for row in cursor.fetchall():
                poured_l += float(row[3])  # Column 3 is pour amount in liters

            cursor.close()
            db.close()

            # New size = amount poured (so remaining = 0)
            new_size_l = poured_l

            return jsonify({
                'success': True,
                'current_size_l': current_size_l,
                'poured_l': poured_l,
                'new_size_l': new_size_l,
                'keg_id': current_keg_id
            })

        except Exception as db_error:
            logging.error(f"Database error calculating pours: {db_error}")
            return jsonify({'success': False, 'error': f'Database error: {str(db_error)}'})

    except Exception as e:
        logging.error(f"Error calculating empty keg: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/tv/activity', methods=['POST'])
def tv_activity():
    """Handle user activity to reset TV timer and turn on TV"""
    try:
        # Send PowerOn message to TV thread via queue
        if 'tv_message_m2t' in _queues:
            try:
                _queues['tv_message_m2t'].put({'PowerOn': True})
                logging.debug("User activity detected - sent PowerOn to TV thread")
                return jsonify({'success': True})
            except Exception as e:
                logging.error(f"Error sending PowerOn to TV thread: {e}")
                return jsonify({'success': False, 'error': str(e)})
        else:
            logging.warning("tv_message_m2t queue not available")
            return jsonify({'success': False, 'error': 'TV queue not available'})

    except Exception as e:
        logging.error(f"Error handling TV activity: {e}")
        return jsonify({'success': False, 'error': str(e)})


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
