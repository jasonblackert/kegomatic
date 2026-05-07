#!/usr/bin/env python
"""
Kegomatic Hardware Workers
Hardware interface classes - no GUI dependencies
"""
import multiprocessing
from queue import Full, Empty
import sys
import time
import serial
import re
import logging
import math
import os
import subprocess
import mysql.connector 
import glob
import configparser
from gpiozero import Button, PWMLED
from signal import pause

# Add script directory to path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# Import flowmeter
from flowmeter import FlowMeter

# Config parser
Config = configparser.ConfigParser()

# Load database credentials from config.env
_env_path = os.path.join(SCRIPT_DIR, 'config', 'config.env')
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _v = _line.split('=', 1)
                os.environ.setdefault(_k.strip(), _v.strip())

def ConfigSectionMap(section):
    """Parse config section into dict"""
    dict1 = {}
    options = Config.options(section)
    for option in options:
        try:
            dict1[option] = Config.get(section, option)
            if dict1[option] == -1:
                logging.debug("Skip: %s" % option)
        except:
            logging.error("exception on %s" % option)
            dict1[option] = None
    return dict1

class read_keg_data(multiprocessing.Process):

    def __init__(self, keg_data_q, keg_message_q, keg_dict, gpio_pin, click_q=None):
        multiprocessing.Process.__init__(self)
        self.exit = multiprocessing.Event()
        self.keg_data_q = keg_data_q
        self.keg_message_q = keg_message_q
        self.keg_dict = keg_dict
        self.gpio_pin = int(gpio_pin)
        self.click_q = click_q
        self.fm = FlowMeter('metric', ["keg 1 beer"])
        print("Starting on gpio " + str(gpio_pin))

    def doAClick(self, channel):
        print("I'm buttoning!")
        currentTime=int(time.time() * FlowMeter.MS_IN_A_SECOND)
        if self.fm.enabled == True:
            self.fm.update(currentTime)

    def doAMeow(self, channel):
        print("I'm buttoning!")

    def write_db_pour(self, keg_id, pour_amt):
        self.keg_id = keg_id
        self.pour_amt = pour_amt
        #Trying to zero some shit
        if keg_id == 'AC':
            print(self.pour_amt)
            print('See ya')
            self.pour_amt += 20
            print(self.pour_amt)
        try:
            db = mysql.connector.connect(host=os.environ['DB_HOST'], user=os.environ['DB_USER'], password=os.environ['DB_PASSWORD'], database=os.environ['DB_NAME'])
            curs = db.cursor()
            curs.execute (''' INSERT INTO pours values (CURRENT_DATE(), CURRENT_TIME(), %s, %s) ''', (keg_id, pour_amt))
            db.commit()
        except Exception as ue:
            logging.error(f"Unable to write to the database! {ue}")
        db.close()

    def read_db_tally(self, keg_id):
        self.keg_id = keg_id
        try:
            db = mysql.connector.connect(host=os.environ['DB_HOST'], user=os.environ['DB_USER'], password=os.environ['DB_PASSWORD'], database=os.environ['DB_NAME'])
            curs = db.cursor()
            curs.execute (''' SELECT * FROM pours WHERE kegid = %s ''', (keg_id, ))
            tally = 0.0
            for reading in curs.fetchall():
                tally = tally + float(reading[3])
            return tally
        except Exception as ue:
            logging.error(f"Unable to read the database! {ue}")
            return 0.0
        db.close()

    def run(self):
        oz_per_l = 0.02957352956
        logging.info("Starting read_keg_data thread...")
        msg = time.strftime("%m-%d-%Y - %H:%M:%S") + ": Starting thread for FlowMeter on " + self.keg_dict['keg_id']
        try:
            self.keg_message_q.put(str(msg))
        except Full:
            logging.warning("Queue is full when writing keg message")

        button = Button(self.gpio_pin, pull_up=False, bounce_time=0.020)
        button.when_pressed = self.doAClick
        keg_data_dict = dict()
        keg_message = ""
        empty_keg = False
        tally = self.read_db_tally(self.keg_dict['keg_id'])
        cost_per_l = float(self.keg_dict['costofkeg']) / float(self.keg_dict['kegsizel'])

        #Calculate % left to start
        percent_left = int((((float(self.keg_dict['kegsizel']) - tally) + 0.001) / float(self.keg_dict['kegsizel']) ) * 100 )
        if (percent_left < 0 or self.keg_id=='AC'):
            #print(self.keg_id)
            #print(percent_left)
            precent_left = int(0)
            empty_keg = True

        #Set status to empty on startup
        if empty_keg:
            keg_data_dict['PourStatus'] = "Keg Empty"
        else:
            keg_data_dict['PourStatus'] = "Ready"
        while not self.exit.is_set():
            currentTime = int(time.time() * FlowMeter.MS_IN_A_SECOND)
            # The Pour has stopped but may not be over
            if (self.fm.thisPour > 0.01 and currentTime - self.fm.lastClick > 500):
                self.fm.flow = 0.0 
                keg_data_dict['PourStatus'] = "Pour Wait"

            # After 4 seconds of nothing happening, the pour is over
            if (self.fm.thisPour > 0.01 and currentTime - self.fm.lastClick > 4000):
                pour_cost = str(float("{0:.2f}".format(float(keg_data_dict['PourCost']))))
                if not re.search(r'\d+\.\d\d', pour_cost):
                    pour_cost = str(pour_cost) + "0"
                msg = time.strftime("%m-%d-%Y - %H:%M:%S") + ": Someone just poured " + str(round(float(self.fm.getThisPour() / oz_per_l), 2)) + " oz. of " + self.keg_dict['name'] + " from the kegomatic! The cost was $" + str(pour_cost)
                print(msg)
                self.write_db_pour(self.keg_dict['keg_id'], self.fm.getThisPour())
                self.fm.thisPour = 0.0
                tally = self.read_db_tally(self.keg_dict['keg_id'])
                try:
                    self.keg_message_q.put(str(msg))
                except Full:
                    logging.warning("Queue is full when writing keg message")

                percent_left = int((((float(self.keg_dict['kegsizel']) - tally) + 0.001) / float(self.keg_dict['kegsizel']) ) * 100 )
                
                if (percent_left < 0 or self.keg_id=='AC'):
                    #print(self.keg_id)
                    #print(percent_left)
                    precent_left = int(0)
                    empty_keg = True

                if empty_keg:
                    keg_data_dict['PourStatus'] = "Keg Empty"
                else:
                    keg_data_dict['PourStatus'] = "Ready"

            # The Pour is active
            if (self.fm.flow > 0.0):
                keg_data_dict['PourStatus'] = "Pour Active"

            percent_left = int((((float(self.keg_dict['kegsizel']) - tally) + 0.001) / float(self.keg_dict['kegsizel']) ) * 100 )
            
            if (percent_left < 0 or self.keg_id=='AC'):
                #print(self.keg_id)
                #print(percent_left)
                precent_left = int(0)
                empty_keg = True
            
            #print('Percent Left: ')
            #print(percent_left)
            keg_data_dict['KegFillPercent'] = int(percent_left)
            keg_data_dict['BeerRemainingL'] = round(float(self.keg_dict['kegsizel']) - tally, 2)
            keg_data_dict['BeerRemainingOz'] = round((float(self.keg_dict['kegsizel']) - tally) / oz_per_l, 2)
            keg_data_dict['PourAmtL'] = round(self.fm.getThisPour(), 2)
            keg_data_dict['PourAmtOz'] = round(float(self.fm.getThisPour()) / oz_per_l, 2)
            # Add 25% to price of the pour
            keg_data_dict['PourCost'] = round((cost_per_l * self.fm.getThisPour())*1.25, 2)
            keg_data_dict['InstFlowRateLS'] = round(self.fm.getFlow(), 2)
            keg_data_dict['InstFlowRateOzS'] = round(self.fm.getFlow() / oz_per_l, 2)
            try:
                self.keg_data_q.put(keg_data_dict)
            except Full:
                logging.warning("Queue is full when writing keg data")
            #print "tick"
            time.sleep(.03)
        pause() # gpiozero pair
        print("Keg Thread exit.")

    def shutdown(self):
        print("Shutdown started...")
        self.exit.set()


