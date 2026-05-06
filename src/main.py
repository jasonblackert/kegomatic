#!/usr//bin/python
#####################################################
# File: main.py
# Author: Allen Nichols
# Desc: Kegomatic
# Date: 05/06/18
# Current Rev Date: 05/27/18
#####################################################
from PyQt6 import QtGui, QtCore
from PyQt6.QtCore import QThread, pyqtSignal, QObject
from PyQt6.QtWidgets import QApplication, QWidget, QPlainTextEdit, QFrame, QLabel, QLCDNumber, QProgressBar, QGridLayout
import multiprocessing
from queue import Full,Empty

logo_image = 'logos/Jason_Blackert_Venmo.png'

import sys
import numpy as np
import time
import serial
import re
import logging
import signal
import math
import os
import subprocess
from subprocess import CalledProcessError, check_output
import multiprocessing as mp
import mysql.connector 
import glob
import argparse
import configparser
Config = configparser.ConfigParser()

# Load database credentials from config.env
_env_path = os.path.join(os.path.dirname(__file__), 'config', 'config.env')
with open(_env_path) as _f:
    for _line in _f:
        _line = _line.strip()
        if _line and not _line.startswith('#') and '=' in _line:
            _k, _v = _line.split('=', 1)
            os.environ.setdefault(_k.strip(), _v.strip())

from flowmeter import *

event_q = mp.Queue()

from gpiozero import Button, PWMLED
from signal import pause

import multiprocessing as mp
import threading
from queue import Full, Empty  # you already have this

"""
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                    stream=sys.stdout,
                    )
"""

