#!/usr/bin/env python
"""********************************************************************************
RPIHomeAlarmSystem

setup i2c modules...
GPIO

packages required:
python-gdata
python-pip  
"pip install PyDispatcher"
"pip install rpyc"

Features

--- Dispatcher Signal List ---
"Alarm Message"
"Time Update Model"
"Weather Update"
"Weather Update Model"
"Fault Update"
"Fault Update Model"
"Input String Update Model"
"Alarm Message"
"Alarm Mode Update Model"
"Grace Update Model"
"Sensor Update Model"
"Reboot"
"Terminate"

********************************************************************************"""
import time
import urllib2
import json
import yaml
import sys
import string
import random
import os
import logging
import logging.handlers
import logging.config
import subprocess
import signal
import smtplib                              # Import smtplib to provide email functions
from email.mime.text import MIMEText        # Import the email modules
from Queue import Queue
import threading
from threading import Thread
from i2clcd import I2CLCD
from I2CBV4618 import I2CBV4618
import RPi.GPIO as GPIO
import atom
import gdata.calendar
import gdata.calendar.service
from pydispatch import dispatcher
import rpyc
#from alarm_model import AlarmModel
#from alarm_model import Sensor,FireSensor,MotionCamera
# This import should be fine if we keep the module clean.
from alarm_model import *
from event_serializer import EventSerializer,event_q

network_is_alive = True
lcd_init_required = False

class TimeScanner(Thread):
    """ This class scans and publishes the time in its own thread.  A "Time Update" event is generated every second. """
    #------------------------------------------------------------------------------
    def __init__(self):
        """ Init the time scanner """
        Thread.__init__(self)
        self.daemon = True
        self.model = AlarmModel.getInstance()
        self.start()

    #-------------------------------------------------------------------
    def run(self):
        logger.info("TimeScanner started")
        while True:
            h = time.localtime().tm_hour
            m = time.localtime().tm_min
            s = time.localtime().tm_sec
            self.model.update_time(h,m,s)
            time.sleep(1)


class WeatherScanner(Thread, Testable):
    """ This class scans the weather in its own thread. A "Weather Update" event is generated every 5 minutes. """

    def __init__(self):
        """ Init the weather scanner """
        Thread.__init__(self)
        Testable.__init__(self)
        self.model = AlarmModel.getInstance()
        self.daemon = True

        self.last_weather_check = None
        self.url = 'http://api.wunderground.com/api/' + alarm_config_dictionary["wunderground api key"]\
                   + "/geolookup/conditions/q/" + alarm_config_dictionary["wunderground location"] + ".json"
        #self.forecast_url = 'http://api.wunderground.com/api/' + alarm_config_dictionary["wunderground api key"] +/
        # '/geolookup/forecast/q/'+alarm_config_dictionary["wunderground location"]+'.json'
        self.start()

    def run(self):
        logger.info("WeatherScanner started")
        while True:
            self.undergoing_test.wait() #Wait if doing BIT
            if network_is_alive:
                try:
                    logger.info("Checking Weather.")
                    weather_url = urllib2.urlopen(self.url)
                    json_weather_string = weather_url.read()

                    parsed_json_weather = json.loads(json_weather_string)

                    wind_dir = parsed_json_weather['current_observation']['wind_degrees']
                    wind_kph = parsed_json_weather['current_observation']['wind_mph'] * 1.61
                    temp = parsed_json_weather['current_observation']['feelslike_c']
                    self.model.update_weather(temp, wind_dir, wind_kph)
                    self.last_weather_check = time.time()

                except:
                    logger.warning("Exception in WeatherScanner", exc_info=True)

            time.sleep(300)

    def do_BIT(self):
        super(self)
        assert self.isAlive()
        self.model.broadcast_message("Last check: " + time.strftime("%H:%M", time.localtime(self.last_weather_check)))
        time.sleep(.5)

class NetworkMonitorScanner(Thread, Testable):
    """ This class verifies the network connectivity periodically. """
    #------------------------------------------------------------------------------
    def __init__(self):
        """ Init the NetworkMonitor scanner """
        Thread.__init__(self)
        Testable.__init__(self)

        self.model = AlarmModel.getInstance()
        self.daemon = True

        self.url = 'http://74.125.228.100'
        self.start()

    #-------------------------------------------------------------------
    def run(self):
        global network_is_alive
        network_is_alive = True
        logger.info("NetworkMonitor started")
        while True:
            self.undergoing_test.wait() #Wait if doing BIT

            is_alive = self.check_connectivity(self.url)
            if not (network_is_alive == is_alive):
                network_is_alive = is_alive
                if network_is_alive:
                    msg = "internet_on"
                else:
                    msg = "internet_off"
                self.model.update_fault(self, msg)

            if network_is_alive:
                time.sleep(60)
            else:
                time.sleep(20)

    @staticmethod
    def check_connectivity(reference):
        try:
            urllib2.urlopen(reference, timeout=15)
            return True
        #except urllib2.URLError as err: pass
        except:
            pass
        return False

    def do_BIT(self):
        super(self)
        logger.info("url: " + self.url)
        self.model.broadcast_message("Inet alive: " + str(network_is_alive))
        assert self.isAlive()


class AlarmRemote(Thread, Testable):
    """ This class creates a simple thread that contains the RemoteService. """

    def __init__(self):
        Thread.__init__(self)
        Testable.__init__(self)
        self.daemon = True

        self.test_flag = Event().clear()
        dispatcher.connect(self.handle_test, signal="AlarmRemote Test", sender=dispatcher.Any, weak=False)

        self.start()

    def run(self):
        logger.info("AlarmRemote started")
        from rpyc.utils.server import ThreadedServer

        self.t = ThreadedServer(RemoteService, port=18861)
        self.t.start()

    def do_BIT(self):
        super(self)
        assert self.isAlive()
        logger.info("Ensuring RemoteService is also alive.")
        assert self.t.isAlive()
        logger.info("Testing RemoteService exposed_get_model.")
        logger.info(self.t.exposed_get_model())

        logger.info("Testing RemoteService exposed_create_event.")
        self.t.exposed_create_event("AlarmRemote Test","")
        assert self.test_flag.wait(3)   #returns True if no timeout.
        logger.info("Test signal received.")
        self.test_flag.clear()

    def handle_test(self):
        self.test_flag.set()

class RemoteService(rpyc.Service):
    """ This class uses rpyc to provide access to and control of the RPIAlarmSystem """

    def on_connect(self):
        # code that runs when a connection is created
        pass

    def on_disconnect(self):
        # code that runs when the connection has already closed
        pass

    @staticmethod
    def exposed_create_event(signal_name, msg):     # this is an exposed method
        """ This method allows the alarm_remote to generate events through the pydispatcher.  This is rather unsafe;
        it should be modified to restrict what can actually be done.
        """
        logger.info("Received remote create_event(): " + signal_name + ", msg=" + str(msg))
        event_q.put([dispatcher.send, {"signal": signal_name, "sender": dispatcher.Any, "msg": msg}])

    def exposed_set_alarm_state(self, state_name):  # this is an exposed method
        """ This method allows the alarm_remote to change the state of the AlarmModel. Again, this is rather unsafe;
        it should be modified to restrict what can actually be done.  For example, de-arming the AlarmModel should
        require the PIN.
        """
        logger.info("Received remote set_alarm_state() to state: " + state_name)
        try:
            State = getattr(sys.modules[__name__], state_name)
            AlarmModel.getInstance().alarm_mode.set_state(State())
        except:
            logger.warning("State is invalid: " + state_name)

    def exposed_get_model(self): # this is an exposed method
        """ This method simply returns an AlarmModel string containing its current state.
        """
        logger.debug("Received remote get_model().")
        return str(AlarmModel.getInstance())

