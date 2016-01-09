from pydispatch import dispatcher
import logging
from singletonmixin import Singleton
from event_serializer import event_q
import os
import sys
import yaml
import time
from threading import RLock, Thread, Event
import RPi.GPIO as GPIO

class Testable():
    def __init__(self):
        self.BITServer = BuiltInTest.getInstance()
        self.BITServer.register(self)
        self.not_undergoing_BIT = self.BITServer.not_undergoing_BIT

        # The execution of the BIT could be done using the dispatcher.  However, there is no real benefit.
        # dispatcher.connect(self.do_BIT, signal="BIT", sender=dispatcher.Any, weak=False)

    def handle_system_BIT_started(self):
        pass

    def handle_system_BIT_stopped(self):
        pass

    def do_BIT(self):
        logging.info("C:" + self.__class__.__name__)
        time.sleep(1)

class BuiltInTest(Thread, Singleton):
    def __init__(self):
        Thread.__init__(self)
        self.testable_list = []

        self.start_BIT_command = Event()
        self.start_BIT_command.clear()
        self.not_undergoing_BIT = Event()
        self.not_undergoing_BIT.set()

        self.state_change_event = Event()
        self.state_change_event.clear()

        self.model = AlarmModel.getInstance()
        self.daemon = True

        dispatcher.connect(self.update_alarm_mode, signal="Alarm Mode Update Model",
                           sender=dispatcher.Any, weak=False)

        self.start()

    def register(self, testable_objet):
        self.testable_list.append(testable_objet)

    def run_component_BIT(self,component_type_string):
        self.not_undergoing_BIT.clear()
        for component in self.testable_list:
                if component.__class__.__name__ == component_type_string:
                    component.do_BIT()
        self.not_undergoing_BIT.set()

    def run_BIT(self):
        self.start_BIT_command.set()

    def run(self):
        while True:
            self.start_BIT_command.wait()

            self.model.broadcast_message("Starting BIT")

            # Output the config
            self.model.broadcast_message("Dumping config")
            logger.info(yaml.dump(self.model.alarm_config_dictionary))
            time.sleep(1)

            # Output the AlarmModel
            self.model.broadcast_message("Dumping model")
            logger.info(str(self.model))
            time.sleep(1)

            # Flags all testable objects that the test is ongoing.  The testable object should wait.
            self.not_undergoing_BIT.clear()

            try:
                # This is the modular/component testing.  The AlarmModel is in StateBIT which prevents state changes.
                self.model.alarm_mode.set_state(StateBIT())
                self.model.broadcast_message("Components Tests")
                time.sleep(1)
                # Run BIT on all testable objects
                for an_object in self.testable_list:
                    an_object.do_BIT()

                # This is the system level testing.  The AlarmModel the system changes states as per normal operation.
                self.model.broadcast_message("System Tests")
                self.model.alarm_mode.set_state(StateIdle())
                time.sleep(1)

                ########## Test Case ##########
                # Trigger Fire sensor.
                self.model.broadcast_message("TC: Fire")
                self.reset_alarm_mode_wait()
                sensor = self.force_sensor(FireSensor)
                if not sensor == None:
                    self.wait_for_alarm_mode()
                    assert isinstance(self.model.alarm_mode, StateFire)
                    time.sleep(2)
                    self.reset_alarm_mode_wait()
                    sensor.cancel_forced_reading()
                    self.wait_for_alarm_mode()
                    assert isinstance(self.model.alarm_mode, StateIdle)
                time.sleep(5)

                ########## Test Case ##########
                # Trigger intrusion (with grace) while in StatePartiallyArmed
                self.model.broadcast_message("TC: Intrusion 1")
                time.sleep(2)
                self.reset_alarm_mode_wait()
                self.model.function_partial_arm()
                self.wait_for_alarm_mode()
                assert isinstance(self.model.alarm_mode, StatePartiallyArmed)
                self.reset_alarm_mode_wait()
                sensor = self.force_sensor(Sensor, True)
                if not sensor == None:
                    self.wait_for_alarm_mode()
                    assert isinstance(self.model.alarm_mode, StateDisarming)
                    self.reset_alarm_mode_wait()
                    self.model.grace_timer = 0      # forcing the grace to 0
                    self.model.update_time(self.model.hours, self.model.minutes, self.model.seconds)    # TIC
                    self.wait_for_alarm_mode()
                    assert isinstance(self.model.alarm_mode, StateAlert)
                    sensor.cancel_forced_reading()
                # Simulate entering PIN to disarm.
                self.reset_alarm_mode_wait()
                self.model.function_arm()
                self.wait_for_alarm_mode()
                assert isinstance(self.model.alarm_mode, StateIdle)
                time.sleep(5)

                ########## Test Case ##########
                # Trigger intrusion (without grace) while in StatePartiallyArmed
                self.model.broadcast_message("TC: Intrusion 2")
                time.sleep(2)
                self.reset_alarm_mode_wait()
                self.model.function_partial_arm()
                self.wait_for_alarm_mode()
                assert isinstance(self.model.alarm_mode, StatePartiallyArmed)
                self.reset_alarm_mode_wait()
                sensor = self.force_sensor(Sensor, False)
                if not sensor == None:
                    self.wait_for_alarm_mode()
                    assert isinstance(self.model.alarm_mode, StateAlert)
                    sensor.cancel_forced_reading()
                # Simulate entering PIN to disarm.
                self.reset_alarm_mode_wait()
                self.model.function_arm()
                self.wait_for_alarm_mode()
                assert isinstance(self.model.alarm_mode, StateIdle)
                time.sleep(5)

                ########## Test Case ##########
                # Trigger intrusion (with grace) while in StateArmed
                self.model.broadcast_message("TC: Intrusion 3")
                time.sleep(2)
                self.reset_alarm_mode_wait()
                self.model.function_arm()
                self.wait_for_alarm_mode()
                assert isinstance(self.model.alarm_mode, StateArming)
                self.reset_alarm_mode_wait()
                self.model.grace_timer = 0      # forcing the grace to 0
                self.model.update_time(self.model.hours, self.model.minutes, self.model.seconds)    # TIC
                self.wait_for_alarm_mode()
                assert isinstance(self.model.alarm_mode, StateArmed)
                self.reset_alarm_mode_wait()
                sensor = self.force_sensor(Sensor, True)
                if not sensor == None:
                    self.wait_for_alarm_mode()
                    assert isinstance(self.model.alarm_mode, StateDisarming)
                    self.reset_alarm_mode_wait()
                    self.model.grace_timer = 0      # forcing the grace to 0
                    self.model.update_time(self.model.hours, self.model.minutes, self.model.seconds)    # TIC
                    self.wait_for_alarm_mode()
                    assert isinstance(self.model.alarm_mode, StateAlert)
                    sensor.cancel_forced_reading()
                # Simulate entering PIN to disarm.
                self.reset_alarm_mode_wait()
                self.model.function_arm()
                self.wait_for_alarm_mode()
                assert isinstance(self.model.alarm_mode, StateIdle)
                time.sleep(5)

                ########## Test Case ##########
                # Trigger intrusion (with grace) while in StateArmed
                self.model.broadcast_message("TC: Intrusion 4")
                time.sleep(2)
                self.reset_alarm_mode_wait()
                self.model.function_arm()
                self.wait_for_alarm_mode()
                assert isinstance(self.model.alarm_mode, StateArming)
                self.reset_alarm_mode_wait()
                self.model.grace_timer = 0      # forcing the grace to 0
                self.model.update_time(self.model.hours, self.model.minutes, self.model.seconds)    # TIC
                self.wait_for_alarm_mode()
                assert isinstance(self.model.alarm_mode, StateArmed)
                self.reset_alarm_mode_wait()
                sensor = self.force_sensor(Sensor, False)
                if not sensor == None:
                    self.wait_for_alarm_mode()
                    assert isinstance(self.model.alarm_mode, StateAlert)
                    sensor.cancel_forced_reading()
                # Simulate entering PIN to disarm.
                self.reset_alarm_mode_wait()
                self.model.function_arm()
                self.wait_for_alarm_mode()
                assert isinstance(self.model.alarm_mode, StateIdle)
                time.sleep(1)
                self.model.broadcast_message("BIT Success")
            except:
                self.model.broadcast_message("BIT Failed")
                logger.warning("Exception while running BIT.", exc_info=True)

            self.not_undergoing_BIT.set()   # This restarts all the threads.
            self.start_BIT_command.clear()

    def force_sensor(self, sensor_type, has_grace=False):
        for sensor in self.model.sensor_list:
            if type(sensor) == sensor_type and sensor.is_armed() and has_grace == (sensor.get_disarming_grace() > 0):
                sensor.force_reading(0)    # unlock the sensor.
                return sensor
        return None

    def update_alarm_mode(self):
        self.state_change_event.set()

    def wait_for_alarm_mode(self):
        self.state_change_event.wait(10)
        self.reset_alarm_mode_wait()

    def reset_alarm_mode_wait(self):
        self.state_change_event.clear()

