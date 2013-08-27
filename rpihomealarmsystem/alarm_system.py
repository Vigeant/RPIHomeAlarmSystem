#!/usr/bin/env python

from i2clcd import I2CLCD
import time
import RPi.GPIO as io
#import RPIO as io
import urllib2
import urllib
import json
#import wx
import sys
import string

import atom
import gdata.calendar
import gdata.calendar.service
import random
import os
import subprocess
import signal

from Queue import Queue
from threading import Thread
#from multiprocessing import Process

#from wx.lib.pubsub import Publisher
from pydispatch import dispatcher
from singletonmixin import Singleton


'''********************************************************************************
							vige_alarm_system

Features



********************************************************************************'''


###################################################################################
class Time_scanner(Thread):
	""" This class scanns and publishes the time in its own thread """
	#------------------------------------------------------------------------------
	def __init__(self):
		""" Init the time scanner """
		Thread.__init__(self)
		self.start()

	#-------------------------------------------------------------------
	def run(self):
		print("Time_scanner started")
		while(True):
			h = time.localtime().tm_hour
			m = time.localtime().tm_min
			s = time.localtime().tm_sec
			eventQ.put([dispatcher.send,{"signal":"Time Update", "sender":dispatcher.Any,"msg":[h,m,s]}])
			time.sleep(1)

#####################################################################################
class Weather_scanner(Thread):
	""" This class will scann the weather in its own thread """
	#------------------------------------------------------------------------------
	def __init__(self,alarm_config_dictionary):
		""" Init the weather scanner """
		Thread.__init__(self)
		self.url = 'http://api.wunderground.com/api/' + alarm_config_dictionary["wunderground api key"] + '/geolookup/conditions/q/'+alarm_config_dictionary["wunderground location"]+'.json'
		
		self.start()

	#-------------------------------------------------------------------
	def run(self):
		print("Weather_scanner started")
		while(True):
			try:
				self.weather_url = urllib2.urlopen(self.url)
				json_weather_string = self.weather_url.read()
			except:
				print(sys.exc_info())
				
			try:
				parsed_json_weather = json.loads(json_weather_string)
			except ValueError:
				print(sys.exc_info())
				
			location = parsed_json_weather['location']['city']
			wind_dir = parsed_json_weather['current_observation']['wind_degrees']
			wind_kph = parsed_json_weather['current_observation']['wind_kph']
			temp = parsed_json_weather['current_observation']['feelslike_c']
			msg = [temp,wind_dir,wind_kph]
			eventQ.put([dispatcher.send,{"signal":"Weather Update", "sender":dispatcher.Any,"msg":msg }])
			time.sleep(300) 


		   
