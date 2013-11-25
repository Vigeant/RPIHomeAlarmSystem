import smbus

from singletonmixin import Singleton
from threading import RLock
from Queue import Queue

"""
This is a library for using the i2c LCD03
with i2c on a Raspberry Pi. It was built and tested on Raspbian Wheezy.

This is not an Adafruit product. 

To get i2c to work, you need Raspbian Wheezy or later and to do:
sudo apt-get install python-smbus
sudo apt-get install i2c-tools (usefull but not essential)
sudo modprobe i2c-dev
sudo modprobe i2c-bcm2708

Example Usage:

my_lcd = lcd.I2CLCD()
my_lcd.clr_scrn()
my_lcd.set_backlight(True)
my_lcd.print_str("Time: {:>2}:{:>2}".format(h,m))

This lcd03 driver was built by
Guillaume Vigeant

from an example driver written for the 7segment display by:
Simon Monk http://www.simonmonk.org

Please give credit where credit is due.

Modified by Yann Moffett to meet common interface requirement with I2CBV4618.
"""

key_buffer = []


class I2CLCD(Singleton):
    """
    Initializes the I2CLCD on I2C1.
        Note that if you are using this driver on the RPi A you will need to
        change self.bus = smbus.SMBus(1) to self.bus = smbus.SMBus(0)
    """

    def __init__(self, address=0x63):
        self.lcd_mutex = RLock()
        self.address = address
        self.bus = smbus.SMBus(1)

        self.BUTTON_RELEASED, self.BUTTON_PRESSED = [False, True]
        self.key_state = {'1': self.BUTTON_RELEASED,
                          '2': self.BUTTON_RELEASED,
                          '3': self.BUTTON_RELEASED,
                          '4': self.BUTTON_RELEASED,
                          '5': self.BUTTON_RELEASED,
                          '6': self.BUTTON_RELEASED,
                          '7': self.BUTTON_RELEASED,
                          '8': self.BUTTON_RELEASED,
                          '9': self.BUTTON_RELEASED,
                          '0': self.BUTTON_RELEASED,
                          '*': self.BUTTON_RELEASED,
                          '#': self.BUTTON_RELEASED}

        self.init()

    def init(self):
        self.clr_scrn()
        self.char_dict = {}

        """
        self.CLOCK = 128 # clock char  ex.:lcd lcd.print_str(chr(CLOCK))
        self.DEG = 129 # deg symbol
        self.LOCKED = 130 # Locked lock char
        self.UNLOCKED = 131 # unlocked lock char
        self.DOOR = 132
        self.CAMERA = 133
        self.PATIO = 134
        self.current_symbol = 'null'

        self.send_cmd([27,self.CLOCK,128,142,149,151,145,142,128,128])#clock chr(128)
        self.send_cmd([27,self.DEG,140,146,146,140,128,128,128,128])#deg chr(129)
        self.send_cmd([27,self.LOCKED,128,142,145,145,159,155,159,128])#locked chr(130)
        self.send_cmd([27,self.UNLOCKED,128,142,144,144,159,155,159,128])#unlocked chr(131)
        self.send_cmd([27,self.DOOR,159,149,159,149,159,159,159,159])#door chr(132)
        self.send_cmd([27,self.CAMERA,159,142,132,142,142,142,142,142])#camera chr(133)
        self.send_cmd([27,self.PATIO,159,145,145,147,147,145,145,159])#patio door chr(134)
        """

    def clr_scrn(self):
        self.send_cmd([0x0C])

    """
    Send a command to the LCD.
    """

    def send_cmd(self, cmd):
        with self.lcd_mutex:
            while len(cmd) > 0:
                room = self.get_buffer_room()
                endIndex = min(len(cmd), room, 31)
                self.bus.write_i2c_block_data(self.address, 0x00, cmd[0:endIndex])
                cmd = cmd[endIndex:]

    """
    Sends text to the LCD.
    """

    def send(self, data):
        with self.lcd_mutex:
            for a in range(0, len(data)):
                self.bus.write_byte(self.address, data[a])

    """
    The I2C can send bytes faster than the LCD can process them. Therefore it has a
    64 byte FIFO buffer to receive commands and process them.
    It is good practice to ensure there is room in the buffer
    before sending more data. If data is sent on a full buffer, it will be ignored.
    """

    def get_buffer_room(self):
        return self.bus.read_byte_data(self.address, 0)

    """
    takes a boolean as argument
    """

    def set_backlight(self, on):
        if on:
            self.send_cmd([0x13])
        else:
            self.send_cmd([0x14])

    """
    returns an int where each bit represents the state of a key on the keypad.
    the 16 bits returned map to the following buttons:
    0000#0*987654321
    """

    def get_keypad_raw_state(self):
        with self.lcd_mutex:
            temp = self.bus.read_byte_data(self.address, 2) * 256 + self.bus.read_byte_data(self.address, 1)
            return temp

    """
    prints a string on the LCD and makes sure not to overrun the buffer.
    """

    def print_str(self, string, row=0, column=0):
        if (not row == 0) and (not column == 0):
            self.move_cursor(row, column)
        ordinated_str = [ord(i) for i in string]
        self.send_cmd(ordinated_str)

    def move_cursor(self, row, col):
        self.send_cmd([3, row, col])

    """
    returns a string containing the characters pressed on the keypad
    """

    def get_keypad_buttons(self):
        raw = self.get_keypad_raw_state()
        button_list = "123456789*0#"
        buttons = ""
        mask = 1
        for i in range(12):
            if (raw & mask) == 1:
                buttons += button_list[i]
            raw = raw >> 1
        return buttons

    def get_key(self):
        try:
            raw_keypad = self.get_keypad_buttons()
        #print "raw key fetched"
        except:
            pass
        #print "exception in keys"
        else:
            #print "raw key debounce"
            #print self.raw_keypad
            for key, state in self.key_state.iteritems():
                if state == self.BUTTON_RELEASED:

                    if key in raw_keypad:                  #and is read as pressed
                        #print key
                        self.key_state[key] = self.BUTTON_PRESSED
                        return key
                else:
                    if not (key in raw_keypad):
                        self.key_state[key] = self.BUTTON_RELEASED

        return ''

    def change_custom_char(self, num, data, charname=""):
        #self.lcd.change_custom_char(0,[128,142,149,151,145,142,128,128],"clock")
        #self.send_cmd([27,self.CLOCK,128,142,149,151,145,142,128,128])#clock chr(128)
        with self.lcd_mutex:
            if not charname == "":
                self.char_dict[charname] = num

                #self.send_cmd([27,128+num*8])
                self.send_cmd([27, 128 + num] + data)
                #self.send(data)

    #returns the string that can be sent to lcd to generate the symbol corresponding to charname
    def get_char(self, charname):
        with self.lcd_mutex:
            try:
                return chr(self.char_dict[charname] + 128)
            except:
                return '?'

