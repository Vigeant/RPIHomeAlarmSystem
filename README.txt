==============================
Raspberry Pi Home Alarm System
==============================

The Raspberry Pi Alarm system is a DIY system built around the Raspberry Pi computer. It provides normal home alarm system functionalities as well as some added features such as sms message notifications, remote configuration and administration through ssh and weather display on interface unit.

In it current version, it supports a physical user interface based on the LCD03 display that is also used to scann a 3x4 keypad. Complete instructions on how to setup the hardware can be found in the technical documentation found in the docs folder of this project.

Once the RPIHomeAlarmSystem is operational, it operates very similarly to any modern alarm systems:

Installation
============

Please consult the installation_.sh file in the doc dir for a detailed procedure for installation.

Arming sequence
===============

If the alarm is in the idle state (Alarm system status icon shows an unlocked lock), it can be armed by entering the nip. When arming, the system immediately takes a snapshot of the sensors and will essentially only monitor the sensors that were closed at the time of arming and ignore the rest. This allows arming the system even if you want to leave the back door or the garage open for example. The arming sequence then enters a grace period of 30 seconds (configurable) to allow the user to leave the house. During this grace period, sensors are allowed to change state without triggering the alarm. The grace timer is displayed on the LCD and a audible beep is emitted every seconds. The last five seconds play three beeps to warn that the grace period is almost over.

Disarming sequence
==================

When the system is armed, it can be disarmed by entering the pin again. If a monitored sensor is open while in the armed mode, it starts a grace timer of 30 seconds to let the user disarm the system by entering the pin. If the user does not successfully disarm the system before the 30 seconds, it transitions into alarm mode where a loud siren is played for 15 minutes and an SMS is sent to the user indicating what sensor triggered the alarm. When in the alarm state, the locked lock icon is replaced with the word ALERT. Note that at any point in time the keypad+LCD unit may be unplugged or disconnected without affecting the operation of the alarm system. This prevents the alarm system from stopping if the burglar cuts the wires. If the keypad and LCD are reconnected in operation, it will reinitialize itself and will be usable again.

Alarm system configuration
==========================

At this point, all your hardware and software is installed and all that remains is to configure your system so that it maps the GPIO pins to the right sensors, sends sms messages through your Google calendar account as well as choose a nip to arm and disarm your system. All of this is done by editing the alarm_config.json file in the project folder. The file should be self-explanatory. Make sure your Google calendar account is set up to allow sms reminders for events as this is the mechanism used to send sms.
The weather is obtained through the web api of wunderground.com. Make sure you obtain a free api key and enter it in the configuration file as well. This will allow you to receive free weather updates that will display on the LCD of your alarm system. Also enter the appropriate zone such as your postal code in the appropriate field.

SSH monitoring
==============

Once your system is operational, you can interact with your system by logging via ssh and using the provided alarmSystem script to either stop, start, restart, arm, and get the status of your system. The status returned is essentially a copy of what is on the LCD.