###################################################################################
class Alarm_model():
	""" This class is the Model in the MVC pattern and contains all the info for
		the alarm system. The model is not aware of any API and only communicates
		updates via publishing."""
	#------------------------------------------------------------------------------
	def __init__(self,alarm_config_dictionary):
		self.armed_mode, self.arming_grace, self.disarming_grace, self.idle, self.alert = range(5)
		self.temp_C = "0.0"
		self.wind_dir = 0
		self.wind_kph = 0.0
		self.hours = 0
		self.minutes = 0
		self.seconds = 0
		self.pin = alarm_config_dictionary["pin"]

		self.trig_sensor = 0
		

		self.input_string = ""
		self.display_string = ""
		
		self.arming_grace_time = alarm_config_dictionary["arming grace delay"] #this is the grace period for the system to arm
		self.disarming_grace_time = alarm_config_dictionary["disarming grace delay"] #this is the grace period for the system to go into alert mode
		self.grace_timer = self.arming_grace_time

		self.sensor_switch_states = alarm_config_dictionary["sensor_map"].copy()

		for pin,state in self.sensor_switch_states.iteritems():   
			self.sensor_switch_states[pin] = ""

		self.sensor_switch_armed_states = self.sensor_switch_states
		self.set_alarm_mode(self.idle)
		
		signal.signal(signal.SIGUSR2, self.arm_signal_handler)
		print("Alarm_model initialized")

	#-------------------------------------------------------------------
	def keypad_input(self, msg):
		if msg == "*" or msg == "#" or len(self.input_string)> 8:
			self.input_string = ""
			self.display_string = ""
		else:			
			self.input_string += msg
			self.display_string += "*"
			self.alarm_state_machine("key")
			if self.input_string == self.pin:
				self.input_string = ""
				self.display_string = ""
		eventQ.put([dispatcher.send,{"signal":"Display String Update Model", "sender":dispatcher.Any, "msg":self.display_string }])
		

	#-------------------------------------------------------------------
	def alarm_state_machine(self,event_type):
		################################################################ idle
		if self.alarm_mode == self.idle:
			if event_type == "key" and self.input_string == self.pin:
				self.set_alarm_mode(self.arming_grace)
				self.set_grace_timer(self.arming_grace_time)
				
		################################################################ arming grace
		elif self.alarm_mode == self.arming_grace:
			if event_type == "key" and self.input_string == self.pin:
				self.set_alarm_mode(self.idle)
			elif event_type == "tic":
				self.set_grace_timer(self.grace_timer - 1)
				if self.grace_timer <=0 :
					self.sensor_switch_armed_states = self.sensor_switch_states.copy()
					self.set_alarm_mode(self.armed_mode)
				
		################################################################ armed
		elif self.alarm_mode == self.armed_mode:
			if event_type == "key" and self.input_string == self.pin:
				self.set_alarm_mode(self.idle)
			elif event_type == "sensor":
				for sensor,state in self.sensor_switch_armed_states.iteritems():
					if state == "LOCKED" and self.sensor_switch_states[sensor] == "UNLOCKED":
						self.trig_sensor = sensor
						self.set_grace_timer(self.disarming_grace_time)
						self.set_alarm_mode(self.disarming_grace)
						break
					
				
		################################################################ disarming grace
		elif self.alarm_mode == self.disarming_grace:
			if event_type == "key" and self.input_string == self.pin:
				self.set_alarm_mode(self.idle)
			elif event_type == "tic":
				self.set_grace_timer(self.grace_timer - 1)
				if self.grace_timer <=0 :
					self.set_alarm_mode(self.alert)
					
		################################################################ alert
		elif self.alarm_mode == self.alert:
			if event_type == "key" and self.input_string == self.pin:
				self.set_alarm_mode(self.idle)
		
	def arm_signal_handler(self,signal_number,frame):
		print("Arming")
		self.sensor_switch_armed_states = self.sensor_switch_states.copy()
		self.set_alarm_mode(self.armed_mode)
		signal.pause()
	
	#-------------------------------------------------------------------
	def set_grace_timer(self,t):
		self.grace_timer = t
		eventQ.put([dispatcher.send,{"signal":"Grace Update Model", "sender":dispatcher.Any, "msg":self.grace_timer}])

	#-------------------------------------------------------------------
	def set_alarm_mode(self,mode):
		self.alarm_mode = mode
		if mode == self.alert:
			
			eventQ.put([dispatcher.send,{"signal":"Alarm Mode Update Model", "sender":dispatcher.Any, "msg":[self.alarm_mode,self.trig_sensor] }])
		else:
			
			eventQ.put([dispatcher.send,{"signal":"Alarm Mode Update Model", "sender":dispatcher.Any, "msg":[self.alarm_mode,0]}])

	#-------------------------------------------------------------------
	def update_weather(self, msg):
		[self.temp_C,self.wind_dir,self.wind_kph] = msg
		eventQ.put([dispatcher.send,{"signal":"Weather Update Model", "sender":dispatcher.Any, "msg":[self.temp_C,self.wind_dir,self.wind_kph]}])

	#-------------------------------------------------------------------
	def update_time(self,msg):
		[self.hours,self.minutes,self.seconds] = msg
		self.alarm_state_machine("tic")
		eventQ.put([dispatcher.send,{"signal":"Time Update Model", "sender":dispatcher.Any, "msg":[self.hours,self.minutes,self.seconds]}])

	#-------------------------------------------------------------------
	def set_sensor(self,channel,state):
		if not self.sensor_switch_states[channel] == state:
			self.sensor_switch_states[channel] = state
			self.alarm_state_machine("sensor")
			eventQ.put([dispatcher.send,{"signal":"Sensor Update Model", "sender":dispatcher.Any, "msg":[channel,state]}])