###################################################################################
class AlarmController():
    """ This class is the Controller in the MVC pattern and drives all of the alarm system.
        The controller is aware of the API for the model and actively interact with it.
        It is however only able to get updates from the model by subscribing to topics
        the model publishes."""
    #------------------------------------------------------------------------------
    def __init__(self):
        #subscribe to several topics of interest (scanners)
        dispatcher.connect(self.handle_reboot_request, signal="Reboot",
                           sender=dispatcher.Any, weak=False)
        dispatcher.connect(self.handle_update_fault, signal="Fault Update", sender=dispatcher.Any,
                           weak=False) # This is required for the apcupsd support

        #create model (MVC pattern)
        self.model = AlarmModel.getInstance()

        # set the GPIO numbering system (BCM or BOARD)
        GPIO.setmode(self.model.alarm_config_dictionary["GPIO_numbering_system"])

        #create sensors
        self.sensor_map = self.model.alarm_config_dictionary["sensor_map"]

        for sensor_type in [Sensor, FireSensor, MotionCamera]:
            for sensor_config in self.sensor_map[sensor_type.__name__]:
                logger.debug("Raw sensor config: " + str(sensor_config))
                new_sensor = sensor_type(sensor_config)
                self.model.add_sensor(new_sensor)
                new_sensor.start()
        logger.info("Sensors created")

        #create GPIOViews (sirens, light, etc)
        self.output_map = self.model.alarm_config_dictionary["output_map"]
        for output_config in self.output_map:
            GPIOView(output_config)
            pass

        #create View  (MVC pattern)
        LCDView()
        SMSView()
        EmailView()
        if self.model.alarm_config_dictionary["speaker"] == "enable":
            SoundPlayerView()
        if self.model.alarm_config_dictionary["piezo"] == "enable":
            PiezoView()
            pass

        #create scanners (threads that periodically poll things)
        TimeScanner()
        KeypadScanner()
        #StdScanner(alarm_config_dictionary,self.model)
        WeatherScanner()
        NetworkMonitorScanner()
        AlarmRemote() #create the Thread that serves as a remote controller

        logger.info("AlarmController started")

    #--------------------------------------------------------------------------------
    @staticmethod
    def handle_reboot_request():
        global terminate
        terminate = True
        event_q.put([dispatcher.send, {"signal": "Terminate", "sender": dispatcher.Any, }])
        logger.warning("----- Reboot code entered. -----")

    # This is required for the apcupsd faults.
    def handle_update_fault(self, msg):
        logger.warning("Alarm Fault. msg=" + msg)
        self.model.update_fault(msg)

#####################################################################################
class KeypadScanner(Thread, Testable):
    """ This class will scan the keypad in its own thread """
    #--------------------------------------------------------------------------------
    def __init__(self, alarm_config_dictionary, model):
        """ Init the keypad scanner """
        Thread.__init__(self)
        Testable.__init__(self)

        self.daemon = True
        self.model = model

        try:
            driver = alarm_config_dictionary["I2C_driver"]
            logger.debug("I2C_driver: " + driver)
        except:
            logger.warning("KeypadScanner cannot be configured properly. ", exc_info=True)
            return

        if driver == "I2CLCD":
            self.keypad = I2CLCD
        elif driver == "I2CBV4618":
            self.keypad = I2CBV4618
        else:
            raise Exception("I2C_driver (" + driver + ") not supported: " + driver)

        self.start()    # start the thread

    #--------------------------------------------------------------------------------
    def run(self):
        """ Run the keypad scanner """
        logger.info("KeypadScanner started")
        global lcd_init_required
        while True:
            self.undergoing_test.wait() #Wait if doing BIT
            try:
                key = self.keypad.getInstance().get_key()
                if not key == '':
                    self.model.keypad_input(key)

                time.sleep(0.1)

            except Exception, err:
                #print sys.exc_info()[0]
                logger.warning("Exception in KeypadScanner", exc_info=True)
                #logger.warning("Exception in KeypadScanner")    #LCDView will take care of resetting the controller
                time.sleep(10)

    def do_BIT(self):
        super(self)
        assert self.isAlive()

###################################################################################
class SoundPlayerView(Testable):
    """ This class is responsible to play_notes the sounds. And for most bugs"""

    #------------------------------------------------------------------------------
    def __init__(self):
        Testable.__init__(self)

        self.model = AlarmModel.getInstance()
        self.script_path = self.model.script_path
        self.sound_config = self.model.alarm_config_dictionary["sounds"]

        try:
            logger.debug("button_wav: " + self.sound_config["button_wav"])
            logger.debug("alarm_wav: " + self.sound_config["alarm_wav"])
            logger.debug("grace_beeps: " + self.sound_config["grace_beeps"])
            logger.debug("grace_beeps3: " + self.sound_config["grace_beeps3"])
            logger.debug("grace_chirp: " + self.sound_config["grace_chirp"])
        except:
            logger.info("SoundPlayerView cannot be configured properly. ", exc_info=True)
            return

        self.lock = threading.RLock()

        """subscribe to several topics of interest (model)"""
        dispatcher.connect(self.play_alarm_mode, signal="Alarm Mode Update Model",
                           sender=dispatcher.Any, weak=False)
        dispatcher.connect(self.play_pin, signal="Input String Update Model",
                           sender=dispatcher.Any, weak=False)
        dispatcher.connect(self.play_grace_timer, signal="Grace Update Model",
                           sender=dispatcher.Any, weak=False)
        dispatcher.connect(self.play_sensor_change, signal="Sensor Update Model",
                           sender=dispatcher.Any, weak=False)

        logger.info("SoundPlayerView created")

    def play_sensor_change(self, msg):
        logger.debug("play_sensor_change")
        sensor = msg
        if sensor.has_sound():
            self.play_notes("grace_beeps3")

    def play_grace_timer(self, msg):
        alarm_mode = self.model.alarm_mode
        if str(alarm_mode) == "StateArming":
            if msg == self.sound_config["arming grace delay"]:
                pass
            elif msg > 10:
                self.play_notes("grace_beeps")
            else:
                self.play_notes("grace_beeps3")
        elif str(alarm_mode) == "StateDisarming":
            self.play_notes("grace_chirp")

    def play_alarm_mode(self):
        alarm_mode = self.model.alarm_mode
        logger.debug("play_alarm_mode")
        if str(alarm_mode) == "StateIdle":
            try:
                with self.lock:
                    if str(alarm_mode) == "StateAlert":
                        subprocess.call("ps x | grep '[a]play_notes' | awk '{ print $1 }' | xargs kill", shell=True)
                    self.play_notes("grace_beeps3")
            except:
                logger.warning("Error when trying to kill aplay process", exc_info=True)
        elif str(alarm_mode) == "StateAlert":
            self.play_notes("alarm_wav")
        elif str(alarm_mode) == "StatePartiallyArmed":
            self.play_notes("grace_beeps3")

    def play_pin(self, msg):
        self.play_notes("button_wav")

    def play_notes(self, string):
        with self.lock:                      # Begin critical section
            subprocess.Popen(['aplay', '-q', self.script_path + self.sound_config[string]])

    def do_BIT(self):
        super(self)
        logger.info("Playing all sound files.")
        for a_string in self.sound_config.values():
            self.model.broadcast_message("Play: " + a_string)
            subprocess.Popen(['aplay', '-q', self.script_path + a_string])
            time.sleep(1)
            subprocess.call("ps x | grep '[a]play_notes' | awk '{ print $1 }' | xargs kill", shell=True)

