import logging
import threading
import time

import RPi.GPIO as GPIO

GPIO.setmode(GPIO.BOARD)
GPIO.setwarnings(False)

module_logger = logging.getLogger('main.temp_sensor')


class Relay(object):
    def __init__(self, pin, on_high=None, name=None):
        self._on = False
        self._pin = pin
        self._run_time = 0
        self._wait = 0
        self._callback = None
        self._gpio_on = GPIO.HIGH
        self._gpio_off = GPIO.LOW
        self._start_time = 0
        self._off_timer = None
        self._on_high = on_high
        self._name = name
        self.setup_pin()

    def on(self):
        if self._pin > 0:
            if self._run_time == 0:
                self._run_time = 1800
            self._on = True
            self.log(f"on() {str(self._run_time)}")
            self._start_time = time.perf_counter()
            GPIO.output(self._pin, self._gpio_on)
            if self._off_timer is None:
                self._off_timer = threading.Timer(self._run_time, self.off)
                self._off_timer.start()

    def force_off(self):
        if self._off_timer is not None:
            self._off_timer.cancel()
        self._run_time = 0
        self._wait = 0
        self.log("force_off()")
        self.off()

    def off(self):
        GPIO.output(self._pin, self._gpio_off)
        self._on = False
        self.log("off()")
        if self._callback is not None:
            timer = threading.Timer(self._wait, self._callback)
            timer.start()

    def on_time(self):
        if self._start_time == 0:
            return 0
        else:
            return int(time.perf_counter() - self._start_time)

    def setup_pin(self):
        if self._pin > 0:
            GPIO.setup(self._pin, GPIO.OUT)
            if (self._on_high is not None and not self._on_high) \
                    or (self._on_high is None and GPIO.input(self._pin) > 0):
                self._gpio_on = GPIO.LOW
                self._gpio_off = GPIO.HIGH
            self.log(f"setup_pin() pin({str(self._pin)}) gpio_on({str(self._gpio_on)})")
            GPIO.output(self._pin, self._gpio_off)

    def log(self, msg):
        module_logger.debug(f"{self._name} : {msg}")

    @property
    def pin(self):
        return self._pin

    @property
    def is_on(self):
        return self._on

    @property
    def run_time(self):
        return self._run_time

    @property
    def wait(self):
        return self._wait

    @property
    def callback(self):
        return self._callback

    @callback.setter
    def callback(self, value):
        self._callback = value

    @pin.setter
    def pin(self, value):
        if (self._pin != value) and not self._on:
            self._pin = value
            self.setup_pin()

    @run_time.setter
    def run_time(self, value):
        self._run_time = value
        if self._off_timer is not None:
            self._off_timer.cancel()
            self._off_timer = threading.Timer(self._run_time, self.off)
            self._off_timer.start()

    @wait.setter
    def wait(self, value):
        self._wait = value