class AbstractSensor(Thread, Testable):
    """ This class represents an abstract sensor.
    """
    def __init__(self, config):
        Thread.__init__(self)
        Testable.__init__(self)

        self.daemon = True
        self.sensor_mutex = RLock()

        self.model = AlarmModel.getInstance()

        self.name = config["name"]
        self.icon = config["icon"]
        self.polling_period = config["polling_period"] / 1000.0    #convert to seconds.
        armed_states = config["armed_states"]
        disarming_setting = config["disarming_setting"]
        self.play_sound = config["play_sound"]

        #Create a list of actual State classes
        self.armed_states = []
        self.armed_states_all = False
        for state_name in armed_states:
            if state_name == "ANY":
                self.armed_states_all = True
            else:
                self.armed_states.append(getattr(sys.modules[__name__], state_name))

        if disarming_setting == 1:    #default value ("disarming grace delay")
            self._disarming_grace = self.model.disarming_grace_time
        else:
            self._disarming_grace = disarming_setting

        #These variable just need to be initialized...
        self._current_reading = 1       #current valid sensor reading
        self._last_reading = 1          #previous valid sensor reading

        dispatcher.connect(self.exit, signal="Terminate", sender=dispatcher.Any, weak=False)
        self.keep_alive = True

    def __str__(self):
        return self.__class__.__name__ + "(" + self.name + ", polling_period: " + str(self.polling_period) + ", locked: " + \
               str(self.is_locked()) + ", armed: " + str(self.is_armed()) + ", grace: " + str(self._disarming_grace)

    def run(self):
        logger.info("Started: " + str(self))
        while (self.keep_alive):
            self.not_undergoing_BIT.wait() #Wait if doing BIT
            self.execute()
            if self.has_changed():
                if not self.is_locked():
                    lvl = logging.DEBUG
                    if self.model.is_armed():
                        lvl = logging.INFO
                    if self.is_armed():
                        if self.get_disarming_grace() == 0:
                            lvl = logging.CRITICAL
                        else:
                            lvl = logging.WARNING
                    logger.log(lvl,"Unlocked: " + str(self))
                self.model.update_sensor(self)
            time.sleep(self.polling_period)

    def exit(self):
        self.keep_alive = False

    def _set_reading(self, reading):
        with self.sensor_mutex:
            self._last_reading = self._current_reading
            self._current_reading = reading

    def get_reading(self):
        with self.sensor_mutex:
            return self._current_reading

    def has_changed(self):
        return not (self._current_reading == self._last_reading)

    # This is the hook that gets polled.  It should hold the code to read the value if required.
    def execute(self):
        pass

    def is_locked(self):
        return self._current_reading

    def is_armed(self, state_type=None):
        # by default, we return the value based on the current model state.
        if state_type == None:
            state_type = self.model.alarm_mode.__class__

        # the sensors are never armed when in the StateBIT.  (However, this is redundant since StateBIT does not do
        # anything. It has been coded for completeness in case the code evolves later...)
        if state_type == StateBIT:
             return False

        # if this sensor is always armed (eg. Smoke Detector)
        if self.armed_states_all:
            return True

        for astate in self.armed_states:
            if state_type == astate:
                return True
        return False

    def has_sound(self):
        return self.play_sound

    def get_disarming_grace(self):
        return self._disarming_grace

    def force_reading(self, value):
        self.saved_reading = self._current_reading
        self._current_reading = value
        self.model.update_sensor(self)   # update the model.

    def cancel_forced_reading(self):
        self._current_reading = self.saved_reading
        self.model.update_sensor(self)   # update the model.

    def do_BIT(self):
        Testable.do_BIT(self)

        self.model.broadcast_message(self.name)
        self.force_reading(0)   #unlock
        time.sleep(1.5)

        # Reset to save value to ensure is is left in the same state
        self.cancel_forced_reading()