class monitor_temp_sensor(multiprocessing.Process):

    def __init__(self, temp_sensor_message_q):
        multiprocessing.Process.__init__(self)
        self.exit = multiprocessing.Event()
        self.temp_sensor_message_q = temp_sensor_message_q
        print("Temp Sensor thread starting...")

    def run(self):
        base_dir = '/sys/bus/w1/devices/'
        matches = glob.glob(base_dir + '28*')
        if not matches:
            logging.warning("NO 1-wire temp sensors found under %s", base_dir)
            return
        device_folder = matches[0]
        #device_folder = glob.glob(base_dir + '28*')[0]
        device_file = device_folder + '/w1_slave'
        temp_sensor_dict = dict()

        while not self.exit.is_set():
            catdata = subprocess.Popen(['cat',device_file], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out,err = catdata.communicate()
            out_decode = out.decode('utf-8')
            lines = out_decode.split('\n')
            while lines[0].strip()[-3:] != 'YES':
                time.sleep(0.2)
                lines = read_temp_raw()
            equals_pos = lines[1].find('t=')
            if equals_pos != -1:
                temp_string = lines[1][equals_pos+2:]
                temp_c = float(temp_string) / 1000.0
                temp_f = temp_c * 9.0 / 5.0 + 32.0

                temp_sensor_dict['TempF'] = float(temp_f)
                temp_sensor_dict['TempC'] = float(temp_c)
                try:
                    self.temp_sensor_message_q.put(temp_sensor_dict)
                except Full:
                    logging.warning("Queue is full when writing to the temp_sensor_message queue.")
                time.sleep(.5)
        print("Temp Sensor Thread exit.")

    def shutdown(self):
        print("Shutdown started...")
        self.exit.set()

class monitor_push_button(multiprocessing.Process):

    def __init__(self, pb_message_q, gpio_pin):
        multiprocessing.Process.__init__(self)
        self.exit = multiprocessing.Event()
        self.pb_message_q = pb_message_q
        self.gpio_pin = int(gpio_pin)
        print("Button thread starting on gpio " + str(gpio_pin))

    def run(self):
        logging.info("Starting monitor_push_button thread...")
        pb_dict = dict()
        button = Button(self.gpio_pin)
        try:
            while not self.exit.is_set():
                if button.is_pressed:
                    print('Button Pressed')
                    pb_dict['ButtonPressed'] = True
                    try:
                        self.pb_message_q.put(pb_dict)
                    except Full:
                        logging.warning("Queue is full when writing to the pb_message queue.")
                    time.sleep(.2)
                else:
                    time.sleep(.1)
        except KeyboardInterrupt as ke:
            logging.warning(f"Keyboard Interrupt received: {ke}")
        finally:
            button.close()

        print("monitor_push_button exit.")

    def shutdown(self):
        print("Shutdown started...")
        self.exit.set()

class led_control(multiprocessing.Process):

    def __init__(self, led_message_q, gpio_pin):
        multiprocessing.Process.__init__(self)
        self.exit = multiprocessing.Event()
        self.led_message_q = led_message_q
        self.gpio_pin = int(gpio_pin)
        print("LED Control thread starting on gpio " + str(gpio_pin))

    def run(self):
        logging.info("Starting led_control thread...")

        # Try to initialize PWM LED, catch and log errors gracefully
        try:
            pwm = PWMLED(self.gpio_pin)
            logging.info(f"✓ LED control initialized on GPIO {self.gpio_pin}")
        except Exception as e:
            logging.error(f"✗ Failed to initialize LED PWM on GPIO {self.gpio_pin}: {e}")
            logging.warning("LED control will be disabled (this is normal if not running on Raspberry Pi)")
            # Keep thread alive but do nothing
            while not self.exit.is_set():
                time.sleep(1)
            return

        duty_cycle = 50
        pwm.value = duty_cycle / 100 # Value translated to between 0.0 and 1.0
        sleep_state = True
        dc_delta = 1
        counter = 0.1
        off_time_msec = 1000
        on_time_msec = 1000
        led_state = True
        currentTime = int(1000*time.time())
        led_state_change = currentTime

        try:
            while not self.exit.is_set():
                try:
                    m2t_dict = self.led_message_q.get_nowait()
                    logging.debug("LED Message from master to thread: %s", str(m2t_dict))

                except Empty:
                    logging.info("Empty Q when getting data from the led_message_q queue")
                    m2t_dict = dict()

                if "PowerActive" in m2t_dict:
                    # PowerActive is boolean True or False
                    if m2t_dict['PowerActive']:
                        sleep_state = False
                    else:
                        sleep_state = True

                if sleep_state:
                    duty_cycle = 100*((0.5*(math.sin(counter))) + 0.5)
                    pwm.value = duty_cycle / 100 # Value translated to between 0.0 and 1.0
                    counter = counter + 0.1
                    if counter == 1000000:
                        counter = 0.1

                else:
                    currentTime = int(1000*time.time())
                    # LED to full on

                    if ( ((currentTime - led_state_change) > on_time_msec) and led_state ):
                        led_state = False
                        led_state_change = currentTime
                        pwm.value = 50 / 100
                    if ( ((currentTime - led_state_change) > off_time_msec) and not led_state ):
                        led_state = True
                        led_state_change = currentTime
                        pwm.value = 100 / 100

                # this sleep will mess with the PWM in sleep!
                time.sleep(0.05)

        except KeyboardInterrupt as ke:
            logging.warning(f"Keyboard Interrupt received: {ke}")

        pause() # paired with gpiozero
        print("led_control exit.")

    def shutdown(self):
        print("Shutdown started...")
        self.exit.set()

class manage_tv_power(multiprocessing.Process):

    def __init__(self, tv_message_q_m2t, tv_message_q_t2m, tv_dict):
        multiprocessing.Process.__init__(self)
        self.exit = multiprocessing.Event()
        self.tv_message_q_m2t = tv_message_q_m2t
        self.tv_message_q_t2m = tv_message_q_t2m
        self.tv_dict = tv_dict

    def run(self):
        logging.info("Starting manage_tv_power thread...")
        tv_power_on = False

        #Setup Serial Port
        serial_port_name = self.tv_dict['serialport']
        baud = self.tv_dict['baudrate']
        databits = 8
        par      = serial.PARITY_NONE  # parity
        sb       = 1                   # stop bits
        to       = 0
        logging.info(f"Opening serial port: {serial_port_name} at {baud} baud")
        try:
            ser = serial.Serial(serial_port_name, baud, parity = par, stopbits = sb, bytesize = databits,timeout = to)
            time.sleep(0.2)
            c = ser.read(100)
            ser.flushOutput()
            ser.flushInput()
            logging.info(f"✓ Serial port {serial_port_name} opened successfully")
        except serial.SerialException as e:
            logging.error(f"✗ Unable to open serial port {serial_port_name}: {e}")
            logging.warning("TV power control will be disabled (this is normal if TV is not connected)")
            ser = None
            # Keep thread alive but do nothing
            while not self.exit.is_set():
                time.sleep(1)
            return
        except Exception as e:
            logging.error(f"✗ Unexpected error opening serial port: {e}")
            ser = None
            while not self.exit.is_set():
                time.sleep(1)
            return

        if ser is not None:
            _send_tv_cmd(ser, "RSPW1    ", 5, 50000)
        else:
            logging.warning("TV power control disabled: serial port not available")

        # Configure the TV to power on via RS-232C
        if not _send_tv_cmd(ser, "RSPW1   ", 5, 50000):
            logging.error("Couldn't configure the TV to power on via RS-232C, continuning anyway.")

        time.sleep(.2)
        tv_power_on_time = int(time.time())
        if not _send_tv_cmd(ser, "POWR1   ", 5, 50000):
            logging.error("Couldn't turn the TV on.")
            tv_power_on = False
        else:
            time.sleep(.2)
            if not _send_tv_cmd(ser, "IAVD3   ", 5, 50000):
                logging.error("Couldn't configure the TV to HDMI Input 3 via RS-232C, continuning anyway.")
            tv_power_on = True

        m2t_dict = dict()
        t2m_dict = dict()
        def_retry_cmd = 5
        def_retry_count = 50000
        while not self.exit.is_set():
            currentTime = int(time.time())
            try:
                m2t_dict = self.tv_message_q_m2t.get_nowait()
                logging.debug("TV Message from master to thread: %s", str(m2t_dict))

            except Empty:
                logging.info("Empty Q when getting data from the tv_message_m2t queue")
                m2t_dict = dict()

            # Power on from someone pouring beer
            if "PowerOn" in m2t_dict:
                if not tv_power_on:
                    if not _send_tv_cmd(ser, "POWR1   ", def_retry_cmd, def_retry_count):
                        logging.error("Couldn't turn the TV on.")
                        tv_power_on = False
                    else:
                        tv_power_on = True
                        tv_power_on_time = int(time.time())
                else:
                    tv_power_on_time = int(time.time())


            #Calculate how long the TV has been on, turn it off if it's been long: enough
            if ( ((currentTime - tv_power_on_time) > int(self.tv_dict['sleeptimesec'])) and tv_power_on ):
                # Turn the TV off
                if not _send_tv_cmd(ser, "POWR0   ", def_retry_cmd, def_retry_count):
                    logging.error("Couldn't turn the TV off.")
                    tv_power_on = True
                else:
                    tv_power_on = False

            # Display the sleep timer
            count_down_timer = int(self.tv_dict['sleeptimesec']) - ( currentTime - tv_power_on_time )
            if (count_down_timer >= 0):
                t2m_dict['SleepTimer'] = count_down_timer
            else:
                t2m_dict['SleepTimer'] = 0

            try:
                self.tv_message_q_t2m.put(t2m_dict)
            except Full:
                logging.warning("Queue is full when writing to the tv_message_t2m queue.")

            time.sleep(.1)
        ser.close()
        print("TV Thread Exit.")

    def shutdown(self):
        print("Shutdown started...")
        self.exit.set()

def _send_tv_cmd(ser, cmd, cmd_retry_count, ser_read_retry_count):
    """Send a command to the TV via serial and wait for response"""
    if ser is None:
        logging.warning("Serial port is None, skipping TV command: %s", cmd)
        return False

    try:
        logging.info("Sending TV Command: ->%s<-", str(cmd))
        i = int(cmd_retry_count)
        while (i > 0):
            logging.debug("Sending TV Command: ->%s<-", str(cmd))
            _send_serial(ser, str(cmd))
            logging.debug("Waiting for a response from the TV... %s", str(cmd))
            time.sleep(.1)
            res = _read_serial(ser, int(ser_read_retry_count))
            logging.info("TV Returned ->%s<-", str(res))
            if (res == "OK"):
                logging.info("The TV has accepted the command")
                return True
            elif (res == "ERR"):
                logging.error("The TV has rejected the command")
            else:
                logging.error("The TV is not responding to serial commands. Will retry %s more time(s)", str(i))

            time.sleep(.1)
            i = i - 1
        logging.error("Unable to command the TV, it is not responding")
        return False

    except Exception as e:
        logging.error(f"Exception while sending TV command '{cmd}': {e}")
        return False

###############################################################################
# Serial Interface
###############################################################################

def _send_serial(ser, cmd_string):
    """Send a string command to serial port, encoding to bytes"""
    if ser is None:
        logging.warning("Serial port is None, skipping send")
        return

    try:
        ser.flushOutput()
        ser.flushInput()

        # Encode string to bytes for serial transmission
        for c in cmd_string:
            ser.write(c.encode('ascii'))
        ser.write(b"\r")

        logging.debug(f"Sent serial command: {cmd_string}")
    except Exception as e:
        logging.error(f"Error sending serial command '{cmd_string}': {e}")

def _read_serial(ser, retry_count):
    """Read response from serial port, decoding bytes to string"""
    if ser is None:
        logging.error("Serial port is None, cannot read")
        return None

    try:
        repeat_count = 0
        cmd_ok = False
        buffer = ""

        while True:
            c = ser.read(1)
            if len(c) == 0:
                if repeat_count == retry_count:
                    break
                repeat_count = repeat_count + 1
                continue

            # Decode bytes to string
            c = c.decode('ascii', errors='ignore')

            if c == '\r':
                cmd_ok = True
                break

            if buffer != "" or c != ">":  # if something is in buffer, add everything
                buffer = buffer + c

        if buffer == "":
            logging.warning("No data received from read command after %s retries", retry_count)
            return None

        logging.debug("Retry count %s, received: %s", repeat_count, buffer)
        return buffer

    except Exception as e:
        logging.error(f"Error reading from serial port: {e}")
        return None


def is_empty(any_structure):
    if any_structure:
        return False
    else:
        return True

def ConfigSectionMap(section):
    dict1 = {}
    options = Config.options(section)
    for option in options:
        try:
            dict1[option] = Config.get(section, option)
            if dict1[option] == -1:
                logging.debug("Skip: %s" % option)
        except:
            logging.error("exception on %s" % option)
            dict1[option] = None
    return dict1