###################################################################################
class Alarm_controller():
	""" This class is the Controller in the MVC pattern and drives all of the alarm system.
		The controller is aware of the API for the model and actively interact with it.
		It is however only able to get updates from the model by subscribint to topics
		the model publishes."""
	#------------------------------------------------------------------------------
	def __init__(self):
 

		#subscribe to several topics of interest (scanners)
		dispatcher.connect(self.handle_update_weather,signal="Weather Update",sender=dispatcher.Any,weak=False )	
		dispatcher.connect(self.handle_keypad_input,signal="Button Pressed",sender=dispatcher.Any, weak=False)
		dispatcher.connect(self.handle_update_time,signal="Time Update",sender=dispatcher.Any, weak=False)
		dispatcher.connect(self.handle_sensor_handler,signal="Sensor Changed",sender=dispatcher.Any, weak=False)

		#read configuration file
		script_path = os.path.dirname(os.path.abspath(__file__))+"/"
		try:
			alarm_config_file = open("/home/pi/" + "alarm_config.json",'r')
		except:
			print("could not open file : /home/pi/alarm_config.json ...")


		try:
			alarm_config_dictionary = json.loads(alarm_config_file.read())
			alarm_config_file.close()
		except ValueError:
			print(sys.exc_info())
			print("your alarm_config.json file seems to be corrupted...\n delete it to generate new stub")
			exit	  
		

		#create model (MVC pattern)
		self.model = Alarm_model(alarm_config_dictionary)

		#create View  (MVC pattern)
		Alarm_view(alarm_config_dictionary,self.model)
		Sound_player(alarm_config_dictionary,script_path) #testing the fucking bug where it stops working after some time when playing a sound
		
		#create scanners (threads that periodically poll things)
		Keypad_scanner()
		Time_scanner()
		Weather_scanner(alarm_config_dictionary)
		Sensor_scanner(alarm_config_dictionary)
		
		print("Alarm_controller started")

	#--------------------------------------------------------------------------------
	def handle_keypad_input(self,msg):
		self.model.keypad_input(msg)

	#--------------------------------------------------------------------------------
	def handle_update_time(self,msg):
		self.model.update_time(msg)

	#--------------------------------------------------------------------------------
	def handle_update_weather(self, msg):
		self.model.update_weather(msg)

	#--------------------------------------------------------------------------------
	def handle_sensor_handler(self, msg):
		[channel,state] = msg
		#print(msg)
		if state:
			self.model.set_sensor(channel,"UNLOCKED")
		else:
			self.model.set_sensor(channel,"LOCKED")
		

		

	

#####################################################################################
class Keypad_scanner(Thread):
	""" This class will scann the keypad in its own thread """
	#--------------------------------------------------------------------------------
	def __init__(self):
		""" Init the keypad scanner """
		Thread.__init__(self)
		self.BUTTON_RELEASED, self.BUTTON_PRESSED = [False, True]
		self.key_state = {'1':self.BUTTON_RELEASED,
						 '2':self.BUTTON_RELEASED,
						 '3':self.BUTTON_RELEASED,
						 '4':self.BUTTON_RELEASED,
						 '5':self.BUTTON_RELEASED,
						 '6':self.BUTTON_RELEASED,
						 '7':self.BUTTON_RELEASED,
						 '8':self.BUTTON_RELEASED,
						 '9':self.BUTTON_RELEASED,
						 '0':self.BUTTON_RELEASED,
						 '*':self.BUTTON_RELEASED,
						 '#':self.BUTTON_RELEASED}
		
		
		self.start()	# start the thread

	#--------------------------------------------------------------------------------
	def run(self):
		""" Run the keypad scanner """
		print("Keypad_scanner started")
		while(True):
			try:
				self.raw_keypad = I2CLCD.getInstance().get_keypad_buttons()
			except IOError:
				pass
				#print("LCD IOError ... keypad reader check connection")
				
			else:
				for key,state in self.key_state.iteritems():
					if state == self.BUTTON_RELEASED:
						
						if key in self.raw_keypad:				  #and is read as pressed
							self.key_state[key] = self.BUTTON_PRESSED
							eventQ.put([dispatcher.send,{"signal":"Button Pressed", "sender":dispatcher.Any, "msg":key}])
							#wx.CallAfter(Publisher().sendMessage, "Button Pressed", key)#publish that this button is pressed   
					else:
						if not (key in self.raw_keypad):
							self.key_state[key] = self.BUTTON_RELEASED
							eventQ.put([dispatcher.send,{"signal":"Button Released", "sender":dispatcher.Any, "msg":key}])
							#wx.CallAfter(Publisher().sendMessage, "Button Released", key)#publish that this button is released

				
			
			
			time.sleep(0.02)

			