class Sensor(AbstractSensor):
    """ This class represents a sensor.
    """
    def __init__(self, config):
        AbstractSensor.__init__(self, config)

        self.pin = config["pin"]
        self.pin_mode = config["pin_mode"]
        self.normally_closed = config["normally_closed"]

        self._previous_raw_reading = 0  #previous raw reading used for de-bouncing purposes and determine validity
        self.setup()

    def __str__(self):
        return AbstractSensor.__str__(self) + ", pin(mode): " + str(self.pin) + "(" + str(self.pin_mode) + \
               ") , normally closed: " + str(self._is_normally_closed()) + ")"

    def setup(self):
        try:
            temp_mode = GPIO.PUD_UP
            if self.pin_mode == "PULLUP":
                temp_mode = GPIO.PUD_UP
            elif self.pin_mode == "FLOATING":
                temp_mode = GPIO.PUD_UP
            elif self.pin_mode == "PULLDOWN":
                temp_mode = GPIO.PUD_DOWN
            else:
                assert False #invalid option
            GPIO.setup(int(self.pin), GPIO.IN, pull_up_down=temp_mode)
        except:
            logger.warning("Exception while setting a Sensor.", exc_info=True)

        self.execute() #initialize the value to the current reading

    def execute(self):
        with self.sensor_mutex:
            try:
                raw_reading = GPIO.input(int(self.pin))

                if raw_reading == self._previous_raw_reading:
                    self._set_reading(self.convert_raw(raw_reading))
                else:
                    self._set_reading(self.get_reading())   # The reading stays the same.  We have to call _set_reading
                                                            # in order to ensure has_changed() is functioning properly.
                self._previous_raw_reading = raw_reading
            except:
                logger.warning("Exception while reading a Sensor.", exc_info=True)

    def convert_raw(self, reading):
        # Convert for pin mode
        tmp = reading   # assuming "PULLUP"
        if self.pin_mode == "FLOATING":
            tmp = 1 - reading
        elif self.pin_mode == "PULLDOWN":
            tmp = 1 - reading

        # Convert for normally opened or closed.
        if self._is_normally_closed():
            return 1 - tmp
        else:    #normally_opened
            return tmp

    def _is_normally_closed(self):
        return self.normally_closed

