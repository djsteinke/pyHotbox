import smbus
import time
import threading
import logging

bus = smbus.SMBus(1)
config = [0x08, 0x00]

temperature = 0.0
humidity = 0.0

refresh_rate = 5

timer = None

module_logger = logging.getLogger('temp_sensor')


def check_temp():
    global temperature, humidity, timer
    temp_c = 80
    humid = 0
    try:
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
    except:
        pass
    temperature = round(temp_c, 1)
    humidity = round(humid, 0)
    # module_logger.debug(f'T[{str(temperature)}] H[{str(humidity)}]')
    timer = threading.Timer(refresh_rate, check_temp)
    timer.start()


def start():
    global timer
    module_logger.debug("start()")
    if timer is None:
        module_logger.debug("was not running... starting")
        timer = threading.Timer(refresh_rate, check_temp)
        timer.start()


def stop():
    global timer
    module_logger.debug("stop()")
    if timer is not None:
        module_logger.debug("was running... stopping")
        timer.cancel()