#####################################################################################
class Sensor_scanner(Thread):
	""" This class will scann the sensors in its own thread """
	#------------------------------------------------------------------------------
	def __init__(self,alarm_config_dictionary):
		""" Init the sensor scanner """
		Thread.__init__(self)
		self.closed,self.open  = range(2)


		#initialize state of each pin
		self.sensor_state = alarm_config_dictionary["sensor_map"].copy()
		self.sensor_map = alarm_config_dictionary["sensor_map"].copy()
		
		for pin,state in self.sensor_state.iteritems():   
			self.sensor_state[pin] = 3
	   
		io.setmode(io.BCM)
		self.gpio_setup()

		self.start()	# start the thread

			
	#------------------------------------------------------------------------------
	def gpio_setup(self):
		temp_mode = io.PUD_UP
		for pin,[sensor_name,position,pin_mode] in self.sensor_map.iteritems():
			if pin_mode == "PULLUP":
				temp_mode = io.PUD_UP
			elif pin_mode == "FLOATING":
				temp_mode = io.PUD_UP
			elif pin_mode == "PULLDOWN":
				temp_mode = io.PUD_DOWN
				
			io.setup(int(pin), io.IN, pull_up_down=temp_mode)

			
	#------------------------------------------------------------------------------
	def run(self):
		""" Run the sensor scanner """
		print("Sensor_scanner started")
		while(True):
			for pin,[sensor_name,position,pin_mode] in self.sensor_map.iteritems():
				current_reading = io.input(int(pin))
				if pin_mode == "PULLUP":
					pass
				elif pin_mode == "FLOATING":
					current_reading = 1 - current_reading
				elif pin_mode == "PULLDOWN":
					current_reading = 1 - current_reading
				
				if not current_reading == self.sensor_state[pin]:
					self.sensor_state[pin] = current_reading
					eventQ.put([dispatcher.send,{"signal":"Sensor Changed", "sender":dispatcher.Any, "msg":[pin,self.sensor_state[pin]]}])						  
			time.sleep(0.2)

