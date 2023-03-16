import threading

from firebase_admin import db, credentials, initialize_app
from firebase_admin.exceptions import FirebaseError
import logging
from time import sleep
import os
from urllib import request
from datetime import datetime

"""
{
    "running": "none", 
    "status": {
        "temp": 40.1, 
        "humidity": 40,
        "pumpOn": false, 
        "lampOn": false, 
        "program": "none", 
        "startTime": 0,
        "step": 0, 
        "stepCnt": 0
    }, 
    "programs": {
        "shoe": {
            "name": "shoe", 
            "desc": "for shoes", 
            "steps": {
                "0": {
                    "runTime": 60,  # mins
                    "setTemp": 60,  # deg C
                    "pumpOn": true  # vacuum
                },
                "1": {
                    "runTime": 60, 
                    "setTemp": 60,
                    "pumpOn": false
                }
            }
        }
    }
}
"""

module_logger = logging.getLogger('main.firebase_db')

databaseURL = "https://rn5notifications-default-rtdb.firebaseio.com/"
appKey = "hotbox"

# key_dir = os.path.dirname(os.getcwd()) + "/firebaseKey.json"
# key_dir = "C:\\MyData\\Program Files\\PyCharm\\rn5notificationsKey.json"
key_dir = "/home/pi/firebaseKey.json"
cred_obj = credentials.Certificate(key_dir)

initialize_app(cred_obj, {
    'databaseURL': databaseURL
})

ref = db.reference(appKey)
status_ref = ref.child("status")
programs_ref = ref.child("programs")
running_ref = ref.child("running")
history_ref = ref.child("history")
running_stream = None
programs_stream = None

status = status_ref.get()
db_status = status
programs = programs_ref.get()
running = "none"

network_up = True
reset_stream = True


def placeholder(val):
    return val


callback = placeholder("placeholder")


temperature = 0.0
humidity = 0.0
lamp_on = False
pump_on = False
histories = []


def add_history(history_in):
    histories.append(history_in)
    if network_up:
        for history in list(histories):
            try:
                history_ref.push(history)
                history_max = round(datetime.utcnow().timestamp()) - (3600*4)      # 4hrs of history
                # snapshot = history_ref.order_by_key().limit_to_last(1).get()
                snapshot = history_ref.order_by_key().limit_to_first(10).get()
                # module_logger.debug("remove everything before: " + str(history_max))
                # module_logger.debug(len(snapshot.items()))
                # 4 hrs of history
                for key, val in snapshot.items():
                    if val['time'] < history_max:
                        # module_logger.debug("remove child... " + str(val))
                        history_ref.child(key).delete()
                histories.remove(history)
            except Exception as e:
                module_logger.error("update history failed. try again.", str(e))


def internet_on():
    global network_up, reset_stream
    while True:
        try:
            request.urlopen("http://google.com")
            if not network_up:
                module_logger.info('Network UP.')
            network_up = True
            return network_up
        except:
            if network_up:
                module_logger.error('Network DOWN!!!')
            network_up = False
            reset_stream = True
        sleep(15)


def save_status():
    if network_up:
        status_ref.update(status)
    else:
        threading.Timer(180, save_status).start()


def get_temperature(t=0):
    global temperature
    if t > 0:
        temperature = t
    return temperature


def get_humidity(h=0):
    global humidity
    if h > 0:
        humidity = h
    return humidity


def is_lamp_on(is_on=None):
    global lamp_on
    if is_on is not None:
        lamp_on = is_on
    return lamp_on


def is_pump_on(is_on=None):
    global pump_on
    if is_on is not None:
        pump_on = is_on
    return pump_on


def programs_listener(event):
    global programs
    # module_logger.debug('programs firebase listener...')
    if event.data:
        programs = programs_ref.get()
        module_logger.debug("PROGRAMS: ", programs)


def set_running(val):
    global running
    if running != val:
        running_ref.set(val)
        running = val


def running_listener(event):
    global running
    # module_logger.debug('running firebase listener...')
    if event.data:
        new_running = running_ref.get()
        if running != new_running:
            running = new_running
            if callback is not None:
                callback(running)
            module_logger.info("RUNNING: " + str(running_ref.get()))


def start_listeners():
    global running_stream, programs_stream, reset_stream
    while True:
        if internet_on():
            if reset_stream:
                try:
                    programs_stream.close()
                    module_logger.debug('programs_stream closed...')
                except:
                    module_logger.debug('programs_stream not running...')

                try:
                    running_stream.close()
                    module_logger.debug('running_stream closed...')
                except:
                    module_logger.debug('running_stream not running...')

                try:
                    running_stream = running_ref.listen(running_listener)
                    programs_stream = programs_ref.listen(programs_listener)
                    module_logger.debug('streams open...')
                    reset_stream = False
                except FirebaseError:
                    module_logger.error('failed to start listeners... ')
                    reset_stream = True
        sleep(15)


def get_programs():
    return programs