class IntrusionSensor(Sensor):
    pass

class FireSensor(Sensor):
    def __init__(self, config):
        config["armed_states"] = ["ANY"]
        config["disarming_setting"] = 0
        Sensor.__init__(self, config)


class MotionCamera(AbstractSensor):
    """ This class represents a Motion Camera (eg. webcam).
    """
    def __init__(self, config):
        AbstractSensor.__init__(self, config)

        dispatcher.connect(self.handle_event, signal=self.name+" Event", sender=dispatcher.Any,
                           weak=False)
        self.motion_activity_timer = 0
        self.MOTION_ACTIVITY_TIMER_SETTING = 4

    def __str__(self):
        return AbstractSensor.__str__(self) + ", MOTION_ACTIVITY_TIMER_SETTING=" + \
               str(self.MOTION_ACTIVITY_TIMER_SETTING) + ")"

    # possible event: event_start | event_end | motion_detected
    def handle_event(self, msg):
        logger.debug(self.name + " receiving event " + msg)
        if msg == "motion_detected":
            with self.sensor_mutex:
                self.motion_activity_timer = self.MOTION_ACTIVITY_TIMER_SETTING

    def execute(self):
        #Reading of the Motion sensor is always locked unless motion was recently detected.
        if self.motion_activity_timer == 0:
            with self.sensor_mutex:
                self._set_reading(1)    #The reading returns to false after the set inactivity period.

        #Decreases the timer when motion was recently detected.
        if self.motion_activity_timer > 0:
            self._set_reading(0)        # Call to propagate the unlocked reading to _last_reading to ensure the
                                        # has_changed() return is accurate.
            self.motion_activity_timer -= 1