###################################################################################
class Sound_player():
	""" This class is responsible to play the sounds. And for most bugs"""

	#------------------------------------------------------------------------------
	def __init__(self,alarm_config_dictionary,script_path):
		self.alarm_config = alarm_config_dictionary.copy()
		
		"""subscribe to several topics of interest (model)"""

		dispatcher.connect( self.play_alarm_mode, signal="Alarm Mode Update Model", sender=dispatcher.Any, weak=False)
		dispatcher.connect( self.play_pin, signal="Display String Update Model", sender=dispatcher.Any,weak=False )
		dispatcher.connect( self.play_grace_timer, signal="Grace Update Model", sender=dispatcher.Any, weak=False)
		dispatcher.connect( self.play_sensor_change, signal="Sensor Update Model", sender=dispatcher.Any, weak=False)
		
		self.armed_mode, self.arming_grace, self.disarming_grace, self.idle, self.alert = range(5)
		self.alarm_mode = self.idle
		self.script_path = script_path
		print("Sound_player started")

	def play_sensor_change(self,msg):
		[sensor,state] = msg
		# the second part of the condition is to disable the sound on the motion sensor (fucking annoying)
		if state == "UNLOCKED" and not (self.alarm_config["sensor_map"][sensor][2] == "FLOATING"): 
			subprocess.Popen(['aplay','-q',self.script_path+self.alarm_config["grace_beeps3"]])
					

	def play_grace_timer(self,msg):
		if msg == self.alarm_config["arming grace delay"]:
			pass
		elif msg > 10:
			subprocess.Popen(['aplay','-q',self.script_path+self.alarm_config["grace_beeps"]])
		else:
			subprocess.Popen(['aplay','-q',self.script_path+self.alarm_config["grace_beeps3"]])


	def play_alarm_mode(self,msg):
		[self.alarm_mode,sensor] = msg
		
		if self.alarm_mode == self.idle:
			try:
				subprocess.Popen(['aplay','-q',self.script_path+self.alarm_config["grace_beeps3"]])
				subprocess.call("ps x | grep '[a]play' | awk '{ print $1 }' | xargs kill",shell=True)
			except:
				print(sys.exc_info()) 
		
		elif self.alarm_mode == self.alert:
			subprocess.Popen(['aplay','-q',self.script_path+self.alarm_config["alarm_wav"]])
			

	def play_pin(self,msg):	   
		subprocess.Popen(['aplay','-q',self.script_path+self.alarm_config["button_wav"]])   
			
		

