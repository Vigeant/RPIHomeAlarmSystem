#! /usr/bin/python
# Example routines for using the BV4618 I2C interface
#
# This is required first
# sudo apt-get install python-smbus 
#
import smbus
import time
 
bus = smbus.SMBus(1)
adr = 0x31

# ------------------------------------------------------------------------------
# generic, sends text to I2C bus.
# ------------------------------------------------------------------------------
def Send(data): 
    for a in range(0,len(data)):
	   bus.write_byte(adr,ord(data[a]))

# ------------------------------------------------------------------------------
# all commands are preceeded by escape
# ------------------------------------------------------------------------------
def Cmd(command):
    bus.write_byte(adr,27)
    bus.write_byte(adr,command)
    time.sleep(0.05) # no clock stretching here either

# ------------------------------------------------------------------------------
# moves cursor to a position
# ------------------------------------------------------------------------------
def CursorRC(row,col):
    Cmd(0x24)
    bus.write_byte(adr,row)
    bus.write_byte(adr,col)

# ------------------------------------------------------------------------------
# simple demonstartion
# ------------------------------------------------------------------------------
def Demo():
    Cmd(0x50) # clear screen
    Send('Hello')
    Cmd(0x25) # cursor home
    Cmd(0x21) # cursor down 1
    Send('World')

# ******************************************************************************
# Input
# This works but not correctly because as far as I know you can't read after
# sending 2 bytes, just the one so this causes bit 8 to be always set high.
# ******************************************************************************

# ------------------------------------------------------------------------------
# returns the scan code of the key that was pressed, returns 0x80 if no keys
# in buffer
# ------------------------------------------------------------------------------
def Key():
    Cmd(0x11)
    print hex(bus.read_byte(adr))