class AlarmModel(Singleton):
    """ This class is the Model in the MVC pattern and contains all the info for
    the alarm system. The model is not aware of any API and only communicates
    updates via publishing.
    """
    alarm_mode = None

    def __init__(self):
        self.transition_mutex = RLock()

        global logger
        logger = logging.getLogger('model')

        self.alarm_config_dictionary = self.get_config()

        logger.debug("Loading AlarmModel grace timers")
        self.arming_grace_time =  self.alarm_config_dictionary[
            "arming grace delay"]  # this is the grace period for the system to arm
        self.disarming_grace_time =  self.alarm_config_dictionary[
            "disarming grace delay"]  # this is the grace period for the system to go into alert mode
        self.grace_timer = self.arming_grace_time
        self.fire_hush_setting = self.alarm_config_dictionary["fire_hush_setting"]

        self.last_trig_sensor = None
        self.last_trig_state = None

        self.last_weather_check = None
        self.parsed_json_weather = None
        self.parsed_json_forecast = None
        self.temp_c = "0.0"
        self.wind_deg = 0
        self.wind_dir = ""
        self.wind_kph = 0.0

        self.hours = 0
        self.minutes = 0
        self.seconds = 0

        logger.debug("Loading AlarmModel PINs")
        self.pin = str(self.alarm_config_dictionary["pin"])
        self.guest_pin = str(self.alarm_config_dictionary["guest_pin"])

        self.script_path = ""

        self.fault_power = False
        self.fault_network = False

        self.input_string = ""
        self.display_string = ""
        self.last_message = ""

        self.input_activity = 0
        self.input_activity_setting = 4

        self.sensor_list = []

        logger.debug("Loading functions strings.")
        self.function_dict = self.alarm_config_dictionary["functions"]

        logger.debug("Initializing AlarmModel state.")
        AbstractState.model = self
        AbstractState().set_state(StateIdle())

        self.time_started = time.time()
        logger.info("AlarmModel initialized")

    def get_config(self):
        #read configuration file
        self.script_path = os.path.dirname(os.path.abspath(__file__)) + "/"
        logger.info('script_path ' + self.script_path)

        logger.debug("----- Loading YAML config file (alarm_config.yaml) -----")
        try:
            alarm_config_file = open(self.script_path + "../../alarm_config.yaml", 'r')
            alarm_config_dictionary = yaml.load(alarm_config_file)
            logger.debug("YAML config file loaded succesfully")
            alarm_config_file.close()
            return alarm_config_dictionary
        except:
            logger.warning("Error while reading YAML config file.", exc_info=True)
        return None

    def __str__(self):
        model_string = "AlarmModel:\n"
        model_string += "Started Time: " + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.time_started)) + "\n"
        model_string += "Current Time: {:0>2}:{:0>2}".format(self.hours, self.minutes) + "\n"
        model_string += "Last weather update: " + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.last_weather_check)) + "\n"
        model_string += "Temperature: " + str(self.temp_c) + "\n"
        model_string += "Wind direction: " + str(self.wind_dir) + " (" + str(self.wind_deg) + "deg) \n"
        model_string += "Wind speed: " + str(self.wind_kph) + "\n"
        model_string += "Current State: " + str(self.alarm_mode) + "\n"
        model_string += "Last sensor triggered: " + str(self.last_trig_sensor) + " when in state: " + str(
            self.last_trig_state) + "\n"
        model_string += "Current Input String: " + self.input_string + "\n"
        model_string += "Last broadcasted message: " + self.last_message + "\n"
        model_string += "Power Fault: " + str(self.fault_power) + "\n"
        model_string += "Network Fault: " + str(self.fault_network) + "\n"
        model_string += "Sensors armed in StatePartiallyArmed:"
        for sensor in self.sensor_list:
            if sensor.is_armed(StatePartiallyArmed):
                model_string += " " + sensor.name
        model_string += "\n"
        model_string += "Sensors armed in StateArmed: "
        for sensor in self.sensor_list:
            if sensor.is_armed(StateArmed):
                model_string += " " + sensor.name
        model_string += "\n"
        model_string += "Sensors state: \n"
        model_string += self.print_sensors_state()

        return model_string

    #-------------------------------------------------------------------
    def keypad_input(self, key):
        # TODO:
        # Guest PIN
        # Print System's uptime
        # Display last events
        # Initiate BIT

        # System tic.  This is used to reset the input string after a set delay (self.input_activity_setting).
        if key == "":
            if self.input_activity > 0:
                self.input_activity -= 1
                if self.input_activity == 0:
                    self.input_string = ""
                    self.display_string = ""
                    event_q.put([dispatcher.send,
                                {"signal": "Input String Update Model", "sender": dispatcher.Any,
                                 "msg": self.display_string}])
            return

        self.input_activity = self.input_activity_setting

        # Function key.  They should be part of StateIdle
        if key == "*":
            if self.function_dict.has_key(self.input_string):
                function = self.function_dict[self.input_string]
                logger.debug("Function key pressed. Input string: " + self.input_string + ", function: " + function)
                self.alarm_function_call(function)
                self.input_string = ""
                self.display_string = ""
        # Input_string reset
        elif key == "#":
            self.input_string = ""
            self.display_string = ""
        # Append the key to the input_string
        else:
            if len(self.input_string) == len(self.pin):
                self.input_string = self.input_string[1:]
            else:
                self.display_string += "*"
            self.input_string += key
        logger.debug("Input string: " + self.input_string)

        event_q.put([dispatcher.send, {"signal": "Input String Update Model", "sender": dispatcher.Any,
                     "msg": self.display_string}])

        # Check if the input_string matches the pin
        if self.input_string == self.pin or self.input_string == self.guest_pin:
            self.broadcast_message("PIN entered.")
            self.input_string = ""
            self.display_string = ""
            self.function_arm()

    def alarm_function_call(self,function_string):
        function_string = "function_"+function_string
        return getattr(self, function_string)()

    def alarm_state_machine(self, event_type, sensor=None):
        # Ensure no race condition while execution a transition of the state machine
        with self.transition_mutex:
            self.alarm_mode.handle_event(event_type, sensor)

    def set_grace_timer(self, t):
        self.grace_timer = t
        event_q.put(
            [dispatcher.send,
             {"signal": "Grace Update Model", "sender": dispatcher.Any, "msg": self.grace_timer}])

    #-------------------------------------------------------------------
    def update_weather(self, temp_c, wind_deg, wind_kph):
        self.temp_c = temp_c
        self.wind_kph = wind_kph
        self.wind_deg = wind_deg
        if 23 <= wind_deg < 68:        #SOUTH_WEST
            self.wind_dir = "SOUTH_WEST"
        elif 68 <= wind_deg < 113:        #WEST
            self.wind_dir = "WEST"
        elif 113 <= wind_deg < 158:    #NORTH_WEST
            self.wind_dir = "NORTH_WEST"
        elif 158 <= wind_deg < 203:    #NORTH
            self.wind_dir = "NORTH"
        elif 203 <= wind_deg < 248:        #NORTH_EAST
            self.wind_dir = "NORTH_EAST"
        elif 248 <= wind_deg < 293:        #EAST
            self.wind_dir = "EAST"
        elif 293 <= wind_deg < 338:        #SOUTH_EAST
            self.wind_dir = "SOUTH_EAST"
        else:                            #SOUTH
            self.wind_dir = "SOUTH"
        event_q.put([dispatcher.send, {"signal": "Weather Update Model", "sender": dispatcher.Any,
                                      "msg": [self.temp_c, self.wind_dir, self.wind_kph]}])

    def update_fault(self, msg):
        logger.warning("Alarm Fault. msg=" + msg)
        if msg == "onbattery":
            self.fault_power = True
            fault_type = "power"
        elif msg == "offbattery":
            self.fault_power = False
            fault_type = "power"
        elif msg == "internet_on":
            self.fault_network = False
            fault_type = "network"
        elif msg == "internet_off":
            self.fault_network = True
            fault_type = "network"
        else:
            fault_type = "unknown"

        event_q.put([dispatcher.send, {"signal": "Fault Update Model", "sender": dispatcher.Any, "msg": fault_type}])

    #-------------------------------------------------------------------
    def update_time(self, h, m, s):
        self.hours = h
        self.minutes = m
        self.seconds = s

        self.keypad_input("")  # This call is a "tic" for the keypad which is used to reset the input_string.
        self.alarm_state_machine("tic")

        event_q.put([dispatcher.send, {"signal": "Time Update Model", "sender": dispatcher.Any}])

    #-------------------------------------------------------------------
    def add_sensor(self, sensor):
        """ Adds a sensor to the model."""
        self.sensor_list.append(sensor)

    #-------------------------------------------------------------------
    def update_sensor(self, sensor):
        if isinstance(sensor,FireSensor):
            self.alarm_state_machine("fire", sensor)
        else:
            self.alarm_state_machine("sensor", sensor)
        event_q.put([dispatcher.send,
                    {"signal": "Sensor Update Model", "sender": dispatcher.Any, "msg": sensor}])

    def is_armed(self):
        # Should be pushed in the state class. Replace with a call like this (once the states have been redesigned):
        # self.alarm_mode.is_armed()

        if isinstance(self.alarm_mode, StatePartiallyArmed) or isinstance(self.alarm_mode, StateArmed):
            return True
        return False

    def check_sensors_locked(self, state=None, sensor_type=AbstractSensor):
        # Verifies if all armed sensors are locked.
        # The verification is done in the current alarm_mode by default unless specified otherwise
        if state is None:
            state = self.alarm_mode
        for sensor in self.sensor_list:
            if sensor.is_armed(state) and not sensor.is_locked():
                if isinstance(sensor, sensor_type):
                    return False
        return True

    def print_sensors_state(self):
        """ Returns a string containing the current state of all sensors. """
        sensor_state_string = ""
        for sensor in self.sensor_list:
            sensor_state_string += str(sensor) + "\n"
        return sensor_state_string

    def broadcast_message(self, msg):
        logger.info("Alarm Message: " + msg)
        self.last_message = msg
        event_q.put(
            [dispatcher.send, {"signal": "Alarm Message", "sender": dispatcher.Any, "msg": msg}])

    # Belongs to the StateIdle
    def function_arm(self):
        self.alarm_state_machine("PIN")
        return 1

    # Belongs to the StateIdle
    def function_reboot(self):
        event_q.put([dispatcher.send, {"signal": "Terminate", "sender": dispatcher.Any, }])
        logger.warning("----- Terminate Signal Sent. -----")
        return 1

    # Belongs to the StateIdle
    def function_partial_arm(self):
        self.alarm_state_machine("*")
        return 1

    def function_status(self):
        return str(self)

    # Belongs to the StateIdle
    def function_delayed_partial_arm(self):
        pass
        return 1

    # Belongs to all states.  Or maybe all but StateArmed and StateDisarming
    def function_fire_hush(self):
        pass
        return 1

    # Belongs to the StateIdle
    def function_built_in_test(self):
        if isinstance(self.alarm_mode, StateIdle):
            BuiltInTest.getInstance().run_BIT()
        return 1

    # Belongs to the StateIdle
    def function_LCD_BIT(self):
        if isinstance(self.alarm_mode, StateIdle):
            BuiltInTest.getInstance().run_component_BIT("LCDConsole")
        return 1

