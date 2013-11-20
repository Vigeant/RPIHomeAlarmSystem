from pydispatch import dispatcher
import logging
from singletonmixin import Singleton
from event_serializer import event_q

logger = logging.getLogger('alarm')


class AlarmModel(Singleton):
    """ This class is the Model in the MVC pattern and contains all the info for
    the alarm system. The model is not aware of any API and only communicates
    updates via publishing.
    """
    alarm_mode = None

    #------------------------------------------------------------------------------
    def __init__(self, alarm_config_dictionary):
        self.arming_grace_time = alarm_config_dictionary[
            "arming grace delay"]  # this is the grace period for the system to arm
        self.disarming_grace_time = alarm_config_dictionary[
            "disarming grace delay"]  # this is the grace period for the system to go into alert mode
        self.grace_timer = self.arming_grace_time

        self.last_trig_sensor = None
        self.last_trig_state = None

        self.temp_c = "0.0"
        self.wind_deg = 0
        self.wind_dir = ""
        self.wind_kph = 0.0

        self.hours = 0
        self.minutes = 0
        self.seconds = 0
        self.pin = alarm_config_dictionary["pin"]

        self.script_path = ""

        self.fault_power = False
        self.fault_network = False

        self.input_string = ""
        self.display_string = ""
        self.last_message = ""

        self.input_activity = 0
        self.input_activity_setting = 4

        self.sensor_list = []
        self.reboot_string = alarm_config_dictionary["reboot"]

        AbstractState.model = self
        AbstractState().set_state(StateIdle())

        logger.info("AlarmModel initialized")

    def __str__(self):
        model_string = "AlarmModel:\n"
        model_string += "Current Time: {:0>2}:{:0>2}".format(self.hours, self.minutes) + "\n"
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
        model_string += self.print_sensors_state()

        return model_string

    #-------------------------------------------------------------------
    def keypad_input(self, key):
        if key == "":    # System tic
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

        if key == "*" and self.input_string == self.reboot_string:
            global terminate
            terminate = True
            event_q.put([dispatcher.send, {"signal": "Reboot", "sender": dispatcher.Any, }])
            logger.warning("----- Reboot code entered. -----")
        elif key == "*":
            self.input_string = ""
            self.display_string = ""
            self.alarm_state_machine("*")

        #elif key == "#" or len(self.input_string)> 8:
        elif key == "#":
            self.input_string = ""
            self.display_string = ""
        else:
            if len(self.input_string) == len(self.pin):
                self.input_string = self.input_string[1:]
            else:
                self.display_string += "*"
            self.input_string += key

        logger.debug("Input string: " + self.input_string)

        event_q.put([dispatcher.send,
                    {"signal": "Input String Update Model", "sender": dispatcher.Any,
                     "msg": self.display_string}])

        if self.input_string == self.pin:
            level = logger.info("PIN entered.")
            self.broadcast_message("PIN entered.")
            self.input_string = ""
            self.display_string = ""
            self.alarm_state_machine("PIN")

    #-------------------------------------------------------------------
    def alarm_state_machine(self, event_type, sensor=None):
        self.alarm_mode.handle_event(event_type, sensor)

    ##-------------------------------------------------------------------
    #def arm_signal_handler(self, signal_number, frame):
    #    logger.info("Received arming signal. Arming...")
    #    self.alarm_mode.set_state(StateArmed)
    #    signal.pause()

    #-------------------------------------------------------------------
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

        self.keypad_input("")  # TODO review wtf???
        self.alarm_state_machine("tic")

        event_q.put([dispatcher.send, {"signal": "Time Update Model", "sender": dispatcher.Any}])

    #-------------------------------------------------------------------
    def add_sensor(self, sensor):
        """ Adds a sensor to the model."""
        self.sensor_list.append(sensor)

    #-------------------------------------------------------------------
    def update_sensor(self, sensor):
        if sensor.is_fire_type():
            self.alarm_state_machine("fire", sensor)
        else:
            self.alarm_state_machine("sensor", sensor)
        event_q.put([dispatcher.send,
                    {"signal": "Sensor Update Model", "sender": dispatcher.Any, "msg": sensor}])

    def check_sensors_locked(self, state=None, sensor_type="intrusion"):
        """ Verifies if all armed sensors are locked.
        The verification is done in the current alarm_mode by default.
        """
        if state is None:
            state = self.alarm_mode
        for sensor in self.sensor_list:
            if sensor.is_armed(state) and not sensor.is_locked():
                if sensor_type == "fire":
                    if sensor.is_fire_type():
                        return False
                else:
                    return False
        return True

    def print_sensors_state(self):
        """ Returns a string containing the current state of all sensors. """
        sensor_state_string = ""
        for sensor in self.sensor_list:
            sensor_state_string += str(sensor) + "\n"
        return sensor_state_string

    def broadcast_message(self, msg):
        self.last_message = msg
        event_q.put(
            [dispatcher.send, {"signal": "Alarm Message", "sender": dispatcher.Any, "msg": msg}])

class AbstractState():
    """ This class is the default behaviour of a state.  As per the name, it is meant to be abstract and
    specialized.  Every state can transition to StateFire.  This behaviour is implemented by the AbstractState.
    """

    def __init__(self):
        pass

    model = None

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
            if self.model.check_sensors_locked(StatePartiallyArmed()):
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
            if sensor.is_armed() and not sensor.is_locked():
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
                if self.model.check_sensors_locked(StateArmed()):
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
            if self.model.check_sensors_locked(sensor_type="fire"):
                self.set_state(StateIdle())
