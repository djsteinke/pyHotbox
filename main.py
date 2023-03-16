import logging
import temp_sensor
import threading
import time
import firebase_db
from datetime import datetime, timezone
from relay import Relay

logger = logging.getLogger('main')
logger.setLevel(logging.DEBUG)
# create file handler which logs even debug messages
fh = logging.FileHandler('/home/pi/projects/pyHotbox/log.log')
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

heat_pin = 16
vacuum_pin = 18
fan_pin = 22

max_temp_c = 72
interval = 5
status_update_cnt = 0

program = {}
step = {}
hold_timer = None
step_timer = None
record_timer = None
running = False

lamp_on_time = 0
lamp_on_temp = 0
program_start_time = 0.0
step_start_time = 0.0
record_start_time = 0.0
lamp_relay = Relay(heat_pin, True)
pump_relay = Relay(vacuum_pin, True)
fan_relay = Relay(fan_pin, True)
callback = None
last_temp = 0.0


def record():
    global record_timer
    if not running:
        t = [temp_sensor.temperature, temp_sensor.humidity]
        firebase_db.get_temperature(t[0])
        firebase_db.get_humidity(t[1])
    history = {"time": round(datetime.utcnow().timestamp()),
               "temperature": firebase_db.get_temperature(),
               "humidity": firebase_db.get_humidity(),
               "pumpOn": firebase_db.is_pump_on(),
               "lampOn": firebase_db.is_lamp_on()}
    logger.debug("record: " + str(history))
    # TODO FbDB push history
    record_interval = 15
    #if not running:
    #    record_interval = 300
    if firebase_db.get_humidity() != 0.0:
        firebase_db.add_history(history)
    #else:
    #    record_interval = 15
    if record_timer is not None and record_timer.isAlive():
        record_timer.cancel()
    record_timer = threading.Timer(record_interval, record)
    record_timer.start()


def run_program(name):
    global program, record_timer
    logger.info(f"run_program({name})")
    found = False
    for p in firebase_db.programs:
        if p['name'] == name:
            program = p
            firebase_db.status['program'] = name
            step_cnt = len(program['steps'])
            firebase_db.status['stepCnt'] = step_cnt
            firebase_db.save_status()
            found = True
            break
    if found:
        if record_timer is not None and record_timer.isAlive():
            record_timer.cancel()
        record_timer = threading.Timer(1, record)
        record_timer.start()
        threading.Timer(0.1, start_program).start()
        logger.info(f"Program {name} Started")
        # TODO update status
    else:
        logger.error(f"Program {name} Not Found")
        # TODO update status


def start_program():
    global hold_timer, program_start_time, running
    running = True
    program_start_time = time.perf_counter()
    if hold_timer is not None:
        hold_timer.cancel()
    firebase_db.status['startTime'] = round(datetime.utcnow().timestamp())
    run_step()


def end_program():
    global program_start_time, hold_timer, step_timer, program, step, running
    if hold_timer is not None:
        hold_timer.cancel()
    if step_timer is not None:
        step_timer.cancel()
    program_start_time = 0
    firebase_db.status['step'] = -1
    program = {}
    step = {}
    lamp_relay.force_off()
    pump_relay.force_off()
    fan_relay.force_off()
    firebase_db.status['step'] = -1
    firebase_db.status['program'] = "none"
    firebase_db.status['stepCnt'] = 0
    firebase_db.status['startTime'] = 0
    firebase_db.is_pump_on(pump_relay.is_on)
    firebase_db.is_lamp_on(lamp_relay.is_on)
    firebase_db.save_status()
    firebase_db.set_running("none")
    running = False
    logger.info(f"Program Ended")


def run_step():
    global step_start_time, step_timer, step
    step_start_time = 0.0
    firebase_db.status['step'] = firebase_db.status['step'] + 1
    if firebase_db.status['step'] < firebase_db.status['stepCnt']:
        value = program['steps'][firebase_db.status['step']]
        step = value
        step_start_time = time.perf_counter()
        t = value['runTime'] * 60
        step_timer = threading.Timer(t, run_step)
        step_timer.start()
        if hold_timer is not None:
            hold_timer.cancel()
        hold_step()
        if value['pumpOn']:
            pump_relay.run_time = t
            if not pump_relay.is_on:
                pump_relay.on()
        fan_relay.run_time = t-10
        fan_relay.on()
        firebase_db.is_pump_on(pump_relay.is_on)
        firebase_db.save_status()
    else:
        end_program()


def hold_step():
    global lamp_on_temp, lamp_on_time, hold_timer, status_update_cnt
    t = [temp_sensor.temperature, temp_sensor.humidity]
    if lamp_relay.is_on:
        if lamp_on_temp == 0:
            lamp_on_temp = t[0]
        lamp_on_time = lamp_on_time + interval
    else:
        lamp_on_time = 0
        lamp_on_temp = 0
    if lamp_on_time >= 300 and t[0] <= lamp_on_temp + 5:
        temp_change = round(t[0] - lamp_on_temp, 1)
        logger.error(f'EMERGENCY STOP PROGRAM. 5 min temp change {temp_change} deg C.')
        end_program()
        return
    firebase_db.get_temperature(t[0])
    firebase_db.get_humidity(t[1])
    if step["setTemp"] > 0:
        t_h = step["setTemp"] + 1.0
        t_l = step["setTemp"] - 1.0
        temp = temp_sensor.temperature
        if temp > max_temp_c:
            lamp_relay.force_off()
        else:
            if temp > t_h:
                lamp_relay.force_off()
            elif temp < t_l and not lamp_relay.is_on:
                lamp_relay.on()
        firebase_db.is_lamp_on(lamp_relay.is_on)
    status_update_cnt += 1
    if status_update_cnt >= 3:
        firebase_db.save_status()
        status_update_cnt = 0
    hold_timer = threading.Timer(interval, hold_step)
    hold_timer.start()


def runaway_heat():
    if temp_sensor.temperature > max_temp_c:
        logger.error(f'EMERGENCY STOP HEAT.  Error reading sensor.')
        lamp_relay.force_off()
    threading.Timer(60, runaway_heat).start()


def trigger_action(action):
    if action == "none":
        logger.debug("program stopped")
        end_program()
    else:
        run_program(action)


if __name__ == '__main__':
    logger.debug("Start Application")
    logger.debug("Start temp_sensor")
    temp_sensor.start()
    logger.debug("callback")
    firebase_db.callback = trigger_action
    logger.debug("Start firebase_db")
    threading.Timer(0.1, firebase_db.start_listeners).start()
    logger.debug("Start record()")
    threading.Timer(1, record).start()
    logger.debug("Start runaway_heat()")
    threading.Timer(60, runaway_heat).start()