class AbstractState():
    """ This class is the default behaviour of a state.  As per the name, it is meant to be abstract and
    specialized.  Every state can transition to StateFire.  This behaviour is implemented by the AbstractState.
    """
    model = None

    def __init__(self):
        pass

    def __str__(self):
        return self.__class__.__name__

    def handle_event(self, event_type, sensor):
        """ This method handle the events for which the behaviour is common to every state.  It should be
        called by the specialized state.
        """
        #Code that is common to all states.
        if event_type == "fire" and not sensor.is_locked():
            self.model.last_trig_sensor = sensor
            self.model.last_trig_state = self
            self.set_state(StateFire())

    def set_state(self, state):
        """ This method changes the alarm_mode of the AlarmModel.  It ensures the proper "Alarm Mode Update Model"
        event is generated.
        """
        logger.info("------- Entering state " + str(state) + " -------")
        self.model.last_alarm_mode = self.model.alarm_mode
        self.model.alarm_mode = state
        event_q.put(
            [dispatcher.send, {"signal": "Alarm Mode Update Model", "sender": dispatcher.Any}])

class StateBIT(AbstractState):
    """ This class is the state when the system is doing the component BITs.
    """

    def handle_event(self, event_type, sensor):
        # This state does absolutely nothing.
        pass

class StateIdle(AbstractState):
    """ This class is the state when the system is Idle.  This state can transition to StatePartiallyArmed
    or StateArming.
    """

    def handle_event(self, event_type, sensor):
        AbstractState.handle_event(self, event_type, sensor)
        if event_type == "PIN":
            self.model.set_grace_timer(self.model.arming_grace_time)
            self.model.broadcast_message("Leave the house.")
            self.set_state(StateArming())
        elif event_type == "*":
            # Sensors should be checked before changing to the PARMED state (we should not arm if a door is open)
            if self.model.check_sensors_locked(StatePartiallyArmed):
                self.set_state(StatePartiallyArmed())
            else:
                self.model.broadcast_message("Not locked!")
                logger.info("Sensor not locked when attempting to enter StatePartiallyArmed")