###################################################################################
buzzQ = Queue()

class PiezoView():
    """ This class is responsible to play_notes the sounds. And for most bugs"""
    #------------------------------------------------------------------------------
    def __init__(self):
        self.model = AlarmModel.getInstance()
        self.alarm_config = self.model.alarm_config_dictionary

        """subscribe to several topics of interest (model)"""
        dispatcher.connect(self.alarm_mode, signal="Alarm Mode Update Model",
                           sender=dispatcher.Any, weak=False)
        dispatcher.connect(self.key, signal="Input String Update Model", sender=dispatcher.Any, weak=False)
        #dispatcher.connect( self.grace_timer, signal="Grace Update Model", sender=dispatcher.Any, weak=False)
        dispatcher.connect(self.sensor_change, signal="Sensor Update Model",
                           sender=dispatcher.Any, weak=False)
        dispatcher.connect(self.exit, signal="Terminate", sender=dispatcher.Any, weak=False)

        GPIO.setup(18, GPIO.OUT)
        self.buzzer = GPIO.PWM(18, 0.5)

        self.player = BuzzPlayer(self.buzzer)

        logger.info("PiezoView created")

    def exit(self):

        self.buzzer.stop()

    def sensor_change(self, msg):
        sensor = msg
        if sensor.has_sound():
            logger.debug("PiezoView: sensor_change")
            self.player.next([self.player.play_notes, {
                "string": [[880, 50, 0.12], [880, 0, 0.1], [880, 50, 0.12], [880, 0, 0.07], [880, 50, 0.12],
                           [880, 0, 0]]}])

    def grace_timer(self, msg):
        if str(self.alarm_mode) == "StateArming":
            if msg > 10:
                self.player.next([self.player.play_notes, {"string": [[200, 50, 0.1], [200, 0, 0]]}])
            else:
                self.player.next(
                    [self.player.play_notes, {"string": [[200, 50, 0.1], [200, 0, 0.2], [200, 50, 0.1], [200, 0, 0]]}])
        else:
            self.player.next([self.player.play_notes, {"string": [[880, 50, 0.1]]}])

    def alarm_mode(self):
        self.alarm_mode = self.model.alarm_mode
        logger.debug("play_alarm_mode")

        self.player.next([self.player.stop, {}])

        if str(self.alarm_mode) == "StateAlert":
            self.player.next([self.player.play_siren, {}])
        elif str(self.alarm_mode) == "StateArming":
            self.player.next([self.player.play_continuously, {"string": [[200, 50, 0.1], [200, 0, 0.9]]}])
        elif str(self.alarm_mode) == "StateDisarming":
            self.player.next([self.player.play_continuously, {"string": [[2200, 50, 0.4], [2200, 0, 0.1]]}])
        elif str(self.alarm_mode) == "StateIdle":
            self.player.next(
                [self.player.play_notes, {"string": [[440, 50, 0.1], [440, 0, 0.05], [440, 50, 0.1], [440, 0, 0]]}])
        elif str(self.alarm_mode) == "StatePartiallyArmed":
            self.player.next([self.player.play_notes, {
                "string": [[440, 50, 0.1], [440, 0, 0.05], [503, 50, 0.1], [503, 0, 0.05], [566, 50, 0.1],
                           [566, 0, 0]]}])

    def key(self, msg):
        self.player.next([self.player.play_notes, {"string": [[200, 30, 0.03], [200, 0, 0]]}])


class BuzzPlayer(Thread):
    def __init__(self, buzzer):
        Thread.__init__(self)
        self.daemon = True

        self.buzzer = buzzer

        self.default_string = [[200, 0, 0.05]]

        self.stop()
        self.buzzer.start(0)

        self.start()

    def next(self, call):
        buzzQ.put(call)

    def run(self):
        while (True):
            try:
                [func, kwargs] = buzzQ.get(not self.is_continuous)
                func(**kwargs)
            except:
                self.play_notes(self.continuous_string)

    def play_notes(self, string):
        logger.debug("BuzzPlayer play_notes() string: " + str(string))
        for [freq, dc, d] in string:
            self.buzzer.ChangeFrequency(freq)
            self.buzzer.ChangeDutyCycle(dc)
            time.sleep(d)

    def play_continuously(self, string):
        logger.debug("BuzzPlayer play_continuously() string: " + str(string))
        self.is_continuous = True
        self.continuous_string = string

    def play_siren(self):
        logger.debug("BuzzPlayer play_siren()")
        string = []
        for y in range(0, 8000, 400):
            string.append([2500 + y, 50, 0.05])
            #for y in range(0, 8000,400):
        #	string.append([10500-y,50,0.05])
        self.play_continuously(self, string)

    def stop(self):
        logger.debug("BuzzPlayer stop()")
        self.is_continuous = False
        self.continuous_string = self.default_string
        self.play_notes(self.continuous_string)

