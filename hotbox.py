import logging
import threading
import time
import json
import temp_sensor
from relay import Relay
import firebase_db

module_logger = logging.getLogger('main.hotbox')
max_temp_c = 72
interval = 15

heat_pin = 29
vacuum_pin = 30


class Hotbox(object):
    def __init__(self):
        self._program = {}
        self._hold_timer = None
        self._step_timer = None
        self._heat_timer = None
        self._record_timer = None
        self._history = []
        self._lamp_on_time = 0
        self._lamp_on_temp = 0
        self._program_start_time = 0.0
        self._step_start_time = 0.0
        self._record_start_time = 0.0
        self._lamp_relay = Relay(heat_pin)
        self._pump_relay = Relay(vacuum_pin)
        self._callback = None
        self._recording = False
        self._last_temp = 0.0

    def start(self):
        if not self.recording:
            self.record()

    def start_heat(self, temp, run_time):
        self.step_start_time = time.perf_counter()
        if run_time is None or run_time == 0:
            run_time = 1800
        firebase_db.heat(temp, run_time)
        firebase_db.save_status()
        self.hold_step()
        if self.heat_timer is not None:
            self.heat_timer.cancel()
            self.heat_timer = None
        self.heat_timer = threading.Timer(run_time, self.stop_heat)
        self.heat_timer.start()

    def stop_heat(self):
        self.lamp_relay.force_off()
        firebase_db.lamp_on(False)
        self.step_start_time = 0
        firebase_db.heat()
        firebase_db.save_status()
        if self.heat_timer is not None:
            self.heat_timer.cancel()
            self.heat_timer = None
        if self.hold_timer is not None:
            self.hold_timer.cancel()
            self.hold_timer = None

    def start_vacuum(self, run_time):
        module_logger.debug(f'start_vacuum({str(run_time)})')
        if run_time is None:
            run_time = 1800
        self.pump_relay.run_time = run_time
        self.pump_relay.callback = self.stop_vacuum
        self.pump_relay.on()
        firebase_db.pump_on(True)
        firebase_db.vacuum(run_time)
        firebase_db.save_status()
        if not self.recording:
            self.record()

    def stop_vacuum(self):
        module_logger.debug("stop_vacuum()")
        self.pump_relay.force_off()
        firebase_db.pump_on(False)
        firebase_db.vacuum()
        firebase_db.save_status()

    def run_program(self, name):
        module_logger.info(f"Program.run({name})")
        found = False
        for key, value in firebase_db.programs:
            print(key)
            if key == name:
                self.program = value
                found = True
                firebase_db.program(key, 0, value)
                break
        if found:
            threading.Timer(0.1, self.start_program).start()
            module_logger.info(f"Program {name} Started")
            return [200, f"Program {name} Started"]
        else:
            module_logger.error(f"Program {name} Not Found")
            return [400, f"Program {name} Not Found"]

    def start_program(self):
        if not self.recording:
            self.record()
        self.program_start_time = time.perf_counter()
        self.hold_timer.cancel()
        self.hold_timer = None
        if 'heat' in firebase_db.status:
            self.stop_heat()
        if 'vacuum' in firebase_db.status:
            self.stop_vacuum()
        self.run_step()

    def end_program(self):
        self.program_start_time = 0
        if self.hold_timer is not None:
            self.hold_timer.cancel()
            self.hold_timer = None
        if self.step_timer is not None:
            self.step_timer.cancel()
            self.step_timer = None
        self.lamp_relay.force_off()
        self.pump_relay.force_off()
        firebase_db.program()
        module_logger.info(f"Program Ended")
        if self.callback is not None:
            self.callback()

    def run_step(self):
        self.step_start_time = None
        if 'program' in firebase_db.status and firebase_db.status['program']['step'] < firebase_db.status['program']['stepCnt']:
            for key, value in self.program:
                if key == firebase_db.status['program']['step']:
                    self.step_start_time = time.perf_counter()
                    firebase_db.program_step(key, value)
                    t = value['timeSet']
                    self.step_timer = threading.Timer(t, self.run_step)
                    self.step_timer.start()
                    if self.hold_timer is not None:
                        self.hold_timer.cancel()
                        self.hold_timer = None
                    self.hold_step()
                    if value['pumpOn']:
                        self.pump_relay.run_time = t
                        if not self.pump_relay.is_on:
                            self.pump_relay.on()
                    firebase_db.pump_on(self.pump_relay.is_on)
            module_logger.debug(json.dumps(self.repr_json(), cls=ComplexEncoder))
            if 'program' not in firebase_db.status:
                self.end_program()
        else:
            self.end_program()

    def hold_step(self):
        t = get_temp()
        if self.lamp_relay.is_on:
            if self._lamp_on_temp == 0:
                self._lamp_on_temp = t[0]
            self._lamp_on_time = self._lamp_on_time + interval
        else:
            self._lamp_on_time = 0
            self._lamp_on_temp = 0
        if self._lamp_on_time >= 300 and t[0] <= self._lamp_on_temp + 5:
            temp_change = t[0] - self._lamp_on_temp
            module_logger.error(f'EMERGENCY STOP PROGRAM. 5 min temp change {temp_change} deg C.')
            self.end_program()
        firebase_db.temperature(t[0])
        firebase_db.humidity(t[1])
        if firebase_db.hold_temp() > 0:
            t_h = firebase_db.hold_temp() + 1.0
            t_l = firebase_db.hold_temp() - 1.0
            t = firebase_db.temperature()
            if t > max_temp_c:
                self.lamp_relay.force_off()
            else:
                if t > t_h:
                    self.lamp_relay.force_off()
                elif t < t_l and not self.lamp_relay.is_on:
                    self.lamp_relay.on()
            firebase_db.lamp_on(self.lamp_relay.is_on)
        firebase_db.save_status()
        self.hold_timer = threading.Timer(interval, self.hold_step)
        self.hold_timer.start()

    def record(self):
        self.recording = True
        if not self.recording:
            #self.status.history.clear()
            self.record_start_time = time.perf_counter()
        history = History()
        #status = self.status
        history.heat = self.lamp_relay.is_on
        history.vacuum = self.pump_relay.is_on
        #history.temp = status.temperature
        history.time = int(time.perf_counter() - self.record_start_time)
        #history.target_temp = status.hold_temperature
        #status.recording_time = history.time
        #status.add_history(history)
        self.record_timer = threading.Timer(interval, self.record)
        self.record_timer.start()

    def stop_record(self):
        self.recording = False
        if self.record_timer is not None:
            self.record_timer.cancel()
            self.record_timer = None

    @property
    def record_timer(self):
        return self._record_timer

    @property
    def hold_timer(self):
        return self._hold_timer

    @property
    def step_timer(self):
        return self._step_timer

    @property
    def heat_timer(self):
        return self._heat_timer

    @property
    def history(self):
        return self._history

    @property
    def program_start_time(self):
        return self._program_start_time

    @property
    def step_start_time(self):
        return self._step_start_time

    @property
    def record_start_time(self):
        return self._record_start_time

    @property
    def lamp_relay(self):
        return self._lamp_relay

    @property
    def pump_relay(self):
        return self._pump_relay

    @property
    def recording(self):
        return self._recording

    @property
    def program(self):
        return self._program

    @property
    def callback(self):
        return self._callback

    @record_timer.setter
    def record_timer(self, record_timer):
        self._record_timer = record_timer

    @hold_timer.setter
    def hold_timer(self, hold_timer):
        self._hold_timer = hold_timer

    @step_timer.setter
    def step_timer(self, step_timer):
        self._step_timer = step_timer

    @heat_timer.setter
    def heat_timer(self, heat_timer):
        self._heat_timer = heat_timer

    @history.setter
    def history(self, history):
        self._history = history

    @program_start_time.setter
    def program_start_time(self, program_start_time):
        self._program_start_time = program_start_time

    @step_start_time.setter
    def step_start_time(self, step_start_time):
        self._step_start_time = step_start_time

    @record_start_time.setter
    def record_start_time(self, record_start_time):
        self._record_start_time = record_start_time

    @lamp_relay.setter
    def lamp_relay(self, heat):
        self._lamp_relay = heat

    @pump_relay.setter
    def pump_relay(self, vacuum):
        self._pump_relay = vacuum

    @recording.setter
    def recording(self, recording):
        self._recording = recording

    @program.setter
    def program(self, program):
        self._program = program

    @callback.setter
    def callback(self, callback):
        self._callback = callback
