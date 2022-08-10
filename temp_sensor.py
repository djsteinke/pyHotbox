from typing import Callable

import smbus
import time
import threading

bus = smbus.SMBus(1)
config = [0x08, 0x00]

temperature = 0.0
humidity = 0.0

refresh_rate = 5
timer = None


def check_temp():
    global temperature, humidity, timer
    bus.write_i2c_block_data(0x38, 0xE1, config)
    byt = bus.read_byte(0x38)
    measure_cmd = [0x33, 0x00]
    bus.write_i2c_block_data(0x38, 0xAC, measure_cmd)
    time.sleep(0.5)
    data = bus.read_i2c_block_data(0x38, 0x00)
    temp_raw = ((data[3] & 0x0F) << 16) | (data[4] << 8) | data[5]
    temp_c = ((temp_raw*200) / 1048576) - 50
    humid_raw = ((data[1] << 16) | (data[2] << 8) | data[3]) >> 4
    humid = humid_raw * 100 / 1048576
    temperature = round(temp_c, 1)
    humidity = round(humid, 1)
    timer = threading.Timer(refresh_rate, check_temp)
    timer.start()


def start():
    global timer
    if timer is None:
        timer = threading.Timer(0.1, check_temp)
        timer.start()


def stop():
    global timer
    if timer is not None:
        timer.cancel()
        timer = None