class LCDView(Testable):
    def __init__(self):
        Testable.__init__(self)
        self.model = AlarmModel.getInstance()

        try:
            driver = self.model.alarm_config_dictionary["I2C_driver"]
        except:
            logger.info("I2C_driver not found in configuration")
            return

        if driver == "I2CLCD":
            self.driver = I2CLCD
        elif driver == "I2CBV4618":
            self.driver = I2CBV4618
        else:
            raise Exception("I2C_driver (" + driver + ") not supported: " + driver)

        try:
            self.lcd_backlight_timer_setting = self.model.alarm_config_dictionary[
                "lcd_backlight_timer"]    # Timer setting to deactivate backlight when LCD is inactive.
        except:
            self.lcd_backlight_timer_setting = 30

        try:
            self.lcd_custom_chars = self.model.alarm_config_dictionary["lcd_custom_chars"]
        except:
            logger.warning("Problem loading lcd_custom_chars", exc_info=True)

        self.lcd_backlight_timer_enabled = not (self.lcd_backlight_timer_setting == 0)
        self.lcd_backlight_current_state = False

        #Display locations
        self.time_cursor_start = [1, 1]
        self.weather_cursor_start = [1, 11]
        self.pin_cursor_start = [2, 1]
        self.msg_cursor_start = [3, 1]
        self.alarm_mode_cursor_start = [2, 15]
        self.grace_timer_cursor_start = [3, 18]
        self.sensor_cursor_start = [4, 1]
        self.fault_cursor_start = [4, 19]

        #Settings
        self.message_fade_timer = -1
        self.msg_fade_timer_setting = 5                            #Timer setting to remove a message after it is displayed.
        self.lcd_backlight_timer = self.lcd_backlight_timer_setting        #Timer to deactivate backlight when LCD is inactive.
        self.fault_char = " "
        self.current_arrow_dir = ""
        self.activity_timer_active = False

        #This is not elegant.  This table works for both I2CLCD and I2CBV4618. It should be dynamic...


        self.LCD_template = ( '######################\n' +
                              '#                    #\n' +
                              '#                    #\n' +
                              '#                    #\n' +
                              '#                    #\n' +
                              '######################\n')

        """subscribe to several topics of interest (model)"""
        dispatcher.connect(self.update_weather, signal="Weather Update Model",
                           sender=dispatcher.Any, weak=False)
        dispatcher.connect(self.update_time, signal="Time Update Model", sender=dispatcher.Any,
                           weak=False)
        dispatcher.connect(self.update_alarm_mode, signal="Alarm Mode Update Model",
                           sender=dispatcher.Any, weak=False)
        dispatcher.connect(self.update_fault, signal="Fault Update Model", sender=dispatcher.Any,
                           weak=False)
        dispatcher.connect(self.update_pin, signal="Input String Update Model",
                           sender=dispatcher.Any, weak=False)
        dispatcher.connect(self.update_msg, signal="Alarm Message", sender=dispatcher.Any,
                           weak=False)
        dispatcher.connect(self.update_sensor_state, signal="Sensor Update Model",
                           sender=dispatcher.Any, weak=False)
        dispatcher.connect(self.update_grace_timer, signal="Grace Update Model",
                           sender=dispatcher.Any, weak=False)
        dispatcher.connect(self.exit, signal="Terminate", sender=dispatcher.Any, weak=False)

        signal.signal(signal.SIGUSR1, self.update_ui_file)
        self.ui_file_path = os.path.dirname(os.path.abspath(__file__)) + "/"

        # TODO: This table should be updated so that it is not hard coded...  Once the LCD
        # is up and running, the table should be built using the lcd get_char()
        self.table = string.maketrans(
            chr(128) + chr(129) + chr(130) + chr(131) + chr(132) + chr(133) + chr(134) + chr(135) + chr(0) + chr(
                1) + chr(2) + chr(3) + chr(4) + chr(5) + chr(6) + chr(7), "                ")

        global lcd_init_required
        lcd_init_required = True

        logger.info("LCDView created")

    #-------------------------------------------------------------------
    def init_screen(self):
        global lcd_init_required
        logger.debug("Starting LCDView initialization")
        lcd_init_required = False

        try:
            self.lcd = self.driver.getInstance()
            logger.debug("LCD initialization.")
            self.lcd.init()
            logger.debug("LCD init completed.")

            logger.debug("LCD Changing custom chars...")
            self.current_arrow_dir = "SOUTH_WEST"
            self.lcd.change_custom_char(0, [128, 129, 146, 148, 152, 158, 128, 128], "arrow")

            for [index, data, symbol] in self.lcd_custom_chars:
                if not index == 0:
                    self.lcd.change_custom_char(index, data, symbol)
            #self.lcd.change_custom_char(2,[128,142,145,145,159,155,159,159],"locked")	#Currently not used
            #self.lcd.change_custom_char(7,[128,142,144,144,159,155,159,159],"unlock") #Currently not used
            logger.debug("LCD custom chars completed.")

            self.table = string.maketrans(
                self.get_char("clock") + self.get_char("door") + self.get_char("patio") + self.get_char(
                    "motion") + self.get_char("deg") + self.get_char("camera") + self.get_char("arrow"), "cDPMoCa")

            self.lcd_backlight_current_state = False    #This will force a command to be sent to turn on (in set_backlight())

            logger.debug("LCD updating current display...")
            self.draw_sensors()
            self.update_weather("")
            self.update_time()
            self.update_alarm_mode()
            self.update_msg(self.model.last_message)
            logger.debug("LCD updating current display completed.")

            logger.info("LCD initialized")

        except IOError:
            logger.warning("Exception in LCDView init_screen")
            lcd_init_required = True

    #-------------------------------------------------------------------
    def exit(self):
        try:
            self.update_msg("Rebooting...")
            dispatcher.disconnect(self.update_weather, signal="Weather Update Model",
                                  sender=dispatcher.Any, weak=False)
            dispatcher.disconnect(self.update_time, signal="Time Update Model",
                                  sender=dispatcher.Any, weak=False)
            dispatcher.disconnect(self.update_alarm_mode, signal="Alarm Mode Update Model",
                                  sender=dispatcher.Any,
                                  weak=False)
            dispatcher.disconnect(self.update_fault, signal="Fault Update Model",
                                  sender=dispatcher.Any, weak=False)
            dispatcher.disconnect(self.update_pin, signal="Input String Update Model",
                                  sender=dispatcher.Any,
                                  weak=False)
            dispatcher.disconnect(self.update_msg, signal="Alarm Message", sender=dispatcher.Any,
                                  weak=False)
            dispatcher.disconnect(self.update_sensor_state, signal="Sensor Update Model",
                                  sender=dispatcher.Any,
                                  weak=False)
            dispatcher.disconnect(self.update_grace_timer, signal="Grace Update Model",
                                  sender=dispatcher.Any,
                                  weak=False)
            dispatcher.disconnect(self.exit, signal="Terminate", sender=dispatcher.Any,
                                  weak=False)
        except IOError:
            pass

    #-------------------------------------------------------------------
    def update_ui_file_template(self, loc, s):
        [row, col] = loc
        temp_s = string.translate(s, self.table)

        start_char = 23 * row + col
        end_char = start_char + len(temp_s)

        self.LCD_template = self.LCD_template[:start_char] + temp_s + self.LCD_template[end_char:]

    def update_ui_file(self, signalnumber, frame):
        with open(self.ui_file_path + "ui_file", 'w') as ui_file:
            ui_file.write(self.LCD_template)
        signal.pause()

    #-------------------------------------------------------------------
    def send_to_lcd(self, loc, s):
        self.update_ui_file_template(loc, s)    #update the shadow copy of the lcd
        [row, col] = loc
        global lcd_init_required
        try:
            if lcd_init_required:
                self.init_screen()
            if not lcd_init_required:
                self.lcd.print_str(s, row, col)
        except (IOError):
            logger.warning("Exception in LCDView send_to_lcd")
            lcd_init_required = True

    #-------------------------------------------------------------------
    def get_char(self, symbol):
        temp = "?"
        global lcd_init_required
        try:
            if not lcd_init_required:
                temp = self.lcd.get_char(symbol)
        except (IOError, AttributeError):
            logger.warning("Exception in LCDView get_char")
            lcd_init_required = True
        return temp

    #-------------------------------------------------------------------
    def set_backlight(self, on):
        global lcd_init_required
        try:
            if not lcd_init_required:
                if not (self.lcd_backlight_current_state == on):
                    logger.debug("LCDView changing backlight to: " + str(on))
                    self.lcd.set_backlight(on)
                    self.lcd_backlight_current_state = on
        except (IOError, AttributeError):
            logger.warning("Exception in LCDView set_backlight")
            lcd_init_required = True

    #-------------------------------------------------------------------
    def update_grace_timer(self, msg):
        timer = self.model.grace_timer
        if timer <= 0:
            timer_string = "   "
        else:
            timer_string = self.get_char("clock") + "{:2}".format(timer)
        self.send_to_lcd(self.grace_timer_cursor_start, timer_string)

    #-------------------------------------------------------------------
    def draw_sensors(self):
        for sensor in self.model.sensor_list:
            self.update_sensor_state(sensor)

    #-------------------------------------------------------------------
    def update_sensor_state(self, msg):
        sensor = msg
        [row, col] = self.sensor_cursor_start
        col = col + self.model.sensor_list.index(sensor)
        #Displays the icon when it is unlocked
        if sensor.is_locked():
            sensor_string = " "
        else:
            if len(sensor.icon) == 1:
                sensor_string = sensor.icon[0]
            else:
                sensor_string = self.get_char(sensor.icon)
        self.send_to_lcd([row, col], str(sensor_string))

    #-------------------------------------------------------------------
    def update_weather(self, msg):
        [temp, wind_dir, wind_kph] = [self.model.temp_c, self.model.wind_dir, self.model.wind_kph]
        self.wind_dir_arrow(self.model.wind_dir)
        #weather_string = "{:>3}".format(int(round(float(temp),0)))+chr(self.get_char("deg"))+ "C" +chr(self.get_char("arrow"))+"{:>2.0f}".format(wind_kph)+"kh"
        weather_string = "{:>3}".format(int(round(float(temp), 0))) + self.get_char("deg") + "C" + self.get_char(
            "arrow") + "{:>2.0f}".format(wind_kph) + "kh"
        #print("formed weather string in view" + weather_string)
        self.send_to_lcd(self.weather_cursor_start, weather_string)

    #-------------------------------------------------------------------
    def update_time(self):
        [h, m, s] = [self.model.hours, self.model.minutes, self.model.seconds]
        time_string = "{:0>2}:{:0>2}".format(h, m) + " "
        self.send_to_lcd(self.time_cursor_start, time_string)

        #Remove the displayed message after the fade timer.
        if self.message_fade_timer >= 0:
            self.message_fade_timer -= 1
        if self.message_fade_timer == 0:
            self.update_msg("")

        #blink if there is a fault
        if not self.fault_char == "  ":
            if s % 2 == 0:
                self.send_to_lcd(self.fault_cursor_start, "  ")
            else:
                self.send_to_lcd(self.fault_cursor_start, self.fault_char)

        self.backlight_timer_decrease()

    #-------------------------------------------------------------------
    def update_pin(self, msg):
        a_string = "              "
        a_string = msg + a_string[len(msg):len(a_string)]
        self.send_to_lcd(self.pin_cursor_start, a_string)
        self.backlight_timer_reset()

    #-------------------------------------------------------------------
    def update_msg(self, msg):
        a_string = "                 "
        a_string = msg + a_string[len(msg):len(a_string)]
        self.send_to_lcd(self.msg_cursor_start, a_string)

        self.message_fade_timer = self.msg_fade_timer_setting

    def update_fault(self, msg):
        a_string = ""
        if self.model.fault_power:
            a_string += "!"
        else:
            a_string += " "

        if self.model.fault_network:
            a_string += "@"
        else:
            a_string += " "
        self.fault_char = a_string

        if a_string == "  ":    # This is to ensure the chars are erased from the LCD.
            self.send_to_lcd(self.fault_cursor_start, "  ")

    #-------------------------------------------------------------------
    def update_alarm_mode(self):
        alarm_mode = self.model.alarm_mode
        if str(alarm_mode) == "StateArmed":
            self.backlight_timer_active(timer_active=self.lcd_backlight_timer_enabled)
            status_str = '  AWAY'
        elif str(alarm_mode) == "StatePartiallyArmed":
            self.backlight_timer_active(timer_active=self.lcd_backlight_timer_enabled)
            status_str = '  STAY'
        elif str(alarm_mode) == "StateDisarming":
            self.backlight_timer_active(timer_active=False)
            status_str = 'DISARM'
        elif str(alarm_mode) == "StateArming":
            self.backlight_timer_active(timer_active=False)
            status_str = 'ARMING'
        elif str(alarm_mode) == "StateIdle":
            self.backlight_timer_active(timer_active=self.lcd_backlight_timer_enabled)
            status_str = '  IDLE'
        elif str(alarm_mode) == "StateAlert":
            self.backlight_timer_active(timer_active=False)
            status_str = ' ALERT'
        elif str(alarm_mode) == "StateFire":
            self.backlight_timer_active(timer_active=False)
            status_str = '  FIRE'
        else:
            status_str = "ERROR"
        logger.debug("LCDView changing state to: " + status_str)
        self.send_to_lcd(self.alarm_mode_cursor_start, status_str)
        self.update_pin(self.model.input_string)

    #-------------------------------------------------------------------
    def wind_dir_arrow(self, wind_deg):
        try:
            if not (self.current_arrow_dir == wind_deg):
                if wind_deg == "SOUTH_WEST":
                    self.lcd.change_custom_char(0, [128, 129, 146, 148, 152, 158, 128, 128], "arrow")
                elif wind_deg == "WEST":
                    self.lcd.change_custom_char(0, [128, 132, 136, 159, 136, 132, 128, 128], "arrow")
                elif wind_deg == "NORTH_WEST":
                    self.lcd.change_custom_char(0, [128, 158, 152, 148, 146, 129, 128, 128], "arrow")
                elif wind_deg == "NORTH":
                    self.lcd.change_custom_char(0, [128, 132, 142, 149, 132, 132, 128, 128], "arrow")
                elif wind_deg == "NORTH_EAST":
                    self.lcd.change_custom_char(0, [128, 143, 131, 133, 137, 144, 128, 128], "arrow")
                elif wind_deg == "EAST":
                    self.lcd.change_custom_char(0, [128, 132, 130, 159, 130, 132, 128, 128], "arrow")
                elif wind_deg == "SOUTH_EAST":
                    self.lcd.change_custom_char(0, [128, 144, 137, 133, 131, 143, 128, 128], "arrow")
                else: #SOUTH
                    self.lcd.change_custom_char(0, [128, 132, 132, 149, 142, 132, 128, 128], "arrow")
                self.current_arrow_dir = wind_deg
        except:
            logger.warning("Exception in LCDView wind_dir_arrow")
            pass

    def backlight_timer_active(self, timer_active):
        self.activity_timer_active = timer_active
        if self.activity_timer_active:
            self.backlight_timer_reset()

    def backlight_timer_decrease(self):
        if self.activity_timer_active:
            if self.lcd_backlight_timer > -1:
                self.lcd_backlight_timer -= 1
            if self.lcd_backlight_timer == 0:
                self.set_backlight(False)

    def backlight_timer_reset(self):
        if self.activity_timer_active:
            self.lcd_backlight_timer = self.lcd_backlight_timer_setting
        self.set_backlight(True)

    def do_BIT(self):
        super(self)

        # Test all arrows
        arrow_chars = self.lcd.get_char("arrow")
        for dir in ["SOUTH_WEST","WEST","NORTH_WEST","NORTH","NORTH_EAST","EAST","SOUTH_EAST"]:
            self.wind_dir_arrow(dir)
            self.update_msg(arrow_chars)
            time.sleep(.5)
        # Displaying custom chars on the LCD.
        custom_chars=""
        for [index, data, symbol] in self.lcd_custom_chars:
            custom_chars += self.lcd.get_char(symbol)
        self.update_msg(custom_chars)
        time.sleep(1)

        # Redraw everything on the LCD.
        self.draw_sensors()
        self.update_weather("")
        self.update_time()
        self.update_alarm_mode()

