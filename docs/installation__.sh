#!shell

################################## Update distribution ##################################
#enlarge fs
sudo raspi-config

sudo passwd

sudo apt-get update
sudo apt-get dist-upgrade

##auto mount a windows folder to get files
sudo nano /etc/fstab
##modify to mount your folder containing the alarm system
#//WindowsPC/Share1 /mnt/mountfoldername cifs username=yourusername,password=yourpassword 0 0
//GUILLAUME-PC/RaspberryPi /mnt/dropbox cifs username= 0 0


##install latest firmware for audio to be smooth
##https://github.com/Hexxeh/rpi-update

sudo wget http://goo.gl/1BOfJ -O /usr/bin/rpi-update && sudo chmod +x /usr/bin/rpi-update
sudo apt-get install git-core
sudo rpi-update


################################## install packages ##################################

##Not required anymore in version 13.4
##install wx
##sudo apt-get install python-wxgtk2.8 python-wxtools wx2.8-i18n
##or
##sudo apt-get install python-wxgtk2.8 python-wxtools wx2.8-i18n libwxgtk2.8-dev libgtk2.0-dev



##install RPi.GPIO
sudo apt-get install python-rpi.gpio python3-rpi.gpio #replaced by RPIO in auto setup

##install get pip
sudo apt-get install python-pip #implicit
##then use it to install PyDisapatcher
sudo pip install PyDispatcher # added to auto setup
##and to install RPYC
sudo pip install rpyc

#install PYYAML
sudo pip install pyyaml

##install alsa for wav playback
sudo apt-get install alsa-utils 


##un-blacklist i2c 
sudo nano /etc/modprobe.d/raspi-blacklist.conf
un-blacklist i2c and spi. (comment both lines)

##install smbus (for i2c)
sudo apt-get install python-smbus

##install gdata 
sudo apt-get install python-gdata


##add i2c and music to modules
sudo nano /etc/modules
##add
i2c-bcm2708
i2c-dev
##snd_bcm2835 (already there)

##give i2c access to all users
sudo nano /etc/udev/rules.d/99-i2c.rules
##add lines
SUBSYSTEM=="i2c-dev", MODE="0666"

##configuring sounds
sudo amixer cset numid=3 1



##################################  auto run ##################################
##add line to auto start

#modify and copy the alarmSystem shell script into the /etc/init.d/ folder
sudo cp ./alarmSystem /etc/init.d/
sudo chmod 755 /etc/init.d/alarmSystem

#test starting the alarmSystem
sudo /etc/init.d/alarmSystem start

#test stopping the alarmSystem
sudo /etc/init.d/alarmSystem stop

#register your script so it auto starts
sudo update-rc.d alarmSystem defaults 

#to deregister it, run
#sudo update-rc.d -f  alarmSystem remove 