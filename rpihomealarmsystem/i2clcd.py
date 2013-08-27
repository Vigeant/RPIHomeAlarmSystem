import smbus
from singletonmixin import Singleton
from threading import RLock

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

"""


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
        
        
    def init(self):
        self.clr_scrn()
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

    
    def clr_scrn(self):
        self.send_cmd([0x0C])

    """
    Send a command to the LCD.
    """
    def send_cmd(self,cmd):
        with self.lcd_mutex:
            while len(cmd) > 0:
                room = self.get_buffer_room()
                endIndex = min(len(cmd),room,31)
                self.bus.write_i2c_block_data(self.address, 0x00, cmd[0:endIndex])
                cmd = cmd[endIndex:]

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
        if on :
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
            temp = self.bus.read_byte_data(self.address, 2)*256 + self.bus.read_byte_data(self.address, 1)
        return temp

    """
    returns a string containing the characters pressed on the keypad
    """
    def get_keypad_buttons(self):
        raw =  self.get_keypad_raw_state()
        button_list = "123456789*0#"
        buttons = ""
        mask = 1
        for i in range(12):
            if (raw & mask)==1:
                buttons += button_list[i]
            raw = raw>>1
        return buttons

    """
    prints a string on the LCD and makes sure not to overrun the buffer.
    """
    def print_str(self, s):
        ordinated_s = [ord(i) for i in s]
        self.send_cmd(ordinated_s)

    def do_north(self):
        if not self.current_symbol == 'north':
            self.send_cmd([27,135,132,142,149,132,132,128,128,128])#arrow chr(135)
            self.current_symbol = 'north'

    def do_north_east(self):
        if not self.current_symbol == 'north_east':
            self.send_cmd([27,135,143,131,133,137,144,128,128,128])#arrow chr(135)
            self.current_symbol = 'north_east'

    def do_east(self):
        if not self.current_symbol == 'east':
            self.send_cmd([27,135,132,130,159,1130,132,128,128,128])#arrow chr(135)
            self.current_symbol = 'east'

    def do_south_east(self):
        if not self.current_symbol == 'south_east':
            self.send_cmd([27,135,144,137,133,131,143,128,128,128])#arrow chr(135)
            self.current_symbol = 'south_east'

    def do_south(self):
        if not self.current_symbol == 'south':
            self.send_cmd([27,135,132,132,149,142,132,128,128,128])#arrow chr(135)
            self.current_symbol = 'south'

    def do_south_west(self):
        if not self.current_symbol == 'south_west':
            self.send_cmd([27,135,129,146,148,152,158,128,128,128])#arrow chr(135)
            self.current_symbol = 'south_west'

    def do_west(self):
        if not self.current_symbol == 'west':
            self.send_cmd([27,135,132,136,159,136,132,128,128,128])#arrow chr(135)
            self.current_symbol = 'west'

    def do_north_west(self):
        if not self.current_symbol == 'north_west':
            self.send_cmd([27,135,158,152,148,146,129,128,128,128])#arrow chr(135)
            self.current_symbol = 'north_west'

    
    def get_char(self,char_name):
        if char_name == 'NORTH':self.do_north()
        elif char_name =='NORTH_EAST':self.do_north_east()
        elif char_name =='EAST':self.do_east()
        elif char_name =='SOUTH_EAST':self.do_south_east()
        elif char_name =='SOUTH':self.do_south()
        elif char_name =='SOUTH_WEST':self.do_south_west()
        elif char_name =='WEST':self.do_west()
        elif char_name =='NORTH_WEST':self.do_north_west()
            
        return {
            'CLOCK':chr(128),
            'DEG':chr(129),
            'LOCKED':chr(130),
            'UNLOCKED':chr(131),
            'DOOR':chr(132),
            'CAMERA':chr(133),
			'MS1':chr(133),
			'MS2':chr(133),
			'MS3':chr(133),
            'PATIO':chr(134),
            'GARAGE':'G',
			'NORTH':chr(135),
			'NORTH_EAST':chr(135),
			'EAST':chr(135),
			'SOUTH_EAST':chr(135),
			'SOUTH':chr(135),
			'SOUTH_WEST':chr(135),
			'WEST':chr(135),
			'NORTH_WEST':chr(135)}.get(char_name, chr(135))
            