#####################################################################################
import tty, termios
class StdScanner(Thread):
    """ This class will scan standard in on its own thread """
    #--------------------------------------------------------------------------------
    def __init__(self, alarm_config_dictionary, model):
        """ Init the keyboard scanner """
        Thread.__init__(self)
        self.daemon = True

        self.start()    # start the thread

    #--------------------------------------------------------------------------------
    def run(self):
        """ Run the keyboard scanner """
        logger.info("StdScanner started")
        global terminate
        while (not terminate):
            try:
                key = self.get_key()
                event_q.put([dispatcher.send,
                            {"signal": "Button Pressed", "sender": dispatcher.Any, "msg": key}])
            except IOError:
                pass

    #--------------------------------------------------------------------------------
    @staticmethod
    def get_key():
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch

###################################################################################
"""
class StdView():
	def __init__(self,alarm_config_dictionary,model):
		self.model = model
		
		dispatcher.connect( self.update_weather, signal="Weather Update Model", sender=dispatcher.Any ,weak=False)
		dispatcher.connect( self.update_time, signal="Time Update Model", sender=dispatcher.Any ,weak=False)
		dispatcher.connect( self.update_alarm_mode, signal="Alarm Mode Update Model", sender=dispatcher.Any,weak=False )
		dispatcher.connect( self.update_fault, signal="Fault Update Model", sender=dispatcher.Any,weak=False)
		dispatcher.connect( self.update_PIN, signal="Input String Update Model", sender=dispatcher.Any ,weak=False)
		dispatcher.connect( self.update_msg, signal="Alarm Message", sender=dispatcher.Any ,weak=False)
		dispatcher.connect( self.update_sensor_state, signal="Sensor Update Model", sender=dispatcher.Any, weak=False)
		dispatcher.connect( self.update_grace_timer, signal="Grace Update Model", sender=dispatcher.Any, weak=False)
		dispatcher.connect( self.exit, signal="Terminate", sender=dispatcher.Any, weak=False)

		logger.info("StdView created")
	#-------------------------------------------------------------------
	def init_screen(self):
		pass
		
	#-------------------------------------------------------------------
	def exit(self):
		pass
	
	#-------------------------------------------------------------------
	def update_grace_timer(self,msg):
		timer = self.model.grace_timer
		if timer <= 0:
			timer_string = "   "
		else:
			timer_string = self.get_char("clock")+"{:2}".format(timer)	
		self.send_to_lcd(self.grace_timer_cursor_start,timer_string)		

	#-------------------------------------------------------------------
	def draw_sensors(self):
		for sensor in self.model.sensor_list:
			self.update_sensor_state(sensor)

	#-------------------------------------------------------------------
	def update_sensor_state(self,msg):
		sensor=msg
		[row,col]=self.sensor_cursor_start
		col=col+self.model.sensor_list.index(sensor)
		#Displays the icon when it is unlocked
		if sensor.is_locked():
			sensor_string = " "
		else:
			if len(sensor.icon)==1:
				sensor_string = sensor.icon[0]
			else:
				sensor_string = self.get_char(sensor.icon)
	
	#-------------------------------------------------------------------
	def update_weather(self,msg):
	
		[temp,wind_dir,wind_kph] = [self.model.temp_C,self.model.wind_dir,self.model.wind_kph]
		self.wind_dir_arrow(wind_dir)
		#weather_string = "{:>3}".format(int(round(float(temp),0)))+chr(self.get_char("deg"))+ "C" +chr(self.get_char("arrow"))+"{:>2.0f}".format(wind_kph)+"kh"
		weather_string = "{:>3}".format(int(round(float(temp),0)))+self.get_char("deg")+ "C" +self.get_char("arrow")+"{:>2.0f}".format(wind_kph)+"kh"
		#print("formed weather string in view" + weather_string)
		self.send_to_lcd(self.weather_cursor_start,weather_string)

	#-------------------------------------------------------------------
	def update_time(self):
		[h,m,s] = [self.model.hours,self.model.minutes,self.model.seconds]
		time_string = "{:0>2}:{:0>2}".format(h,m) + " "
		self.send_to_lcd(self.time_cursor_start,time_string)
		self.backlight_timer_decrease()
		
		#Remove the displayed message after the fade timer.
		if self.message_fade_timer>=0:
			self.message_fade_timer-=1
		if self.message_fade_timer==0:
			self.update_msg("")
			
		#blink if there is a fault
		if not self.fault_char==" ":
			if s%2==0:
				self.send_to_lcd(self.fault_cursor_start," ")
			else:
				self.send_to_lcd(self.fault_cursor_start,self.fault_char)

	#-------------------------------------------------------------------
	def update_PIN(self,msg):
		string = "              " 
		string = msg+string[len(msg):len(string)]
		self.send_to_lcd(self.PIN_cursor_start,string)
		self.backlight_timer_reset()

	#-------------------------------------------------------------------
	def update_msg(self,msg):
		string = "                 " 
		string = msg+string[len(msg):len(string)]
		self.send_to_lcd(self.msg_cursor_start,string)
		
		self.message_fade_timer=self.msg_fade_timer_setting
		
	def update_fault(self,msg):	
		if msg=="onbattery":
			self.fault_char="!"
		elif msg=="offbattery":
			self.fault_char=" "
			self.send_to_lcd(self.fault_cursor_start," ")
	
	#-------------------------------------------------------------------
	def update_alarm_mode(self):
		alarm_mode = self.model.alarm_mode
		if isinstance(alarm_mode, StateArmed):
			self.backlight_timer_active(timerActive=True)
			status_str='  AWAY'
		if isinstance(alarm_mode, StatePartiallyArmed):
			self.backlight_timer_active(timerActive=True)
			status_str='  STAY'
		elif isinstance(alarm_mode, StateDisarming):
			self.backlight_timer_active(timerActive=False)
			status_str='DISARM'
		elif isinstance(alarm_mode, StateArming):
			self.backlight_timer_active(timerActive=False)
			status_str='ARMING'
		elif isinstance(alarm_mode, StateIdle):
			self.backlight_timer_active(timerActive=True)
			status_str='  IDLE'
		elif isinstance(alarm_mode, StateAlert):
			self.backlight_timer_active(timerActive=False)
			status_str=' ALERT'
		elif isinstance(alarm_mode, StateFire):
			self.backlight_timer_active(timerActive=False)
			status_str='  FIRE'
		self.send_to_lcd(self.alarm_mode_cursor_start,status_str)
		self.update_PIN(self.model.input_string)
"""