class gatherDataThread(QThread):
    update_lcdBeerRemaining1 = pyqtSignal(str)
    update_lcdBeerRemaining2 = pyqtSignal(str)
    update_lcdBeerRemaining3 = pyqtSignal(str)
    update_lcdBeerRemaining4 = pyqtSignal(str)
    update_lcdBeerRemaining5 = pyqtSignal(str)
    update_lcdPourAmt1 = pyqtSignal(str)
    update_lcdPourAmt2 = pyqtSignal(str)
    update_lcdPourAmt3 = pyqtSignal(str)
    update_lcdPourAmt4 = pyqtSignal(str)
    update_lcdPourAmt5 = pyqtSignal(str)
    update_lcdPourCost1 = pyqtSignal(str)
    update_lcdPourCost2 = pyqtSignal(str)
    update_lcdPourCost3 = pyqtSignal(str)
    update_lcdPourCost4 = pyqtSignal(str)
    update_lcdPourCost5 = pyqtSignal(str)
    update_lcdInstFlowRate1 = pyqtSignal(str)
    update_lcdInstFlowRate2 = pyqtSignal(str)
    update_lcdInstFlowRate3 = pyqtSignal(str)
    update_lcdInstFlowRate4 = pyqtSignal(str)
    update_lcdInstFlowRate5 = pyqtSignal(str)
    update_lcdCPUTemp = pyqtSignal(str)
    update_lcdTempSensor = pyqtSignal(str)
    update_lcdTVSleep = pyqtSignal(str)
    update_lcdTimeOfDay = pyqtSignal(str)
    update_lcdDate = pyqtSignal(str)
    update_lblPourStatusNow1 = pyqtSignal(str)
    update_lblPourStatusNow2 = pyqtSignal(str)
    update_lblPourStatusNow3 = pyqtSignal(str)
    update_lblPourStatusNow4 = pyqtSignal(str)
    update_lblPourStatusNow5 = pyqtSignal(str)
    update_pbarBeerRemaining1 = pyqtSignal(str)
    update_pbarBeerRemaining2 = pyqtSignal(str)
    update_pbarBeerRemaining3 = pyqtSignal(str)
    update_pbarBeerRemaining4 = pyqtSignal(str)
    update_pbarBeerRemaining5 = pyqtSignal(str)
    update_textboxLogMessage = pyqtSignal(str)

    def __init__(self, keg_data1, keg_message1, keg_data2, keg_message2, keg_data3, keg_message3, keg_data4, keg_message4, keg_data5, keg_message5, tv_message_m2t, tv_message_t2m, pb_data, led_data, temp_sensor_data):
        QThread.__init__(self)
        self.keg_data1 = keg_data1
        self.keg_message1 = keg_message1
        self.keg_data2 = keg_data2
        self.keg_message2 = keg_message2
        self.keg_data3 = keg_data3
        self.keg_message3 = keg_message3
        self.keg_data4 = keg_data4
        self.keg_message4 = keg_message4
        self.keg_data5 = keg_data5
        self.keg_message5 = keg_message5
        self.tv_message_m2t = tv_message_m2t
        self.tv_message_t2m = tv_message_t2m
        self.pb_data = pb_data
        self.led_data = led_data
        self.temp_sensor_data = temp_sensor_data
        self.exiting = False

    def __del__(self):
        self.exiting = True

    def _get_gpu_rpi_temp(self):
        try:
            gpu_temp = subprocess.check_output(['/opt/vc/bin/vcgencmd', 'measure_temp'])
            gpu_temp = re.sub(r'\s', "", str(gpu_temp))
            gpu_temp = re.sub(r'temp=', "", str(gpu_temp))
            gpu_temp = re.sub(r'\'C', "", str(gpu_temp))
            logging.debug("GPU Temperature: %s C", str(gpu_temp))
        except CalledProcessError as e:
            output = e.output
            returncode = e.returncode
            logging.warning("Error getting GPU temperature: %s, %s", str(output), str(returncode))
            gpu_temp = 0
        except Exception as e:
            # logging.warning(f"Command error when getting RPi GPU temperature: {e}")
            gpu_temp = 0
        return self._translate_dec_value(gpu_temp)

    def _get_cpu_rpi_temp(self):
        try:
            cpu_temp = subprocess.check_output(['cat', '/sys/class/thermal/thermal_zone0/temp'])
            cpu_temp = re.sub(r'\s', "", str(cpu_temp))
            cpu_temp = float(cpu_temp) / 1000
            logging.debug("CPU Temperature: %s C", str(cpu_temp))
        except CalledProcessError as e:
            output = e.output
            returncode = e.returncode
            logging.warning("Error getting GPU temperature: %s, %s", str(output), str(returncode))
            cpu_temp = 0
        except Exception as e:
            # logging.warning(f"Command error when getting RPi CPU temperature: {e}")
            cpu_temp = 0
        return self._translate_dec_value(cpu_temp)

    def _update_keg1(self):
        logging.debug("Getting Keg1 data...")
        try:
            keg_data_dict1 = self.keg_data1.get_nowait()
            logging.debug("Keg Data Dict 1: %s", str(keg_data_dict1))

        except Empty:
            logging.info("Empty Q when getting data from the keg_data_dict1 queue")
            keg_data_dict_blank = dict()
            return keg_data_dict_blank
        return keg_data_dict1

    def _update_keg1_msg(self):
        logging.debug("Getting Keg1 messages...")
        try:
            keg_message1 = self.keg_message1.get_nowait()
            logging.debug("Keg Message 1: %s", str(keg_message1))

        except Empty:
            logging.info("Empty Q when getting data from the keg_message1 queue")
            return None
        return str(keg_message1)

    def _update_keg2(self):
        logging.debug("Getting Keg2 data...")
        try:
            keg_data_dict2 = self.keg_data2.get_nowait()
            logging.debug("Keg Data Dict 2: %s", str(keg_data_dict2))

        except Empty:
            logging.info("Empty Q when getting data from the keg_data_dict2 queue")
            keg_data_dict_blank = dict()
            return keg_data_dict_blank
        return keg_data_dict2

    def _update_keg2_msg(self):
        logging.debug("Getting Keg2 messages...")
        try:
            keg_message2 = self.keg_message2.get_nowait()
            logging.debug("Keg Message 2: %s", str(keg_message2))

        except Empty:
            logging.info("Empty Q when getting data from the keg_message2 queue")
            return None
        return str(keg_message2)

    def _update_keg3(self):
        logging.debug("Getting Keg3 data...")
        try:
            keg_data_dict3 = self.keg_data3.get_nowait()
            logging.debug("Keg Data Dict 3: %s", str(keg_data_dict3))

        except Empty:
            logging.info("Empty Q when getting data from the keg_data_dict3 queue")
            keg_data_dict_blank = dict()
            return keg_data_dict_blank
        return keg_data_dict3

    def _update_keg3_msg(self):
        logging.debug("Getting Keg3 messages...")
        try:
            keg_message3 = self.keg_message3.get_nowait()
            logging.debug("Keg Message 3: %s", str(keg_message3))

        except Empty:
            logging.info("Empty Q when getting data from the keg_message3 queue")
            return None
        return str(keg_message3)

    def _update_keg4(self):
        logging.debug("Getting Keg4 data...")
        try:
            keg_data_dict4 = self.keg_data4.get_nowait()
            logging.debug("Keg Data Dict 4: %s", str(keg_data_dict4))

        except Empty:
            logging.info("Empty Q when getting data from the keg_data_dict4 queue")
            keg_data_dict_blank = dict()
            return keg_data_dict_blank
        return keg_data_dict4

    def _update_keg4_msg(self):
        logging.debug("Getting Keg4 messages...")
        try:
            keg_message4 = self.keg_message4.get_nowait()
            logging.debug("Keg Message 4: %s", str(keg_message4))

        except Empty:
            logging.info("Empty Q when getting data from the keg_message4 queue")
            return None
        return str(keg_message4)

    def _update_keg5(self):
        logging.debug("Getting Keg5 data...")
        try:
            keg_data_dict5 = self.keg_data5.get_nowait()
            logging.debug("Keg Data Dict 5: %s", str(keg_data_dict5))

        except Empty:
            logging.info("Empty Q when getting data from the keg_data_dict5 queue")
            keg_data_dict_blank = dict()
            return keg_data_dict_blank
        return keg_data_dict5

    def _update_keg5_msg(self):
        logging.debug("Getting Keg5 messages...")
        try:
            keg_message5 = self.keg_message5.get_nowait()
            logging.debug("Keg Message 5: %s", str(keg_message5))

        except Empty:
            logging.info("Empty Q when getting data from the keg_message5 queue")
            return None
        return str(keg_message5)

    def _update_pb(self):
        logging.debug("Getting push button messages...")
        try:
            pb_data_dict = self.pb_data.get_nowait()
            logging.debug("PB message: %s", str(pb_data_dict))

        except Empty:
            logging.info("Empty Q when getting data from the pb_data queue")
            pb_data_dict_blank = dict()
            return pb_data_dict_blank
        return pb_data_dict

    def _update_temp_sensor(self):
        logging.debug("Getting Temp Sensor...")
        try:
            temp_sensor_data_dict = self.temp_sensor_data.get_nowait()
            logging.debug("Temp Sensor message: %s", str(temp_sensor_data_dict))

        except Empty:
            logging.info("Empty Q when getting data from the temp_sensor_data queue")
            temp_sensor_data_dict_blank = dict()
            return temp_sensor_data_dict_blank
        return temp_sensor_data_dict

    def _update_tv(self):
        logging.debug("Getting tv t2m data...")
        try:
            tv_dict = self.tv_message_t2m.get_nowait()
            logging.debug("TV Dict: %s", str(tv_dict))

        except Empty:
            logging.info("Empty Q when getting data from the tv_dict queue")
            tv_dict_blank = dict()
            return tv_dict_blank
        return tv_dict

    def _translate_dec_value(self, flt_value):
        logging.debug("Convert %s", str(flt_value))
        m = re.match(r'[-]?\d+\.\d', str(flt_value))
        if m:
            cat_flt_value = m.group()
            logging.debug("Translated value is: %s (single decimal)", str(cat_flt_value))
            return cat_flt_value
        else:
            #logging.warning("Error in regex when translating decimal value")
            return "0.0"

    def run(self):
        """
        Main data gathering loop

        """
        # Main Update Loop
        logging.info("Waiting for the threads to get spun up...")
        time.sleep(2)
        counter = 99
        wake_tv = False
        while not self.exiting:
            global alt_avg
            if (counter == 100):
                # Get CPU Temp
                cpu_temp = self._get_cpu_rpi_temp()
                gpu_temp = self._get_gpu_rpi_temp()

                try:
                    avg_pi_temp = self._translate_dec_value((float(cpu_temp) + float(gpu_temp)) / 2)
                    logging.debug("Avg GPU/CPU temp: %s", str(avg_pi_temp))
                except:
                    avg_pi_temp = 0.0
                self.update_lcdCPUTemp.emit(str(avg_pi_temp))
                counter = 0
                date_now = time.strftime("%m-%d-%Y")
                self.update_lcdDate.emit(str(date_now))
            else:

                # Get Keg 1 Data
                keg_data_dict1 = self._update_keg1()
                if "BeerRemainingOz" in keg_data_dict1:
                    self.update_lcdBeerRemaining1.emit(str(keg_data_dict1["BeerRemainingOz"]))
                    self.update_lcdPourAmt1.emit(str(keg_data_dict1["PourAmtOz"]))
                    self.update_lcdPourCost1.emit(str(keg_data_dict1['PourCost']))
                    self.update_lcdInstFlowRate1.emit(str(keg_data_dict1["InstFlowRateOzS"]))
                    self.update_lblPourStatusNow1.emit(str(keg_data_dict1["PourStatus"]))
                    self.update_pbarBeerRemaining1.emit(str(keg_data_dict1["KegFillPercent"]))
                    if (str(keg_data_dict1['PourStatus']) == "Pour Active"):
                        wake_tv = True
                else:
                    logging.info("Keg1 Queue is empty when trying to get data")

                # Get Keg 2 Data
                keg_data_dict2 = self._update_keg2()
                if "BeerRemainingOz" in keg_data_dict2:
                    self.update_lcdBeerRemaining2.emit(str(keg_data_dict2["BeerRemainingOz"]))
                    self.update_lcdPourAmt2.emit(str(keg_data_dict2["PourAmtOz"]))
                    self.update_lcdPourCost2.emit(str(keg_data_dict2['PourCost']))
                    self.update_lcdInstFlowRate2.emit(str(keg_data_dict2["InstFlowRateOzS"]))
                    self.update_lblPourStatusNow2.emit(str(keg_data_dict2["PourStatus"]))
                    self.update_pbarBeerRemaining2.emit(str(keg_data_dict2["KegFillPercent"]))
                    if (str(keg_data_dict2['PourStatus']) == "Pour Active"):
                        wake_tv = True

                else:
                    logging.info("Keg2 Queue is empty when trying to get data")

                # Get Keg 3 Data
                keg_data_dict3 = self._update_keg3()
                if "BeerRemainingOz" in keg_data_dict3:
                    self.update_lcdBeerRemaining3.emit(str(keg_data_dict3["BeerRemainingOz"]))
                    self.update_lcdPourAmt3.emit(str(keg_data_dict3["PourAmtOz"]))
                    self.update_lcdPourCost3.emit(str(keg_data_dict3['PourCost']))
                    self.update_lcdInstFlowRate3.emit(str(keg_data_dict3["InstFlowRateOzS"]))
                    self.update_lblPourStatusNow3.emit(str(keg_data_dict3["PourStatus"]))
                    self.update_pbarBeerRemaining3.emit(str(keg_data_dict3["KegFillPercent"]))
                    if (str(keg_data_dict3['PourStatus']) == "Pour Active"):
                        wake_tv = True

                else:
                    logging.info("Keg3 Queue is empty when trying to get data")

                # Get Keg 4 Data
                keg_data_dict4 = self._update_keg4()
                if "BeerRemainingOz" in keg_data_dict4:
                    self.update_lcdBeerRemaining4.emit(str(keg_data_dict4["BeerRemainingOz"]))
                    self.update_lcdPourAmt4.emit(str(keg_data_dict4["PourAmtOz"]))
                    self.update_lcdPourCost4.emit(str(keg_data_dict4['PourCost']))
                    self.update_lcdInstFlowRate4.emit(str(keg_data_dict4["InstFlowRateOzS"]))
                    self.update_lblPourStatusNow4.emit(str(keg_data_dict4["PourStatus"]))
                    self.update_pbarBeerRemaining4.emit(str(keg_data_dict4["KegFillPercent"]))
                    if (str(keg_data_dict4['PourStatus']) == "Pour Active"):
                        wake_tv = True

                else:
                    logging.info("Keg4 Queue is empty when trying to get data")

                # Get Keg 5 Data
                keg_data_dict5 = self._update_keg5()
                if "BeerRemainingOz" in keg_data_dict5:
                    self.update_lcdBeerRemaining5.emit(str(keg_data_dict5["BeerRemainingOz"]))
                    self.update_lcdPourAmt5.emit(str(keg_data_dict5["PourAmtOz"]))
                    self.update_lcdPourCost5.emit(str(keg_data_dict5['PourCost']))
                    self.update_lcdInstFlowRate5.emit(str(keg_data_dict5["InstFlowRateOzS"]))
                    self.update_lblPourStatusNow5.emit(str(keg_data_dict5["PourStatus"]))
                    self.update_pbarBeerRemaining5.emit(str(keg_data_dict5["KegFillPercent"]))
                    if (str(keg_data_dict5['PourStatus']) == "Pour Active"):
                        wake_tv = True

                else:
                    logging.info("Keg5 Queue is empty when trying to get data")

                # Get Temperature Sensor Data
                temp_sensor_data_dict = self._update_temp_sensor()
                if "TempF" in temp_sensor_data_dict:
                    temp_f_format = "%.1f" % temp_sensor_data_dict['TempF']
                    self.update_lcdTempSensor.emit(str(temp_f_format))

                # Wake TV from a button press
                pb_data_dict = self._update_pb()
                if "ButtonPressed" in pb_data_dict:
                    if pb_data_dict['ButtonPressed']:
                        wake_tv = True

                # Get the TV Sleep Timer Value
                tv_dict = self._update_tv()
                if "SleepTimer" in tv_dict:
                    self.update_lcdTVSleep.emit(str(tv_dict["SleepTimer"]))
                    if int(tv_dict['SleepTimer']) == 0:
                        led_dict = dict()
                        led_dict['PowerActive'] = False
                        try:
                            self.led_data.put(led_dict)
                        except Full:
                            logging.warning("LED control queue full when sending sleep state command")
                    else:
                        led_dict = dict()
                        led_dict['PowerActive'] = True
                        try:
                            self.led_data.put(led_dict)
                        except Full:
                            logging.warning("LED control queue full when sending sleep state command")


                # Get messages from the message queue for the scrolling log box
                keg_message1_str = self._update_keg1_msg()
                if not keg_message1_str is None:
                    self.update_textboxLogMessage.emit(str(keg_message1_str))

                keg_message2_str = self._update_keg2_msg()
                if not keg_message2_str is None:
                    self.update_textboxLogMessage.emit(str(keg_message2_str))

                keg_message3_str = self._update_keg3_msg()
                if not keg_message3_str is None:
                    self.update_textboxLogMessage.emit(str(keg_message3_str))

                keg_message4_str = self._update_keg4_msg()
                if not keg_message4_str is None:
                    self.update_textboxLogMessage.emit(str(keg_message4_str))

                keg_message5_str = self._update_keg5_msg()
                if not keg_message5_str is None:
                    self.update_textboxLogMessage.emit(str(keg_message5_str))

                if wake_tv == "Help me":
                    #Send message to wake TV
                    #self.tv_message_m2t = tv_message_m2t
                    tv_dict = dict()
                    tv_dict['PowerOn'] = True
                    led_dict = dict()
                    led_dict['PowerActive'] = True
                    try:
                        self.tv_message_m2t.put(tv_dict)
                        wake_tv = False
                    except Full:
                        logging.warning("TV m2t queue is full when sending turn on command")
                    try:
                        self.led_data.put(led_dict)
                    except Full:
                        logging.warning("LED control queue full when sending sleep state command")

                time_now = time.strftime("%H:%M:%S")
                self.update_lcdTimeOfDay.emit(str(time_now))
                counter += 1
            time.sleep(.1)