###################################################################################
class Alarm_view():
	""" This class is the View in the MVC pattern and is responsible for updating
		the I2CLCD.getInstance() as well as the ui_file with the current status."""
	#------------------------------------------------------------------------------
	def __init__(self,alarm_config_dictionary,model):
		self.sms_sender = SMS_sender(alarm_config_dictionary.copy())
		
		self.BUTTON_RELEASED, self.BUTTON_PRESSED = [False, True]
		self.key_state = {'1':self.BUTTON_RELEASED,
						 '2':self.BUTTON_RELEASED,
						 '3':self.BUTTON_RELEASED,
						 '4':self.BUTTON_RELEASED,
						 '5':self.BUTTON_RELEASED,
						 '6':self.BUTTON_RELEASED,
						 '7':self.BUTTON_RELEASED,
						 '8':self.BUTTON_RELEASED,
						 '9':self.BUTTON_RELEASED,
						 '0':self.BUTTON_RELEASED,
						 '*':self.BUTTON_RELEASED,
						 '#':self.BUTTON_RELEASED}



		self.time_cursor_start = 1
		self.weather_cursor_start = 11
		self.pin_cursor_start = 21
		self.alarm_mode_cursor_start = 36
		self.grace_timer_cursor_start = 39

		#constants
		self.set_backlight_on = 0x13
		self.set_backlight_off = 0x14

		""" mapping of the pin number and sensor """
		""" {PIN NUMBER : [SENSOR_SYMBOL , CURSOR_PSITION] """
		#get sensor map from alarm_config.json file
		self.sensor_map = alarm_config_dictionary["sensor_map"].copy()
		self.model = model
		
		self.table = string.maketrans(chr(128)+chr(129)+chr(130)+chr(131)+chr(132)+chr(133)+chr(134)+chr(135), "OoLUDCPA")
		self.LCD_template =   ( '######################\n' + 
								'#                    #\n' +
								'#                    #\n' + 
								'#                    #\n' +
								'#                    #\n' +
								'######################\n')
					
		"""subscribe to several topics of interest (model)"""
	   
		dispatcher.connect( self.update_weather, signal="Weather Update Model", sender=dispatcher.Any ,weak=False)
		dispatcher.connect( self.update_time, signal="Time Update Model", sender=dispatcher.Any ,weak=False)
		dispatcher.connect( self.update_alarm_mode, signal="Alarm Mode Update Model", sender=dispatcher.Any,weak=False )
		dispatcher.connect( self.update_pin, signal="Display String Update Model", sender=dispatcher.Any ,weak=False)
		dispatcher.connect( self.update_sensor_state, signal="Sensor Update Model", sender=dispatcher.Any, weak=False)
		dispatcher.connect( self.update_grace_timer, signal="Grace Update Model", sender=dispatcher.Any, weak=False)

		signal.signal(signal.SIGUSR1, self.update_ui_file)
		self.ui_file_path = os.path.dirname(os.path.abspath(__file__))+"/"
		self.lcd_init_required = True


	#-------------------------------------------------------------------
	def init_screen(self):
		I2CLCD.getInstance().init()
		self.lcd_init_required = False
		
		self.draw_sensors()
		self.send_commands_to_lcd([4],"")#remove blinking cursor
		self.send_commands_to_lcd([self.set_backlight_on],"")
		self.update_weather(msg="")
		self.update_time("")
		self.update_pin("")
		self.update_alarm_mode("")

	#-------------------------------------------------------------------
	def update_ui_file_template(self,a_cmd,s):
		temp_s = string.translate(s,self.table)
		if a_cmd[0] == 2 :
			line_num = a_cmd[1] // 20
			col_num = a_cmd[1] % 20 +1
			self.LCD_template = self.LCD_template[:23+a_cmd[1]+line_num*3]+temp_s+self.LCD_template[23+a_cmd[1]+line_num*3+len(temp_s):];

	def update_ui_file(self,signalnumber,frame):
		with open(self.ui_file_path + "ui_file",'w') as ui_file:
			ui_file.write(self.LCD_template)
		#print(self.LCD_template)
		signal.pause()
	
	#-------------------------------------------------------------------
	def send_commands_to_lcd(self,a_cmd,s):
		ordinated_s = [ord(i) for i in s]
		self.update_ui_file_template(a_cmd,s)
		try:
			if self.lcd_init_required:
				self.init_screen()	
			I2CLCD.getInstance().send_cmd(a_cmd + ordinated_s)
		except IOError:
			self.lcd_init_required = True
			#print("LCD IOError ... check connection")

			
	#-------------------------------------------------------------------
	def get_char(self,symbol):
		temp = chr(135)
		try:
			if self.lcd_init_required:
				self.init_screen() 
			temp = I2CLCD.getInstance().get_char(symbol)
		except IOError:
			#self.lcd_init_required = True
			#print("LCD IOError ... check connection")
			pass
		return temp
		
	#-------------------------------------------------------------------
	def update_grace_timer(self,msg):
		timer = self.model.grace_timer
		self.send_commands_to_lcd([2,self.grace_timer_cursor_start],"{:2}".format(timer))		

	#-------------------------------------------------------------------
	def draw_sensors(self):
		for a_sensor,[sensor_symbol,cursor_pos,pin_mode] in self.sensor_map.iteritems():
			self.send_commands_to_lcd([2,cursor_pos],self.get_char(sensor_symbol))
			self.send_commands_to_lcd([2,cursor_pos+20],self.get_char(self.model.sensor_switch_states[a_sensor]))

	#-------------------------------------------------------------------
	def update_sensor_state(self, msg):
		[sensor,state] = msg
		[sensor_symbol,cursor_pos,pin_mode] = self.sensor_map[sensor]
		self.send_commands_to_lcd([2,cursor_pos+20],self.get_char(state))

	#-------------------------------------------------------------------
	def update_weather(self,msg):
		[temp,wind_dir,wind_kph] = [self.model.temp_C,self.model.wind_dir,self.model.wind_kph]
		weather_string = "{:>3}".format(int(round(float(temp),0))) + self.get_char('DEG')+ "C" +self.wind_dir_arrow(wind_dir)+"{:>2.0f}".format(wind_kph)+"kh"
		#print("formed weather string in view" + weather_string)
		self.send_commands_to_lcd([2,self.weather_cursor_start],weather_string)
		#print("sent string to LCD")

	#-------------------------------------------------------------------
	def update_time(self,msg):
		[h,m,s] = [self.model.hours,self.model.minutes,self.model.seconds]
		time_string = self.get_char('CLOCK')+"{:0>2}:{:0>2}:{:0>2}".format(h,m,s) + "|"
		self.send_commands_to_lcd([2,self.time_cursor_start],time_string)
		
	#-------------------------------------------------------------------
	def update_pin(self,msg):
		pin_string = "Pin: {:<9}".format(self.model.display_string)
		self.send_commands_to_lcd([2,self.pin_cursor_start],pin_string)

	#-------------------------------------------------------------------
	def update_alarm_mode(self,msg):

		[alarm_mode,sensor] = [self.model.alarm_mode,self.model.trig_sensor]


		armed_mode, arming_grace, disarming_grace, idle, alert = range(5)
		if alarm_mode == armed_mode or alarm_mode == disarming_grace:
			alarm_mode_string = self.get_char("LOCKED") + "    "
		elif alarm_mode == arming_grace or alarm_mode == idle:
			alarm_mode_string = self.get_char("UNLOCKED") + "    "
		elif alarm_mode == alert:
			alarm_mode_string = 'Alert'
			[sensor_symbol,cursor_pos,pin_mode] = self.sensor_map[sensor]
			self.sms_sender.send_SMS("Alarm! sensor triggered:" + sensor_symbol) #sends sms
		self.send_commands_to_lcd([2,self.alarm_mode_cursor_start],alarm_mode_string)
			   
	#-------------------------------------------------------------------
	def wind_dir_arrow(self,wind_deg):
		if  23 <= wind_deg < 68:
			temp = self.get_char('SOUTH_WEST')  
		elif 68 <= wind_deg < 113:
			temp =  self.get_char('WEST')
		elif 113 <= wind_deg < 158:
			temp =  self.get_char('NORTH_WEST')
		elif 158 <= wind_deg < 203:
			temp =  self.get_char('NORTH')
		elif 203 <= wind_deg < 248:
			temp =  self.get_char('NORTH_EAST')
		elif 248 <= wind_deg < 293:
			temp =  self.get_char('EST')
		elif 293 <= wind_deg < 338:
			temp =  self.get_char('SOUTH_EST')
		else:
			temp =  self.get_char('SOUTH')
		return temp
		
		