calendar_q = Queue()
###################################################################################
class SMSView():
    #-------------------------------------------------------------------
    def __init__(self):
        self.model = AlarmModel.getInstance()
        alarm_config_dictionary = self.model.alarm_config_dictionary

        self.seq = 0    #sequence number used to refer to the event.  This is because the SMSView and SMSSender are on 2 threads.

        self.last_alarm_mode_event = None
        self.last_fault_event = None

        if (SMSSender(alarm_config_dictionary)).isAlive():
            dispatcher.connect(self.update_alarm_mode, signal="Alarm Mode Update Model",
                               sender=dispatcher.Any,
                               weak=False)
            dispatcher.connect(self.update_fault, signal="Fault Update Model",
                               sender=dispatcher.Any, weak=False)
            logger.info("SMSView created")
        else:
            logger.warning("SMSView not created properly.")

    def update_alarm_mode(self):
        #Update the end time of an existing event.
        if (self.last_alarm_mode_event is not None) and str(self.model.alarm_mode) == "StateIdle":
            self.update_event_end_time(self.last_alarm_mode_event)
            self.last_alarm_mode_event = None

        if str(self.model.alarm_mode) == "StateAlert":
            self.last_alarm_mode_event = self.insert_event("RPI Intrusion",
                                                           "System in Alert state\nSensor triggered: " + self.model.last_trig_sensor.name + " while in state " + str(
                                                               self.model.last_trig_state)) #sends sms
        elif str(self.model.alarm_mode) == "StateFire":
            self.last_alarm_mode_event = self.insert_event("RPI Fire",
                                                           "System in Fire state\nFire detector triggered while in state " + str(
                                                               self.model.last_trig_state)) #sends sms

    def update_fault(self, msg):
        #We only do something with Power Faults.
        if msg == "power":
            if self.model.fault_power:
                self.last_fault_event = self.insert_event("RPI_Power_Fault", "APCUPS on battery.") #sends sms
            else:
                #Update the end time of an existing event.
                if not self.last_fault_event == None:
                    self.update_event_end_time(self.last_fault_event)
                    self.last_fault_event = None

    def insert_event(self, title, message):
        if self.seq > 1000:
            self.seq = 0
        self.seq += 1
        logger.info("SMSView creating event " + str(self.seq) + " Title: " + title)
        event = gdata.calendar.CalendarEventEntry()
        event.title = atom.Title(text=title)
        event.content = atom.Content(text=message)
        event.where.append(gdata.calendar.Where(value_string="Home"))
        
        # TODO.  We need to find a more elegant way of doing this.  The event should be created with the actual time
        # it happens...  This extra 60 second is to ensure the reminder is received.
        start_time = time.strftime("%Y-%m-%dT%H:%M:%S.000-05:00", time.localtime(time.time()+60))

        when = gdata.calendar.When(start_time=start_time, end_time=start_time)
        reminder = gdata.calendar.Reminder(minutes=1, extension_attributes={"method": "sms"})
        when.reminder.append(reminder)
        event.when.append(when)

        calendar_q.put([self.seq, event])
        return self.seq

    def update_event_end_time(self, seq):
        logger.info("SMSView update requested on event: " + str(seq))
        calendar_q.put([seq, None])