# Run the program
if __name__ == "__main__":
    import time

    lcd = I2CLCD.getInstance()

    lcd.change_custom_char(0, [159, 149, 159, 149, 159, 159, 159, 159], "door")
    lcd.change_custom_char(1, [128, 142, 149, 151, 145, 142, 128, 128], "clock")
    lcd.change_custom_char(2, [128, 142, 145, 145, 159, 155, 159, 159], "locked")
    lcd.change_custom_char(3, [130, 137, 133, 149, 149, 133, 137, 130], "motion")
    lcd.change_custom_char(4, [159, 145, 145, 147, 147, 145, 145, 159], "patio")
    lcd.change_custom_char(5, [140, 146, 146, 140, 128, 128, 128, 128], "deg")
    lcd.change_custom_char(6, [128, 142, 144, 144, 159, 155, 159, 159], "unlock")
    lcd.change_custom_char(7, [159, 142, 132, 142, 142, 142, 142, 142], "camera")

    lcd.print_str('01:45', 1, 1)
    lcd.print_str('System Idle', 2, 1)
    for i in range(0, 8):
        lcd.print_str(chr(i + 128), 3, i + 1)
    lcd.print_str('[o] [-]', 4, 1)

    #crap = input("PRESS ENTER TO CONTINUE.")
    """
    # horizontal scolling test
    msg='Mega Uber Long Message'
    for x in range(20,-1-len(msg),-1):
        loc=max(1,x)
        lcd.move_cursor(3,loc)
        if x>0:
        startChar=0
        else:
        startChar=-x+1

        if (x+len(msg))>=20:
        endChar=20-x+1
        else:
        endChar=len(msg)
        lcd.clr_line()
        lcd.send(msg[startChar:endChar])
        time.sleep(0.15)
    """

    lcd.set_backlight(True)
    time.sleep(.5)
    lcd.set_backlight(False)
    time.sleep(.5)
    lcd.set_backlight(True)
    time.sleep(.5)
    lcd.set_backlight(False)
    time.sleep(.5)
    lcd.set_backlight(True)

    while (True):
        c = lcd.get_key()
        if c <> "":
            lcd.print_str(c)
            print c
        time.sleep(.1)