###################################################################################
class SMS_sender():
	#-------------------------------------------------------------------
	def __init__(self,alarm_config_dictionary):
		self.UserName = alarm_config_dictionary["google_username"]
		self.Password = alarm_config_dictionary["google_password"]
		self.Title = "RPI_ALARM"
		
	#-------------------------------------------------------------------
	def send_SMS(self,message):
		cs = gdata.calendar.service.CalendarService()
		cs.email = self.UserName
		cs.password = self.Password
		cs.source = "Google-Calendar-SMS-5.0_" + str(random.randint(0, 10000))
		cs.ProgrammaticLogin()
		event = gdata.calendar.CalendarEventEntry()
		event.title = atom.Title(text=self.Title)
		event.content = atom.Content(text=message)
		event.where.append(gdata.calendar.Where(value_string=message))
		start_time = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() + 2 * 60))
		when = gdata.calendar.When(start_time=start_time, end_time=start_time)
		reminder = gdata.calendar.Reminder(minutes=1, extension_attributes={"method":"sms"})
		when.reminder.append(reminder)
		event.when.append(when)
		new_event = cs.InsertEvent(event, "/calendar/feeds/default/private/full")

  
eventQ = Queue()

###################################################################################
class Event_serializer(Thread):
	""" This serializes send events to ensure thread safety """
	#------------------------------------------------------------------------------
	def __init__(self):
		""" Init the event serializer """
		Thread.__init__(self)
		self.start()
		print("Event_Serializer started")
		
	def run(self):
		while(True):
			[func,kwargs] = eventQ.get()
			func(**kwargs)
		

################################################################################### 
#----------------------------------------------------------------------
# Run the program
if __name__ == "__main__":
	Alarm_controller()
	Event_serializer()
	print("***Initialization complete ***")
	signal.pause()

		
		