class MainWindow(QWidget):

    def __init__(self, fullscreen_flag, autostart_flag, keg_thread1, keg_data1, keg_message1, keg_dict1,
                                                        keg_thread2, keg_data2, keg_message2, keg_dict2,
                                                        keg_thread3, keg_data3, keg_message3, keg_dict3,
                                                        keg_thread4, keg_data4, keg_message4, keg_dict4,
                                                        keg_thread5, keg_data5, keg_message5, keg_dict5,
                                                        tv_thread, tv_message_m2t, tv_message_t2m,
                                                        pb_thread, pb_data, led_thread, led_data, temp_sensor_thread, temp_sensor_data):
        super(MainWindow, self).__init__()
        self.fullscreen_flag = fullscreen_flag
        self.autostart_flag = autostart_flag
        self.keg_thread1 = keg_thread1
        self.keg_data1 = keg_data1
        self.keg_message1 = keg_message1
        self.keg_dict1 = keg_dict1

        self.keg_thread2 = keg_thread2
        self.keg_data2 = keg_data2
        self.keg_message2 = keg_message2
        self.keg_dict2 = keg_dict2

        self.keg_thread3 = keg_thread3
        self.keg_data3 = keg_data3
        self.keg_message3 = keg_message3
        self.keg_dict3 = keg_dict3

        self.keg_thread4 = keg_thread4
        self.keg_data4 = keg_data4
        self.keg_message4 = keg_message4
        self.keg_dict4 = keg_dict4

        self.keg_thread5 = keg_thread5
        self.keg_data5 = keg_data5
        self.keg_message5 = keg_message5
        self.keg_dict5 = keg_dict5

        self.tv_thread = tv_thread
        self.tv_message_m2t = tv_message_m2t
        self.tv_message_t2m = tv_message_t2m

        self.pb_thread = pb_thread
        self.pb_data = pb_data

        self.led_thread = led_thread
        self.led_data = led_data

        self.temp_sensor_thread = temp_sensor_thread
        self.temp_sensor_data = temp_sensor_data
        self.initUI()

    def closeEvent(self, event):
        print("Closing window...")
        self.stop_getting_data()
        event.accept()  # Allow the window to close

    def initUI(self):
        self.textboxLogMessage = QPlainTextEdit(self)
        self.textboxLogMessage.setReadOnly(True)

        self.font = QtGui.QFont()
        self.font.setFamily('Lucida')
        self.font.setFixedPitch(True)
        self.font.setPointSize(22)
        #self.font.setBold(true)

        # Status Bar
        #self.sb = QtGui.QStatusBar(self)
        #self.sb.setFixedHeight(18)

        # Vertical Line
        self.vline = QFrame(self)
        self.vline.setFrameShape(QFrame.Shape.VLine)

        self.vline2 = QFrame(self)
        self.vline2.setFrameShape(QFrame.Shape.VLine)

        self.vline3 = QFrame(self)
        self.vline3.setFrameShape(QFrame.Shape.VLine)

        self.vline4 = QFrame(self)
        self.vline4.setFrameShape(QFrame.Shape.VLine)

        lblVenmo = QLabel(self)
        pixmapvenmo = QtGui.QPixmap(logo_image)
        lblVenmo.setPixmap(pixmapvenmo)
        lblVenmo.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBreweryLogo1 = QLabel(self)
        pixmap1 = QtGui.QPixmap('logos/' + self.keg_dict1['logo'])
        lblBreweryLogo1.setPixmap(pixmap1)
        lblBreweryLogo1.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBreweryLogo2 = QLabel(self)
        pixmap2 = QtGui.QPixmap('logos/' + self.keg_dict2['logo'])
        lblBreweryLogo2.setPixmap(pixmap2)
        lblBreweryLogo2.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBreweryLogo3 = QLabel(self)
        pixmap3 = QtGui.QPixmap('logos/' + self.keg_dict3['logo'])
        lblBreweryLogo3.setPixmap(pixmap3)
        lblBreweryLogo3.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBreweryLogo4 = QLabel(self)
        pixmap4 = QtGui.QPixmap('logos/' + self.keg_dict4['logo'])
        lblBreweryLogo4.setPixmap(pixmap4)
        lblBreweryLogo4.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBreweryLogo5 = QLabel(self)
        pixmap5 = QtGui.QPixmap('logos/' + self.keg_dict5['logo'])
        lblBreweryLogo5.setPixmap(pixmap5)
        lblBreweryLogo5.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBeerName = QLabel('Beer Name')
        lblBeerName.setFont(self.font)
        lblBeerName.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBeerName1 = QLabel(self.keg_dict1['name'])
        lblBeerName1.setFont(self.font)
        lblBeerName1.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBeerName2 = QLabel(self.keg_dict2['name'])
        lblBeerName2.setFont(self.font)
        lblBeerName2.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBeerName3 = QLabel(self.keg_dict3['name'])
        lblBeerName3.setFont(self.font)
        lblBeerName3.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBeerName4 = QLabel(self.keg_dict4['name'])
        lblBeerName4.setFont(self.font)
        lblBeerName4.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBeerName5 = QLabel(self.keg_dict5['name'])
        lblBeerName5.setFont(self.font)
        lblBeerName5.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBrewery = QLabel('Brewery')
        lblBrewery.setFont(self.font)
        lblBrewery.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBrewery1 = QLabel(self.keg_dict1['brewery'])
        lblBrewery1.setFont(self.font)
        lblBrewery1.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBrewery2 = QLabel(self.keg_dict2['brewery'])
        lblBrewery2.setFont(self.font)
        lblBrewery2.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBrewery3 = QLabel(self.keg_dict3['brewery'])
        lblBrewery3.setFont(self.font)
        lblBrewery3.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBrewery4 = QLabel(self.keg_dict4['brewery'])
        lblBrewery4.setFont(self.font)
        lblBrewery4.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBrewery5 = QLabel(self.keg_dict5['brewery'])
        lblBrewery5.setFont(self.font)
        lblBrewery5.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBeerType = QLabel('Beer Type')
        lblBeerType.setFont(self.font)
        lblBeerType.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBeerType1 = QLabel(self.keg_dict1['type'])
        lblBeerType1.setFont(self.font)
        lblBeerType1.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBeerType2 = QLabel(self.keg_dict2['type'])
        lblBeerType2.setFont(self.font)
        lblBeerType2.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBeerType3 = QLabel(self.keg_dict3['type'])
        lblBeerType3.setFont(self.font)
        lblBeerType3.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBeerType4 = QLabel(self.keg_dict4['type'])
        lblBeerType4.setFont(self.font)
        lblBeerType4.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBeerType5 = QLabel(self.keg_dict5['type'])
        lblBeerType5.setFont(self.font)
        lblBeerType5.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBeerABV = QLabel('ABV')
        lblBeerABV.setFont(self.font)
        lblBeerABV.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBeerABV1 = QLabel(self.keg_dict1['abv'])
        lblBeerABV1.setFont(self.font)
        lblBeerABV1.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBeerABV2 = QLabel(self.keg_dict2['abv'])
        lblBeerABV2.setFont(self.font)
        lblBeerABV2.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBeerABV3 = QLabel(self.keg_dict3['abv'])
        lblBeerABV3.setFont(self.font)
        lblBeerABV3.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBeerABV4 = QLabel(self.keg_dict4['abv'])
        lblBeerABV4.setFont(self.font)
        lblBeerABV4.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBeerABV5 = QLabel(self.keg_dict5['abv'])
        lblBeerABV5.setFont(self.font)
        lblBeerABV5.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBeerIBU = QLabel('IBU')
        lblBeerIBU.setFont(self.font)
        lblBeerIBU.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBeerIBU1 = QLabel(self.keg_dict1['ibu'])
        lblBeerIBU1.setFont(self.font)
        lblBeerIBU1.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBeerIBU2 = QLabel(self.keg_dict2['ibu'])
        lblBeerIBU2.setFont(self.font)
        lblBeerIBU2.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBeerIBU3 = QLabel(self.keg_dict3['ibu'])
        lblBeerIBU3.setFont(self.font)
        lblBeerIBU3.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBeerIBU4 = QLabel(self.keg_dict4['ibu'])
        lblBeerIBU4.setFont(self.font)
        lblBeerIBU4.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBeerIBU5 = QLabel(self.keg_dict5['ibu'])
        lblBeerIBU5.setFont(self.font)
        lblBeerIBU5.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblBeerRemaining = QLabel('Beer Remaining (fl. oz.)')
        lblBeerRemaining.setFont(self.font)
        lblBeerRemaining.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblKegGuage = QLabel('Keg Fill Level')
        lblKegGuage.setFont(self.font)
        lblKegGuage.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblPourAmt = QLabel('This Pour (fl. oz.)')
        lblPourAmt.setFont(self.font)
        lblPourAmt.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblPourCost = QLabel('Cost of Pour ($)')
        lblPourCost.setFont(self.font)
        lblPourCost.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblInstFlowRate = QLabel('Inst. Flow Rate (fl. oz./s)')
        lblInstFlowRate.setFont(self.font)
        lblInstFlowRate.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        lblPourStatus = QLabel('Status')
        lblPourStatus.setFont(self.font)
        lblPourStatus.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.lblPourStatusNow1 = QLabel('Ready')
        self.lblPourStatusNow1.setFont(self.font)
        self.lblPourStatusNow1.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.lblPourStatusNow2 = QLabel('Ready')
        self.lblPourStatusNow2.setFont(self.font)
        self.lblPourStatusNow2.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.lblPourStatusNow3 = QLabel('Ready')
        self.lblPourStatusNow3.setFont(self.font)
        self.lblPourStatusNow3.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.lblPourStatusNow4 = QLabel('Ready')
        self.lblPourStatusNow4.setFont(self.font)
        self.lblPourStatusNow4.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.lblPourStatusNow5 = QLabel('Ready')
        self.lblPourStatusNow5.setFont(self.font)
        self.lblPourStatusNow5.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.lcdBeerRemaining1 = QLCDNumber()
        self.lcdBeerRemaining1.setDigitCount(7)
        self.lcdBeerRemaining2 = QLCDNumber()
        self.lcdBeerRemaining2.setDigitCount(7)
        self.lcdBeerRemaining3 = QLCDNumber()
        self.lcdBeerRemaining3.setDigitCount(7)
        self.lcdBeerRemaining4 = QLCDNumber()
        self.lcdBeerRemaining4.setDigitCount(7)
        self.lcdBeerRemaining5 = QLCDNumber()
        self.lcdBeerRemaining5.setDigitCount(7)

        self.pbarBeerRemaining1 = QProgressBar(self)
        self.pbarBeerRemaining1.setMinimum(0)
        self.pbarBeerRemaining1.setMaximum(100)
        self.pbarBeerRemaining1.setValue(0)
        self.pbarBeerRemaining2 = QProgressBar(self)
        self.pbarBeerRemaining2.setMinimum(0)
        self.pbarBeerRemaining2.setMaximum(100)
        self.pbarBeerRemaining2.setValue(0)
        self.pbarBeerRemaining3 = QProgressBar(self)
        self.pbarBeerRemaining3.setMinimum(0)
        self.pbarBeerRemaining3.setMaximum(100)
        self.pbarBeerRemaining3.setValue(0)
        self.pbarBeerRemaining4 = QProgressBar(self)
        self.pbarBeerRemaining4.setMinimum(0)
        self.pbarBeerRemaining4.setMaximum(100)
        self.pbarBeerRemaining4.setValue(0)
        self.pbarBeerRemaining5 = QProgressBar(self)
        self.pbarBeerRemaining5.setMinimum(0)
        self.pbarBeerRemaining5.setMaximum(100)
        self.pbarBeerRemaining5.setValue(0)

        self.lcdPourAmt1 = QLCDNumber()
        self.lcdPourAmt1.setDigitCount(7)
        self.lcdPourAmt2 = QLCDNumber()
        self.lcdPourAmt2.setDigitCount(7)
        self.lcdPourAmt3 = QLCDNumber()
        self.lcdPourAmt3.setDigitCount(7)
        self.lcdPourAmt4 = QLCDNumber()
        self.lcdPourAmt4.setDigitCount(7)
        self.lcdPourAmt5 = QLCDNumber()
        self.lcdPourAmt5.setDigitCount(7)

        self.lcdPourCost1 = QLCDNumber()
        self.lcdPourCost1.setDigitCount(7)
        self.lcdPourCost2 = QLCDNumber()
        self.lcdPourCost2.setDigitCount(7)
        self.lcdPourCost3 = QLCDNumber()
        self.lcdPourCost3.setDigitCount(7)
        self.lcdPourCost4 = QLCDNumber()
        self.lcdPourCost4.setDigitCount(7)
        self.lcdPourCost5 = QLCDNumber()
        self.lcdPourCost5.setDigitCount(7)

        self.lcdInstFlowRate1 = QLCDNumber()
        self.lcdInstFlowRate1.setDigitCount(7)
        self.lcdInstFlowRate2 = QLCDNumber()
        self.lcdInstFlowRate2.setDigitCount(7)
        self.lcdInstFlowRate3 = QLCDNumber()
        self.lcdInstFlowRate3.setDigitCount(7)
        self.lcdInstFlowRate4 = QLCDNumber()
        self.lcdInstFlowRate4.setDigitCount(7)
        self.lcdInstFlowRate5 = QLCDNumber()
        self.lcdInstFlowRate5.setDigitCount(7)

        # CPU and (Rpi) Temp Label and LCD
        lblCPUTemp = QLabel('Pi CPU Temp (\xb0C)')
        lblCPUTemp.setFont(self.font)
        lblCPUTemp.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.lcdCPUTemp = QLCDNumber()
        self.lcdCPUTemp.setDigitCount(4)

        # CPU and (Rpi) Temp Label and LCD
        lblTempSensor = QLabel('Kegerator Temp (\xb0F)')
        lblTempSensor.setFont(self.font)
        lblTempSensor.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.lcdTempSensor = QLCDNumber()
        self.lcdTempSensor.setDigitCount(4)

        # TV Sleep Timer
        lblTVSleep = QLabel('TV Sleep Timer')
        lblTVSleep.setFont(self.font)
        lblTVSleep.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.lcdTVSleep = QLCDNumber()
        self.lcdTVSleep.setDigitCount(4)

        self.lcdTimeOfDay = QLCDNumber()
        self.lcdTimeOfDay.setDigitCount(8)
        self.lcdDate = QLCDNumber()
        self.lcdDate.setDigitCount(10)

        #... row#, col#, row_span, col_span
        grid = QGridLayout()
        grid.setSpacing(5)

        row_num = 0
        grid.addWidget(lblVenmo, row_num, 0, 1, 1)
        grid.addWidget(lblBreweryLogo1, row_num, 1, 1, 1)
        grid.addWidget(lblBreweryLogo2, row_num, 3, 1, 1)
        grid.addWidget(lblBreweryLogo3, row_num, 5, 1, 1)
        grid.addWidget(lblBreweryLogo4, row_num, 7, 1, 1)
        grid.addWidget(lblBreweryLogo5, row_num, 9, 1, 1)

        #Row
        row_num += 1
        grid.addWidget(lblBeerName, row_num, 0, 1, 1)
        grid.addWidget(lblBeerName1, row_num, 1, 1, 1)
        grid.addWidget(self.vline, row_num, 2, 11, 1)
        grid.addWidget(lblBeerName2, row_num, 3, 1, 1)
        grid.addWidget(self.vline2, row_num, 4, 11, 1)
        grid.addWidget(lblBeerName3, row_num, 5, 1, 1)
        grid.addWidget(self.vline3, row_num, 6, 11, 1)
        grid.addWidget(lblBeerName4, row_num, 7, 1, 1)
        grid.addWidget(self.vline4, row_num, 8, 11, 1)
        grid.addWidget(lblBeerName5, row_num, 9, 1, 1)

        #Row
        row_num += 1
        grid.addWidget(lblBrewery, row_num, 0, 1, 1)
        grid.addWidget(lblBrewery1, row_num, 1, 1, 1)
        #grid.addWidget(self.vline, row_num, 2, 9, 1)
        grid.addWidget(lblBrewery2, row_num, 3, 1, 1)
        #grid.addWidget(self.vline2, row_num, 4, 9, 1)
        grid.addWidget(lblBrewery3, row_num, 5, 1, 1)
        #grid.addWidget(self.vline3, row_num, 6, 9, 1)
        grid.addWidget(lblBrewery4, row_num, 7, 1, 1)
        #grid.addWidget(self.vline4, row_num, 8, 9, 1)
        grid.addWidget(lblBrewery5, row_num, 9, 1, 1)

        #Row
        row_num += 1
        grid.addWidget(lblBeerType, row_num, 0, 1, 1)
        grid.addWidget(lblBeerType1, row_num, 1, 1, 1)
        #grid.addWidget(self.vline, row_num, 2, 9, 1)
        grid.addWidget(lblBeerType2, row_num, 3, 1, 1)
        #grid.addWidget(self.vline2, row_num, 4, 9, 1)
        grid.addWidget(lblBeerType3, row_num, 5, 1, 1)
        #grid.addWidget(self.vline3, row_num, 6, 9, 1)
        grid.addWidget(lblBeerType4, row_num, 7, 1, 1)
        #grid.addWidget(self.vline4, row_num, 8, 9, 1)
        grid.addWidget(lblBeerType5, row_num, 9, 1, 1)

        #Row
        row_num += 1
        grid.addWidget(lblBeerABV, row_num, 0, 1, 1)
        grid.addWidget(lblBeerABV1, row_num, 1, 1, 1)
        #grid.addWidget(self.vline, row_num, 2, 9, 1)
        grid.addWidget(lblBeerABV2, row_num, 3, 1, 1)
        #grid.addWidget(self.vline2, row_num, 4, 9, 1)
        grid.addWidget(lblBeerABV3, row_num, 5, 1, 1)
        #grid.addWidget(self.vline3, row_num, 6, 9, 1)
        grid.addWidget(lblBeerABV4, row_num, 7, 1, 1)
        #grid.addWidget(self.vline4, row_num, 8, 9, 1)
        grid.addWidget(lblBeerABV5, row_num, 9, 1, 1)

        #Row
        row_num += 1
        grid.addWidget(lblBeerIBU, row_num, 0, 1, 1)
        grid.addWidget(lblBeerIBU1, row_num, 1, 1, 1)
        #grid.addWidget(self.vline, row_num, 2, 9, 1)
        grid.addWidget(lblBeerIBU2, row_num, 3, 1, 1)
        #grid.addWidget(self.vline2, row_num, 4, 9, 1)
        grid.addWidget(lblBeerIBU3, row_num, 5, 1, 1)
        #grid.addWidget(self.vline3, row_num, 6, 9, 1)
        grid.addWidget(lblBeerIBU4, row_num, 7, 1, 1)
        #grid.addWidget(self.vline4, row_num, 8, 9, 1)
        grid.addWidget(lblBeerIBU5, row_num, 9, 1, 1)

        #Row
        row_num += 1
        grid.addWidget(lblKegGuage, row_num, 0, 1, 1)
        grid.addWidget(self.pbarBeerRemaining1, row_num, 1, 1, 1)
        #grid.addWidget(self.vline, row_num, 2, 9, 1)
        grid.addWidget(self.pbarBeerRemaining2, row_num, 3, 1, 1)
        #grid.addWidget(self.vline2, row_num, 4, 9, 1)
        grid.addWidget(self.pbarBeerRemaining3, row_num, 5, 1, 1)
        #grid.addWidget(self.vline2, row_num, 6, 9, 1)
        grid.addWidget(self.pbarBeerRemaining4, row_num, 7, 1, 1)
        #grid.addWidget(self.vline2, row_num, 8, 9, 1)
        grid.addWidget(self.pbarBeerRemaining5, row_num, 9, 1, 1)

        #Row
        row_num += 1
        grid.addWidget(lblBeerRemaining, row_num, 0, 1, 1)
        grid.addWidget(self.lcdBeerRemaining1, row_num, 1, 1, 1)
        #grid.addWidget(self.vline, row_num, 2, 9, 1)
        grid.addWidget(self.lcdBeerRemaining2, row_num, 3, 1, 1)
        #grid.addWidget(self.vline2, row_num, 4, 9, 1)
        grid.addWidget(self.lcdBeerRemaining3, row_num, 5, 1, 1)
        #grid.addWidget(self.vline3, row_num, 6, 9, 1)
        grid.addWidget(self.lcdBeerRemaining4, row_num, 7, 1, 1)
        #grid.addWidget(self.vline4, row_num, 8, 9, 1)
        grid.addWidget(self.lcdBeerRemaining5, row_num, 9, 1, 1)

        #Row
        row_num += 1
        grid.addWidget(lblPourAmt, row_num, 0, 1, 1)
        grid.addWidget(self.lcdPourAmt1, row_num, 1, 1, 1)
        #grid.addWidget(self.vline, row_num, 2, 9, 1)
        grid.addWidget(self.lcdPourAmt2, row_num, 3, 1, 1)
        #grid.addWidget(self.vline2, row_num, 4, 9, 1)
        grid.addWidget(self.lcdPourAmt3, row_num, 5, 1, 1)
        #grid.addWidget(self.vline3, row_num, 6, 9, 1)
        grid.addWidget(self.lcdPourAmt4, row_num, 7, 1, 1)
        #grid.addWidget(self.vline4, row_num, 8, 9, 1)
        grid.addWidget(self.lcdPourAmt5, row_num, 9, 1, 1)

        #Row
        row_num += 1
        grid.addWidget(lblPourCost, row_num, 0, 1, 1)
        grid.addWidget(self.lcdPourCost1, row_num, 1, 1, 1)
        #grid.addWidget(self.vline, row_num, 2, 9, 1)
        grid.addWidget(self.lcdPourCost2, row_num, 3, 1, 1)
        #grid.addWidget(self.vline2, row_num, 4, 9, 1)
        grid.addWidget(self.lcdPourCost3, row_num, 5, 1, 1)
        #grid.addWidget(self.vline3, row_num, 6, 9, 1)
        grid.addWidget(self.lcdPourCost4, row_num, 7, 1, 1)
        #grid.addWidget(self.vline4, row_num, 8, 9, 1)
        grid.addWidget(self.lcdPourCost5, row_num, 9, 1, 1)

        #Row
        row_num += 1
        grid.addWidget(lblInstFlowRate, row_num, 0, 1, 1)
        grid.addWidget(self.lcdInstFlowRate1, row_num, 1, 1, 1)
        #grid.addWidget(self.vline, row_num, 2, 9, 1)
        grid.addWidget(self.lcdInstFlowRate2, row_num, 3, 1, 1)
        #grid.addWidget(self.vline2, row_num, 4, 9, 1)
        grid.addWidget(self.lcdInstFlowRate3, row_num, 5, 1, 1)
        #grid.addWidget(self.vline3, row_num, 6, 9, 1)
        grid.addWidget(self.lcdInstFlowRate4, row_num, 7, 1, 1)
        #grid.addWidget(self.vline4, row_num, 8, 9, 1)
        grid.addWidget(self.lcdInstFlowRate5, row_num, 9, 1, 1)

        #Row
        row_num += 1
        grid.addWidget(lblPourStatus, row_num, 0, 1, 1)
        grid.addWidget(self.lblPourStatusNow1, row_num, 1, 1, 1)
        #grid.addWidget(self.vline, row_num, 2, 9, 1)
        grid.addWidget(self.lblPourStatusNow2, row_num, 3, 1, 1)
        #grid.addWidget(self.vline2, row_num, 4, 9, 1)
        grid.addWidget(self.lblPourStatusNow3, row_num, 5, 1, 1)
        #grid.addWidget(self.vline3, row_num, 6, 9, 1)
        grid.addWidget(self.lblPourStatusNow4, row_num, 7, 1, 1)
        #grid.addWidget(self.vline4, row_num, 8, 9, 1)
        grid.addWidget(self.lblPourStatusNow5, row_num, 9, 1, 1)

        #Row
        row_num += 1
        grid.addWidget(self.textboxLogMessage, row_num, 0, 5, 4)
        grid.addWidget(self.lcdTimeOfDay, row_num, 5, 1, 5)
        grid.addWidget(self.lcdDate, row_num+1, 5, 1, 5)

        grid.addWidget(lblCPUTemp, row_num+2, 5, 1, 3)
        grid.addWidget(self.lcdCPUTemp, row_num+2, 8, 1, 2)

        grid.addWidget(lblTempSensor, row_num+3, 5, 1, 3)
        grid.addWidget(self.lcdTempSensor, row_num+3, 8, 1, 2)

        grid.addWidget(lblTVSleep, row_num+4, 5, 1, 3)
        grid.addWidget(self.lcdTVSleep, row_num+4, 8, 1, 2)

        #grid.addWidget(self.sb, int(row_num+4), 0, 1, 5)

        self.setLayout(grid)
        self.setGeometry(300, 300, 350, 300)
        self.setWindowTitle('Kegomatic')
        #self.sb.showMessage("Ready")
        if self.autostart_flag:
            self.start_getting_data()

        if self.fullscreen_flag:
            self.showMaximized()
        else:
            self.show()

    def start_getting_data(self):
        self.get_thread = gatherDataThread(self.keg_data1, self.keg_message1, self.keg_data2, self.keg_message2, self.keg_data3, self.keg_message3, self.keg_data4, self.keg_message4, self.keg_data5, self.keg_message5, self.tv_message_m2t, self.tv_message_t2m, self.pb_data, self.led_data, self.temp_sensor_data)

        self.get_thread.update_lcdBeerRemaining1.connect(self.update_lcdBeerRemaining1)
        self.get_thread.update_lcdBeerRemaining2.connect(self.update_lcdBeerRemaining2)
        self.get_thread.update_lcdBeerRemaining3.connect(self.update_lcdBeerRemaining3)
        self.get_thread.update_lcdBeerRemaining4.connect(self.update_lcdBeerRemaining4)
        self.get_thread.update_lcdBeerRemaining5.connect(self.update_lcdBeerRemaining5)
        self.get_thread.update_lcdPourAmt1.connect(self.update_lcdPourAmt1)
        self.get_thread.update_lcdPourAmt2.connect(self.update_lcdPourAmt2)
        self.get_thread.update_lcdPourAmt3.connect(self.update_lcdPourAmt3)
        self.get_thread.update_lcdPourAmt4.connect(self.update_lcdPourAmt4)
        self.get_thread.update_lcdPourAmt5.connect(self.update_lcdPourAmt5)
        self.get_thread.update_lcdPourCost1.connect(self.update_lcdPourCost1)
        self.get_thread.update_lcdPourCost2.connect(self.update_lcdPourCost2)
        self.get_thread.update_lcdPourCost3.connect(self.update_lcdPourCost3)
        self.get_thread.update_lcdPourCost4.connect(self.update_lcdPourCost4)
        self.get_thread.update_lcdPourCost5.connect(self.update_lcdPourCost5)
        self.get_thread.update_lcdInstFlowRate1.connect(self.update_lcdInstFlowRate1)
        self.get_thread.update_lcdInstFlowRate2.connect(self.update_lcdInstFlowRate2)
        self.get_thread.update_lcdInstFlowRate3.connect(self.update_lcdInstFlowRate3)
        self.get_thread.update_lcdInstFlowRate4.connect(self.update_lcdInstFlowRate4)
        self.get_thread.update_lcdInstFlowRate5.connect(self.update_lcdInstFlowRate5)
        self.get_thread.update_lcdCPUTemp.connect(self.update_lcdCPUTemp)
        self.get_thread.update_lcdTempSensor.connect(self.update_lcdTempSensor)
        self.get_thread.update_lcdTVSleep.connect(self.update_lcdTVSleep)
        self.get_thread.update_lcdTimeOfDay.connect(self.update_lcdTimeOfDay)
        self.get_thread.update_lcdDate.connect(self.update_lcdDate)
        self.get_thread.update_lblPourStatusNow1.connect(self.update_lblPourStatusNow1)
        self.get_thread.update_lblPourStatusNow2.connect(self.update_lblPourStatusNow2)
        self.get_thread.update_lblPourStatusNow3.connect(self.update_lblPourStatusNow3)
        self.get_thread.update_lblPourStatusNow4.connect(self.update_lblPourStatusNow4)
        self.get_thread.update_lblPourStatusNow5.connect(self.update_lblPourStatusNow5)
        self.get_thread.update_pbarBeerRemaining1.connect(self.update_pbarBeerRemaining1)
        self.get_thread.update_pbarBeerRemaining2.connect(self.update_pbarBeerRemaining2)
        self.get_thread.update_pbarBeerRemaining3.connect(self.update_pbarBeerRemaining3)
        self.get_thread.update_pbarBeerRemaining4.connect(self.update_pbarBeerRemaining4)
        self.get_thread.update_pbarBeerRemaining5.connect(self.update_pbarBeerRemaining5)
        self.get_thread.update_textboxLogMessage.connect(self.update_textboxLogMessage)


        self.get_thread.start()
        #self.sb.showMessage("Main Polling Thread Running")
        self.keg_thread1.start()
        self.keg_thread2.start()
        self.keg_thread3.start()
        self.keg_thread4.start()
        self.keg_thread5.start()
        self.tv_thread.start()
        self.pb_thread.start()
        self.led_thread.start()
        self.temp_sensor_thread.start()
        self.first_run = False

    def stop_getting_data(self):
        print("Stopping all threads and processes...")

        # Stop the QThread first
        if hasattr(self, 'get_thread'):
            self.get_thread.exiting = True
            self.get_thread.quit()
            if not self.get_thread.wait(5000):  # Wait up to 5 seconds
                print("Warning: gatherDataThread did not stop cleanly")

        # Shutdown all hardware processes
        processes = [
            ('keg_thread1', self.keg_thread1),
            ('keg_thread2', self.keg_thread2),
            ('keg_thread3', self.keg_thread3),
            ('keg_thread4', self.keg_thread4),
            ('keg_thread5', self.keg_thread5),
            ('tv_thread', self.tv_thread),
            ('pb_thread', self.pb_thread),
            ('led_thread', self.led_thread),
            ('temp_sensor_thread', self.temp_sensor_thread)
        ]

        for name, proc in processes:
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
            except Exception as e:
                print(f"Error stopping {name}: {e}")

        print("All threads and processes stopped.")

    def update_lcdBeerRemaining1(self, BeerRemaining1):
        self.lcdBeerRemaining1.display(BeerRemaining1)

    def update_lcdBeerRemaining2(self, BeerRemaining2):
        self.lcdBeerRemaining2.display(BeerRemaining2)

    def update_lcdBeerRemaining3(self, BeerRemaining3):
        self.lcdBeerRemaining3.display(BeerRemaining3)

    def update_lcdBeerRemaining4(self, BeerRemaining4):
        self.lcdBeerRemaining4.display(BeerRemaining4)

    def update_lcdBeerRemaining5(self, BeerRemaining5):
        self.lcdBeerRemaining5.display(BeerRemaining5)

    def update_lcdPourAmt1(self, PourAmt1):
        self.lcdPourAmt1.display(PourAmt1)

    def update_lcdPourAmt2(self, PourAmt2):
        self.lcdPourAmt2.display(PourAmt2)

    def update_lcdPourAmt3(self, PourAmt3):
        self.lcdPourAmt3.display(PourAmt3)

    def update_lcdPourAmt4(self, PourAmt4):
        self.lcdPourAmt4.display(PourAmt4)

    def update_lcdPourAmt5(self, PourAmt5):
        self.lcdPourAmt5.display(PourAmt5)

    def update_lcdPourCost1(self, PourCost1):
        self.lcdPourCost1.display(PourCost1)

    def update_lcdPourCost2(self, PourCost2):
        self.lcdPourCost2.display(PourCost2)

    def update_lcdPourCost3(self, PourCost3):
        self.lcdPourCost3.display(PourCost3)

    def update_lcdPourCost4(self, PourCost4):
        self.lcdPourCost4.display(PourCost4)

    def update_lcdPourCost5(self, PourCost5):
        self.lcdPourCost5.display(PourCost5)

    def update_lcdInstFlowRate1(self, InstFlowRate1):
        self.lcdInstFlowRate1.display(InstFlowRate1)

    def update_lcdInstFlowRate2(self, InstFlowRate2):
        self.lcdInstFlowRate2.display(InstFlowRate2)

    def update_lcdInstFlowRate3(self, InstFlowRate3):
        self.lcdInstFlowRate3.display(InstFlowRate3)

    def update_lcdInstFlowRate4(self, InstFlowRate4):
        self.lcdInstFlowRate4.display(InstFlowRate4)

    def update_lcdInstFlowRate5(self, InstFlowRate5):
        self.lcdInstFlowRate5.display(InstFlowRate5)

    def update_lcdCPUTemp(self, cpu_temp):
        self.lcdCPUTemp.display(cpu_temp)

    def update_lcdTempSensor(self, temp_sensor):
        self.lcdTempSensor.display(temp_sensor)

    def update_lcdTVSleep(self, tv_sleep):
        self.lcdTVSleep.display(tv_sleep)

    def update_lcdTimeOfDay(self, time_now):
        self.lcdTimeOfDay.display(time_now)

    def update_lcdDate(self, date):
        self.lcdDate.display(date)

    def update_lblPourStatusNow1(self, PourStatusNow1):
        self.lblPourStatusNow1.setText(PourStatusNow1)
        if PourStatusNow1 == "Keg Empty":
            self.lblPourStatusNow1.setText("<font color='red'>Keg Empty</font>")

    def update_lblPourStatusNow2(self, PourStatusNow2):
        self.lblPourStatusNow2.setText(PourStatusNow2)
        if PourStatusNow2 == "Keg Empty":
            self.lblPourStatusNow2.setText("<font color='red'>Keg Empty</font>")

    def update_lblPourStatusNow3(self, PourStatusNow3):
        self.lblPourStatusNow3.setText(PourStatusNow3)
        if PourStatusNow3 == "Keg Empty":
            self.lblPourStatusNow3.setText("<font color='red'>Keg Empty</font>")

    def update_lblPourStatusNow4(self, PourStatusNow4):
        self.lblPourStatusNow4.setText(PourStatusNow4)
        if PourStatusNow4 == "Keg Empty":
            self.lblPourStatusNow4.setText("<font color='red'>Keg Empty</font>")

    def update_lblPourStatusNow5(self, PourStatusNow5):
        self.lblPourStatusNow5.setText(PourStatusNow5)
        if PourStatusNow5 == "Keg Empty":
            self.lblPourStatusNow5.setText("<font color='red'>Keg Empty</font>")

    def update_pbarBeerRemaining1(self, BeerRemaining1):
        self.pbarBeerRemaining1.setValue(int(BeerRemaining1))

    def update_pbarBeerRemaining2(self, BeerRemaining2):
        self.pbarBeerRemaining2.setValue(int(BeerRemaining2))

    def update_pbarBeerRemaining3(self, BeerRemaining3):
        self.pbarBeerRemaining3.setValue(int(BeerRemaining3))

    def update_pbarBeerRemaining4(self, BeerRemaining4):
        self.pbarBeerRemaining4.setValue(int(BeerRemaining4))

    def update_pbarBeerRemaining5(self, BeerRemaining5):
        self.pbarBeerRemaining5.setValue(int(BeerRemaining5))

    def update_textboxLogMessage(self, textboxLogMessage):
        self.textboxLogMessage.appendPlainText(textboxLogMessage)

