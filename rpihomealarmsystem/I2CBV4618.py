#! /usr/bin/python
# BV4618 I2C interface
#
# 
# sudo apt-get install python-smbus 
#
import smbus
import time
from singletonmixin import Singleton
from threading import RLock


class I2CBV4618(Singleton):
    def __init__(self, adr=0x31):

        self.char_dict = {}
        self.delay = 0.03

        self.mutex = RLock()
        self.bus = smbus.SMBus(1)
        self.adr = adr
        self.rows = 4
        self.columns = 20
        self.init()

    def init(self):
        self.char_dict = {}
        with self.mutex:
            self.reset_LCD()
            self.define_LCD_size(self.rows, self.columns)
            self.show_cursor(False)    #remove blinking cursor        
            self.clr_scrn()
            self.set_debounce(60)
            self.set_scrolling_enabled(False)

    # ------------------------------------------------------------------------------
    # all commands are preceeded by escape
    # ------------------------------------------------------------------------------
    def send_cmd(self, cmd, delay=True):
        with self.mutex:
            self.bus.write_i2c_block_data(self.adr, 0x1b, cmd)
            if delay:
                time.sleep(self.delay)

    # ------------------------------------------------------------------------------
    # generic, sends text to I2C bus.
    # ------------------------------------------------------------------------------
    def send(self, data):
        with self.mutex:
            for a in range(0, len(data)):
                self.bus.write_byte(self.adr, data[a])
                #time.sleep(self.delay)

    def print_str(self, string, row=0, column=0):
        with self.mutex:
            if (not row == 0) and (not column == 0):
                self.move_cursor(row, column)
            ordinated_str = [ord(i) for i in string]
            self.send(ordinated_str)

    def print_line(self, data, row=0, centered=False, clr=False):
        with self.mutex:
            if row <> 0:
                self.move_cursor(row, 1)
            if clr:
                self.clr_line()
            if centered:
                if (len(data) <= self.columns):
                    start = self.columns / 2 - len(data) / 2
                    self.move_cursor(row, start)
                else:
                    self.move_cursor(row, 1)
                    data = data[0:min(len(data), self.columns)]
            self.print_str(data)
            self.cr()

    def clr_scrn(self):
        self.send_cmd([0x50])

    def clr_line(self, row=0):
        with self.mutex:
            if row <> 0:
                self.move_cursor(row, 1)
                self.send_cmd([0x53])

    # ------------------------------------------------------------------------------
    # moves cursor to a position
    # ------------------------------------------------------------------------------
    def move_cursor(self, row, col):
        self.send_cmd([0x24, row, col])

    def move_cursor_home(self):
        self.send_cmd([0x25])

    def move_cursor_up(self):
        self.send_cmd([0x20])

    def move_cursor_down(self):
        self.send_cmd([0x21])

    def move_cursor_left(self):
        self.send_cmd([0x23])

    def move_cursor_right(self):
        self.send_cmd([0x22])

    def cr(self):
        with self.mutex:
            self.send_cmd([0xd])
            self.send_cmd([0xa])

    def keypad_buffer(self):
        with self.mutex:
            self.send_cmd([0x10], delay=True)
            tmp = (self.bus.read_byte(self.adr) ^ 128)
            #time.sleep(self.delay)
        return tmp

    def get_key_raw(self):
        with self.mutex:
            self.send_cmd([0x11], delay=True)
            tmp = self.bus.read_byte(self.adr) ^ 128
            #time.sleep(self.delay)
        return tmp

    key_dict = {110: '1', 94: '2', 62: '3', 109: '4', 93: '5', 61: '6', 107: '7', 91: '8', 59: '9', 103: '*', 87: '0',
                55: '#'}

    def get_key(self):
        tmp = self.get_key_raw()
        if tmp == 0:
            return ''
        return self.key_dict[tmp]

    def define_LCD_size(self, row, col):
        with self.mutex:
            self.send_cmd([0x30, row])
            self.send_cmd([0x31, col])

    def set_scrolling_enabled(self, on):
        if on:
            self.send_cmd([0x45, 0])
        else:
            self.send_cmd([0x45, 1])


    def set_backlight(self, on):
        with self.mutex:
            if on:
                self.send_cmd([0x03, 0x01])
            else:
                self.send_cmd([0x03, 0x00])
            time.sleep(.1)

    def set_debounce(self, value):
        self.send_cmd([0x15, value])

    def show_cursor(self, on):
        if on:
            self.send_cmd([0x01, 0x0e])
        else:
            self.send_cmd([0x01, 0x0c])

    def change_custom_char(self, num, data, charname=""):
        with self.mutex:
            if not charname == "":
                self.char_dict[charname] = num
            self.send_cmd([0x01, 64 + num * 8])
            self.send(data)
            #self.send_cmd([0x01,128]) #Document is not clear about the requirement for this or not.  Suspecting it is not required. 
            time.sleep(.3)

    def print_char(self, char):
        self.send([char])

    #returns the string that can be sent to lcd to generate the symbol corresponding to charname
    def get_char(self, charname):
        with self.mutex:
            try:
                return chr(self.char_dict[charname])
            except:
                return '?'

    def reset_LCD(self):
        with self.mutex:
            self.send_cmd([0x43])
            time.sleep(2)

# Run the program
if __name__ == "__main__":

    lcd = I2CBV4618.getInstance()

    lcd.change_custom_char(0, [159, 149, 159, 149, 159, 159, 159, 159], "door")
    lcd.change_custom_char(1, [128, 142, 149, 151, 145, 142, 128, 128], "clock")
    lcd.change_custom_char(2, [128, 142, 145, 145, 159, 155, 159, 159], "locked")
    lcd.change_custom_char(3, [130, 137, 133, 149, 149, 133, 137, 130], "motion")
    lcd.change_custom_char(4, [159, 145, 145, 147, 147, 145, 145, 159], "patio")
    lcd.change_custom_char(5, [140, 146, 146, 140, 128, 128, 128, 128], "deg")
    lcd.change_custom_char(6, [128, 142, 144, 144, 159, 155, 159, 159], "unlock")
    lcd.change_custom_char(7, [159, 142, 132, 142, 142, 142, 142, 142], "camera")

    lcd.print_line('01:45', 1)
    lcd.print_line('System Idle', 2, True)
    lcd.move_cursor(3, 1)
    for i in range(0, 8):
        lcd.print_char(i)
        lcd.print_char(i)
    lcd.cr()
    lcd.print_line('[o] [-]', 4)

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

    while (True):
        while not lcd.keypad_buffer():
            time.sleep(.2)

        c = lcd.get_key()
        lcd.print_str(c)
        print c

 
    