class StatePartiallyArmed(AbstractState):
    """ This class is the state when the system is not completely armed and meant to be used when occupants are in the
    house.  This state can transition back to StateIdle when the PIN is entered or StateDisarming when an armed sensor
    is triggered.
    """

    def handle_event(self, event_type, sensor):
        AbstractState.handle_event(self, event_type, sensor)
        if event_type == "PIN":
            self.set_state(StateIdle())
        elif event_type == "sensor":
            logger.debug("A sensor event was received")
            if sensor.is_armed() and not sensor.is_locked():
                logger.debug("An armed sensor event was received")
                self.model.last_trig_sensor = sensor
                self.model.last_trig_state = self
                if sensor.get_disarming_grace() == 0:
                    self.set_state(StateAlert())
                else:
                    self.model.set_grace_timer(sensor.get_disarming_grace())
                    self.set_state(StateDisarming())
                    self.model.broadcast_message("Enter PIN")
                    #self.model.set_grace_timer(self.model.disarming_grace_time)


class StateArming(AbstractState):
    """ This class is the state when the system is in transition to StateArmed.  It provides a delay for the occupants to
    leave the house.  This state can transition back to StateIdle when the PIN is entered or StateArmed after the
    grace period.
    """

    def handle_event(self, event_type, sensor):
        AbstractState.handle_event(self, event_type, sensor)
        if event_type == "PIN":
            self.model.set_grace_timer(0)
            self.set_state(StateIdle())
        elif event_type == "tic":
            self.model.set_grace_timer(self.model.grace_timer - 1)
            if self.model.grace_timer <= 0:
                if self.model.check_sensors_locked(StateArmed):
                    self.set_state(StateArmed())
                else:
                    self.model.broadcast_message("Armed failed!")
                    self.set_state(StateIdle())