###############################################################################
######################## BEGIN ################################################
###############################################################################


###############################################################################
# Define Threads
###############################################################################
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
        # pwm = GPIO.PWM(self.gpio_pin, 100) # Init PWM on self.gpio_pin to 100 Hz frequency
        pwm = PWMLED(self.gpio_pin)
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
        logging.info("Opening serial port with the following settings: %s,%s", serial_port_name, str(baud))
        try:
            ser = serial.Serial(serial_port_name, baud, parity = par, stopbits = sb, bytesize = databits,timeout = to)
            time.sleep(0.2)
            c = ser.read(100)
            ser.flushOutput()
            ser.flushInput()
        except serial.SerialException as e:
            #logging.critical("Unable to open Serial Port: %s", e)
            ser = None
            self.exit.set()
            print("Closed early, serial port not initialized")
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

###############################################################################
# Serial Interface
###############################################################################

def _send_serial(ser, cmd_string):
    if ser is None:
        return

    ser.flushOutput()
    ser.flushInput()
    for c in cmd_string:
        ser.write(c)
    ser.write("\r")

def _read_serial(ser, retry_count):
    #Retry the read up to retry_count times
    #time.sleep(0.01)
    repeat_count = 0
    cmd_ok = False
    if ser is None:
        return
        buffer = ""
        while 1:
            c = ser.read(1)
            if len(c) == 0:
               if(repeat_count == retry_count):
                   break
               repeat_count = repeat_count + 1
               continue

            if c == '\r':
               cmd_ok = True
               break;

            if buffer != "" or c != ">": #if something is in buffer, add everything
               buffer = buffer + c

        if(buffer == ""):
           logging.warning("No data received from read command after %s retries", retry_count)
           return None
        logging.debug("Retry count %s", repeat_count)
        return buffer
    else:
        logging.error("NO ser.port!")
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