class SMSSender(Thread):
    #------------------------------------------------------------------------------
    def __init__(self, alarm_config_dictionary):
        Thread.__init__(self)
        self.daemon = True
        try:
            self.user_name = alarm_config_dictionary["google_username"]
            self.password = alarm_config_dictionary["google_password"]

            self.calurl = ""
            try:
                self.calendar_string = alarm_config_dictionary["google_calendar"]
            except:
                logger.info("Problem with google_calendar in config file. Reverting to default calendar.")
                self.calendar_string = "/calendar/feeds/default/private/full"

            self.start()
        except:
            logger.warning("SMSSender could not be started: ", exc_info=True)

        self.event_dict = {}

    #-------------------------------------------------------------------
    def run(self):
        logger.info("SMSSender started")
        while (True):
            [seq, an_event] = calendar_q.get()
            action_completed = False
            while (not action_completed):
                if network_is_alive:
                    try:
                        if an_event == None:
                            logger.info("SMSSender updating event sequence " + str(seq))
                            self.update_endtime(self.event_dict[seq])
                            del self.event_dict[seq]
                        else:
                            logger.info("SMSSender creating event sequence " + str(seq))
                            self.event_dict[seq] = self.insert_event(an_event)
                        action_completed = True
                    except:
                        time.sleep(5)
                        logger.warning("An exception occurred when creating/updating a calendar event. ", exc_info=True)
                    time.sleep(.5)
                else:
                    time.sleep(4)

    def logon(self):
        self.cs = gdata.calendar.service.CalendarService()
        self.cs.email = self.user_name
        self.cs.password = self.password

        self.cs.source = "Google-Calendar-SMS-5.0_" + str(random.randint(0, 10000))
        self.cs.ProgrammaticLogin()

    #-------------------------------------------------------------------
    def insert_event(self, event):
        self.logon()
        #Added to select a specific calendar in which the event will be created.
        feed = self.cs.GetOwnCalendarsFeed()
        calurl_list = [a_calendar.content.src for i, a_calendar in enumerate(feed.entry)]
        for acalurl in calurl_list:
            if self.calendar_string in acalurl:
                self.calurl = acalurl

        if self.calurl == "":    #if the calendar string is not found, we default to the standard calendar.
            self.calurl = "/calendar/feeds/default/private/full"
            logger.debug("calendar string not found. Reverting to standard calendar")

        logger.debug("calendar url: " + self.calurl)

        link = self.calurl
        done = False
        while not done:
            try:
                new_event = self.cs.InsertEvent(event, link)
                done = True
            except gdata.service.RequestError, inst:
                link = self.handle_302(inst)
                if link == "":
                    done = True

        logger.info('New single event inserted: %s' % (new_event.id.text,))
        logger.info('\tEvent edit URL: %s' % (new_event.GetEditLink().href,))
        logger.info('\tEvent HTML URL: %s' % (new_event.GetHtmlLink().href,))

        return new_event

    def update_endtime(self, old_event):
        self.logon()

        event = self.cs.GetCalendarEventEntry(old_event.id.text)
        logger.info("Updating end time of event: " + event.title.text + " ...")

        previous_title = event.title.text
        event.title.text = previous_title + " Updated"

        #end_time = time.strftime("%Y-%m-%dT%H:%M:%S-05:00", time.localtime(time.time() + 2 * 60))
        end_time = time.strftime("%Y-%m-%dT%H:%M:%S.000-05:00", time.localtime(time.time()))

        for a_when in event.when:
            logger.info("Event.when original: ")
            logger.info("Start time: " + a_when.start_time)
            logger.info("End time: " + a_when.end_time)
            start_time = a_when.start_time
            a_when.end_time = end_time

        logger.info("Event.when updated: ")
        logger.info("Start time: " + start_time)
        logger.info("End time: " + end_time)

        link = event.GetEditLink().href
        #logger.info(str(event))
        done = False
        while not done:
            try:
                updated_event = self.cs.UpdateEvent(link, event)
                logger.info('Single event updated: %s' % (updated_event.id.text,))
                logger.info('\tEvent edit URL: %s' % (updated_event.GetEditLink().href,))
                logger.info('\tEvent HTML URL: %s' % (updated_event.GetHtmlLink().href,))
                done = True
            except gdata.service.RequestError, inst:
                link = self.handle_302(inst)
                if link == "":
                    done = True

    def handle_302(self, inst):
        response = inst[0]
        status = response['status']
        reason = response['reason']
        body = response['body']

        logger.warning("Request Error. (code=" + str(status) + ")")

        if status == 302:
            index1 = body.find("A HREF=") + 8
            index2 = body.find("\"", index1)
            link = body[index1:index2]
            logger.warning("New link: " + link)
            time.sleep(5)
            return link

        return ""


