import logging
import temp_sensor
import threading
import time
import firebase_db
from relay import Relay

# create logger with 'spam_application'
logger = logging.getLogger('main')
logger.setLevel(logging.DEBUG)
# create file handler which logs even debug messages
fh = logging.FileHandler('log.log')
fh.setLevel(logging.DEBUG)
# create console handler with a higher log level
ch = logging.StreamHandler()
ch.setLevel(logging.ERROR)
# create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
ch.setFormatter(formatter)
# add the handlers to the logger
logger.addHandler(fh)
logger.addHandler(ch)

heat_pin = 29
vacuum_pin = 30

max_temp_c = 72
interval = 5

program = {}
step = {}
hold_timer: threading.Timer
step_timer: threading.Timer
record_timer: threading.Timer

lamp_on_time = 0
lamp_on_temp = 0
program_start_time = 0.0
step_start_time = 0.0
record_start_time = 0.0
lamp_relay = Relay(heat_pin)
pump_relay = Relay(vacuum_pin)
callback = None
last_temp = 0.0


def record():
    global record_timer
    history = {"time": "",
               "temp": temp_sensor.temperature,
               "humidity": temp_sensor.humidity,
               "pumpOn": False,
               "lampOn": False}
    # history.time = int(time.perf_counter() - self.record_start_time)
    # TODO FbDB push history
    record_timer = threading.Timer(interval, record)
    record_timer.start()


def run_program(name):
    global program
    logger.info(f"run_program({name})")
    found = False
    for key, value in firebase_db.programs:
        print(key)
        if key == name:
            program = value
            firebase_db.status['program'] = key
            step_cnt = len(program['steps'])
            firebase_db.status['stepCnt'] = step_cnt
            found = True
            break
    if found:
        threading.Timer(0.1, start_program).start()
        logger.info(f"Program {name} Started")
        # TODO update status
    else:
        logger.error(f"Program {name} Not Found")
        # TODO update status


def start_program():
    global hold_timer, program_start_time
    program_start_time = time.perf_counter()
    hold_timer.cancel()
    run_step()


def end_program():
    global program_start_time, hold_timer, step_timer
    program_start_time = 0
    hold_timer.cancel()
    step_timer.cancel()
    lamp_relay.force_off()
    pump_relay.force_off()
    logger.info(f"Program Ended")


def run_step():
    global step_start_time, step_timer, step
    step_start_time = 0.0
    if firebase_db.status['step'] < firebase_db.status['stepCnt']:
        for key, value in program['steps']:
            if key == firebase_db.status['step']:
                step = value
                step_start_time = time.perf_counter()
                t = value['runTime'] * 60
                step_timer = threading.Timer(t, run_step)
                step_timer.start()
                hold_timer.cancel()
                hold_step()
                if value['pumpOn']:
                    pump_relay.run_time = t
                    if not pump_relay.is_on:
                        pump_relay.on()
                firebase_db.pump_on(pump_relay.is_on)
    else:
        end_program()


def hold_step():
    global lamp_on_temp, lamp_on_time, hold_timer
    t = temp_sensor.temperature
    if lamp_relay.is_on:
        if lamp_on_temp == 0:
            lamp_on_temp = t[0]
        lamp_on_time = lamp_on_time + interval
    else:
        lamp_on_time = 0
        lamp_on_temp = 0
    if lamp_on_time >= 300 and t[0] <= lamp_on_temp + 5:
        temp_change = t[0] - lamp_on_temp
        logger.error(f'EMERGENCY STOP PROGRAM. 5 min temp change {temp_change} deg C.')
        end_program()
    firebase_db.temperature(t[0])
    firebase_db.humidity(t[1])
    if step["setTemp"] > 0:
        t_h = step["setTemp"] + 1.0
        t_l = step["setTemp"] - 1.0
        t = temp_sensor.temperature()
        if t > max_temp_c:
            lamp_relay.force_off()
        else:
            if t > t_h:
                lamp_relay.force_off()
            elif t < t_l and not lamp_relay.is_on:
                lamp_relay.on()
        firebase_db.lamp_on(lamp_relay.is_on)
    firebase_db.save_status()
    hold_timer = threading.Timer(interval, hold_step)
    hold_timer.start()


def trigger_action(action):
    if action == "stop":
        end_program()
    else:
        run_program(action)


if __name__ == '__main__':
    temp_sensor.start()
    firebase_db.callback = trigger_action
    threading.Timer(0.1, firebase_db.start_programs_listener).start()
    threading.Timer(0.1, record).start()