###############################################################################
######################## END ##################################################
###############################################################################

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", help="Debug level log output", action="store_true")
    parser.add_argument("--info", help="Info level log output", action="store_true")
    parser.add_argument("--fullscreen", help="Maximize window at startup", action="store_true")
    parser.add_argument("--autostart", help="Autostart the polling thread", action="store_true")
    args = parser.parse_args()
    if args.debug:
        print("Debug Enabled")
        logging.basicConfig(level=logging.DEBUG,format='%(asctime)s:%(levelname)s:%(message)s')
    elif args.info:
        print("Info Enabled")
        logging.basicConfig(level=logging.INFO,format='%(asctime)s:%(levelname)s:%(message)s')
    else:
        logging.basicConfig(level=logging.WARNING,format='%(asctime)s:%(levelname)s:%(message)s')

    if args.fullscreen:
        fullscreen_flag = True
    else:
        fullscreen_flag = False
    if args.autostart:
        print("Tungs working!")
        print("Autostarting polling thread")
        autostart_flag = True
    else:
        autostart_flag = False

    # Read Config File
    try:
        Config.read("config/kegs.config")
    except:
        logging.error("Unable to read config file")
        sys.exit()

    try:
        active_keg1 = ConfigSectionMap("Active")['keg1']
        active_keg2 = ConfigSectionMap("Active")['keg2']
        active_keg3 = ConfigSectionMap("Active")['keg3']
        active_keg4 = ConfigSectionMap("Active")['keg4']
        active_keg5 = ConfigSectionMap("Active")['keg5']
        print("Active Kegs: " + active_keg1 + "  " + active_keg2 + "  " + active_keg3 + " " + active_keg4 + " " + active_keg5)

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
        #tv_dict['serialport'] = ConfigSectionMap("TV")['serialport']
        #tv_dict['baudrate'] = ConfigSectionMap("TV")['buadrate']
        #tv_dict['sleeptimesec'] = ConfigSectionMap("TV")['sleeptimesec']

    except:
        logging.error("Config file error")
        sys.exit()

    # Setup the threads and queues
    keg_data1 = multiprocessing.Queue(maxsize=5)
    keg_message1 = multiprocessing.Queue(maxsize=10)
    keg_thread1 = read_keg_data(keg_data1, keg_message1, keg_dict1, 17)

    keg_data2 = multiprocessing.Queue(maxsize=5)
    keg_message2 = multiprocessing.Queue(maxsize=10)
    keg_thread2 = read_keg_data(keg_data2, keg_message2, keg_dict2, 27)

    keg_data3 = multiprocessing.Queue(maxsize=5)
    keg_message3 = multiprocessing.Queue(maxsize=10)
    keg_thread3 = read_keg_data(keg_data3, keg_message3, keg_dict3, 22)

    keg_data4 = multiprocessing.Queue(maxsize=5)
    keg_message4 = multiprocessing.Queue(maxsize=10)
    keg_thread4 = read_keg_data(keg_data4, keg_message4, keg_dict4, 23)

    keg_data5 = multiprocessing.Queue(maxsize=5)
    keg_message5 = multiprocessing.Queue(maxsize=10)
    keg_thread5 = read_keg_data(keg_data5, keg_message5, keg_dict5, 24)

    tv_message_m2t = multiprocessing.Queue(maxsize=10)
    tv_message_t2m = multiprocessing.Queue(maxsize=10)
    tv_thread = manage_tv_power(tv_message_m2t, tv_message_t2m, tv_dict)

    pb_data = multiprocessing.Queue(maxsize=5)
    pb_thread = monitor_push_button(pb_data, 25)

    temp_sensor_data = multiprocessing.Queue(maxsize=5)
    temp_sensor_thread = monitor_temp_sensor(temp_sensor_data)

    led_data = multiprocessing.Queue(maxsize=5)
    led_thread = led_control(led_data, 18)

    app = QApplication(sys.argv)
    sshFile="darkorange.stylesheet"
    with open(sshFile,"r") as fh:
        app.setStyleSheet(fh.read())
    ex = MainWindow(fullscreen_flag, autostart_flag, keg_thread1, keg_data1, keg_message1, keg_dict1,
                                                    keg_thread2, keg_data2, keg_message2, keg_dict2,
                                                    keg_thread3, keg_data3, keg_message3, keg_dict3,
                                                    keg_thread4, keg_data4, keg_message4, keg_dict4,
                                                    keg_thread5, keg_data5, keg_message5, keg_dict5,
                                                    tv_thread, tv_message_m2t, tv_message_t2m, pb_thread, pb_data, led_thread, led_data, temp_sensor_thread, temp_sensor_data)
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    try:
        exit_code = app.exec()
    finally:
        # Ensure cleanup happens even if app crashes
        print("Application closing, cleaning up...")
        ex.stop_getting_data()

    sys.exit(exit_code)

if __name__ == '__main__':
    main()