email_q = Queue()
###################################################################################
class EmailView():
    def __init__(self):
        self.model = AlarmModel.getInstance()

        if EmailSender().isAlive():
            dispatcher.connect(self.update_alarm_mode, signal="Alarm Mode Update Model",
                               sender=dispatcher.Any,
                               weak=False)
            dispatcher.connect(self.update_fault, signal="Fault Update Model",
                               sender=dispatcher.Any, weak=False)
            logger.info("EmailView created")
        else:
            logger.warning("EmailView not created properly.")

    def update_alarm_mode(self):
        if str(self.model.alarm_mode) == "StateAlert":
            self.create_email("RPI_Intrusion",
                              "Sensor triggered: " + self.model.last_trig_sensor.name + " while in state " + str(
                                  self.model.last_trig_state)) #sends sms
        elif str(self.model.alarm_mode) == "StateFire":
            self.create_email("RPI_Fire",
                              "Fire detector triggered while in state " + str(self.model.last_trig_state)) #sends sms
        elif str(self.model.alarm_mode) == "StateIdle":
            if str(self.model.alarm_mode) == "StateFire":
                self.create_email("RPI_Fire", "Fire alarm off.") #sends sms

    def update_fault(self, msg):
        if (msg == "power"):
            if self.model.fault_power:
                self.create_email("RPI_Power_Fault", "APCUPS on battery.") #sends sms
            else:
                self.create_email("RPI_Power_Recovered", "APCUPS off battery.") #sends sms

    def create_email(self, subject, message):
        # Construct email
        email_q.put([subject, message])


class EmailSender(Thread):
    #------------------------------------------------------------------------------
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        alarm_config_dictionary = AlarmModel.getInstance().alarm_config_dictionary
        try:
            # This is the SMTP server, username and password required to send email through your internet service provider
            self.smtp_server = alarm_config_dictionary["smtp_server"]
            self.smtp_user = alarm_config_dictionary["smtp_user"]
            self.smtp_pass = alarm_config_dictionary["smtp_pass"]
            self.addr_list = alarm_config_dictionary["addr_list"]
            self.start()
        except:
            logger.warning("EmailSender could not be started: ", exc_info=True)

    #-------------------------------------------------------------------
    def run(self):
        logger.info("EmailSender started")
        while (True):
            [subj, message] = email_q.get()
            email_sent = False
            while (not email_sent):
                if network_is_alive:
                    try:
                        self.send_email(subj, message)
                        email_sent = True
                        logger.info("An email was sent. Subject: " + subj + ", Message: " + message)
                    except:
                        logger.warning("An exception occured while sending an email. ", exc_info=True)
                    time.sleep(0.5)
                else:
                    time.sleep(4)

    def send_email(self, subj, message):
        msg = MIMEText(message)
        msg['To'] = ", ".join(self.addr_list)
        msg['From'] = self.smtp_user
        msg['Subject'] = subj
        # Send the message via an SMTP server
        s = smtplib.SMTP(self.smtp_server + ':587')
        s.ehlo()
        s.starttls()
        s.login(self.smtp_user, self.smtp_pass)
        s.sendmail(self.smtp_user, self.addr_list, msg.as_string())
        s.quit()

###################################################################################		
class GPIOView(Testable):
    #-------------------------------------------------------------------
    def __init__(self, output_config):
        Testable.__init__(self)

        self.model = AlarmModel.getInstance()
        [self.pin, self.name, normal_pin_value, self.states_on, self.states_from] = output_config

        """  This code has been removed since the comparison between states is done through str()
        self.states_on = []
        for astate in states_on:
            self.states_on.append(getattr(sys.modules[__name__], astate))
            logger.debug("State ON: " + astate + " added to GPIOView: " + self.name)

        self.states_from = []
        """
        self.states_from_any = False
        self.active = False
        for astate in self.states_from:
            if astate == "ANY":
                self.states_from_any = True
            """
            else:
                self.states_from.append(getattr(sys.modules[__name__], astate))
                logger.debug("State from: " + astate + " added to GPIOView: " + self.name)
            """
        if normal_pin_value == "normally_low":
            self.normal_pin_value = False
        elif normal_pin_value == "normally_high":
            self.normal_pin_value = True
        else:
            raise Exception("Invalid string: " + normal_pin_value)

        GPIO.setup(self.pin, GPIO.OUT, initial=self.normal_pin_value)

        dispatcher.connect(self.update_alarm_mode, signal="Alarm Mode Update Model",
                           sender=dispatcher.Any, weak=False)
        logger.info("GPIOView (" + self.name + ") created")

    def update_alarm_mode(self):
        if (str(self.model.alarm_mode) in self.states_on) and self.is_active_from_state(
                self.model.last_trig_state):
            if GPIO.input(self.pin) == self.normal_pin_value:
                logger.info("Output turned on: " + self.name)
                self.active = True
                GPIO.output(self.pin, self.normal_pin_value ^ 1)
        else:
            if not GPIO.input(self.pin) == self.normal_pin_value:
                logger.info("Output turned off: " + self.name)
                self.active = False
                GPIO.output(self.pin, self.normal_pin_value)

    def is_active_from_state(self, state):
        if self.states_from_any:
            return True
        return state in self.states_from

    def do_BIT(self):
        super(self)
        # Save current state
        saved_output = GPIO.input(self.pin)

        self.model.broadcast_message("Output " + self.name)
        GPIO.output(self.pin, self.normal_pin_value ^ 1)
        time.sleep(.5)
        GPIO.output(self.pin, self.normal_pin_value)
        time.sleep(1)
        GPIO.output(self.pin, self.normal_pin_value ^ 1)
        time.sleep(.5)
        GPIO.output(self.pin, self.normal_pin_value)

        # Reset to save value to ensure is is left in the same state
        GPIO.output(self.pin, saved_output)

# Run the program
if __name__ == "__main__":
    global terminate
    terminate = False

    GPIO.setwarnings(False)

    # create logger
    try:
        logging.config.fileConfig('logging.conf')
        logger = logging.getLogger('alarm')
    except:
        print >> sys.stderr, 'File logging.conf not found or contains errors. Logging disabled.'
        logger = logging.getLogger('alarm')
        logger.addHandler(logging.NullHandler())

    logger.info(
        "------------------------------------------- Logger Started -------------------------------------------")

    logger.debug("Starting Event Serializer")
    EventSerializer.getInstance()
    logger.debug("Starting AlarmController")
    AlarmController()
    logger.info("----- Initialization complete -----")

    while threading.active_count() > 0 and not terminate:
        time.sleep(0.1)

    time.sleep(2)
    GPIO.cleanup()

    subprocess.call("shutdown -r now", shell=True)