class StateArmed(AbstractState):
    """ This class is the state when the system fully armed and meant to be used when occupants are away from the
    house.  This state can transition back to StateIdle when the PIN is entered (unlikely since you have to trigger a sensor to
    enter the house) or StateDisarming when an armed sensor
    is triggered.
    """

    def handle_event(self, event_type, sensor):
        AbstractState.handle_event(self, event_type, sensor)
        if event_type == "PIN":
            self.set_state(StateIdle())
        elif event_type == "sensor":
            if sensor.is_armed() and not sensor.is_locked():
                self.model.last_trig_sensor = sensor
                self.model.last_trig_state = self
                if sensor.get_disarming_grace() == 0:
                    self.set_state(StateAlert())
                else:
                    self.model.set_grace_timer(sensor.get_disarming_grace())
                    self.set_state(StateDisarming())
                    self.model.broadcast_message("Enter PIN")
            else:
                pass
                #Perhaps, it is misconfigured unless there is a situation where a sensor is only armed in PARMED?


class StateDisarming(AbstractState):
    """ This class is the state when the system is in transition to StateAlert.  This state can transition back to
    StateIdle when the PIN is entered or StateAlert after the grace period.
    """

    def handle_event(self, event_type, sensor):
        #This call has been removed to prevent the system to go in StateFire
        #AbstractState.handle_event(self,event_type,sensor)
        if event_type == "PIN":
            self.model.set_grace_timer(0)
            self.set_state(StateIdle())
        elif event_type == "tic":
            self.model.set_grace_timer(self.model.grace_timer - 1)
            if self.model.grace_timer <= 0:
                self.set_state(StateAlert())


class StateAlert(AbstractState):
    """ This class is the state when the system is the intrusion alert state.  This state can transition only transition
    back to StateIdle when the PIN is entered.
    """

    def handle_event(self, event_type, sensor):
        #This call has been removed to prevent the system to go in StateFire
        #AbstractState.handle_event(self,event_type,sensor)
        if event_type == "PIN":
            self.set_state(StateIdle())


class StateFire(AbstractState):
    """ This class is the state when the system is the fire alert state.  This state can transition transition back to
    StateIdle when the PIN is entered or when all fire sensors are locked.
    """

    def handle_event(self, event_type, sensor):
        AbstractState.handle_event(self, event_type, sensor)
        if event_type == "PIN":        # leaving StateFire if the PIN is typed
            self.set_state(StateIdle())
        elif event_type == "fire":    # leaving StateFire if there is no longer an unlocked fire detector
            if self.model.check_sensors_locked(sensor_type=FireSensor):
                self.set_state(StateIdle())

#############################################################################################
# Brain Storm on AlarmModel Events
#
# Idea is that the Events could be used by the Dispatcher
# The model can keep a queue of events for history purposes.  Length TBD
#
#############################################################################################
class AlarmModelEvent():
    def __init__(self, description):
        self.event_time = time.time()
        self.description = description

    def __str__(self):
        return time.strftime("%Y-%m-%dT%H:%M:%S", self.event_time) + " " + self.description

class SensorEvent(AlarmModelEvent):
    def __init__(self, sensor):
        self.sensor = sensor
        self.alarm_mode = AlarmModel.getInstance().alarm_mode

class IntrusionEvent(SensorEvent):
    pass

class FireEvent(SensorEvent):
    pass

class InputEvent(AlarmModelEvent):
    #"PIN entered"
    #"Guest PIN entered"
    #"Function X entered"
    pass

class FaultEvent(AlarmModelEvent):
    pass


#############################################################################################