from typing import Callable
from firebase_admin import db, credentials, initialize_app
from firebase_admin.exceptions import FirebaseError
import logging
from time import sleep
import os
from urllib import request, error
from datetime import datetime, timezone

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

key_dir = os.path.dirname(os.getcwd()) + "/firebaseKey.json"
# key_dir = "C:\\MyData\\Program Files\\PyCharm\\rn5notificationsKey.json"
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

callback = None
timer = 0
network_up = True

temperature = 0.0
humidity = 0.0
lamp_on = False
pump_on = False


def add_history(history):
    history_ref.push(history)
    history_max = round(datetime.now(timezone.utc).timestamp()) - (3600*4)      # 4hrs of history
    #snapshot = history_ref.order_by_key().limit_to_last(1).get()
    snapshot = history_ref.order_by_key().limit_to_last(1).get()
    module_logger.debug("remove everything before: " + str(history_max))
    module_logger.debug(snapshot)
    # 4 hrs of history
    for key, val in snapshot.items():
        if val['time'] < history_max:
            module_logger.debug("remove child... " + val)
            history_ref.child(key).delete()


def internet_on():
    global network_up
    while True:
        try:
            request.urlopen("http://google.com")
            if not network_up:
                module_logger.debug('Network UP.')
            network_up = True
            return network_up
        except error.URLError as e:
            if network_up:
                module_logger.error('Network DOWN. Reason: ' + e.reason)
            network_up = False
        sleep(15)


def save_status():
    status_ref.update(status)


def get_temperature(t=-100):
    global temperature
    if t > 0:
        temperature = t
    return temperature


def get_humidity(h=-1):
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
    module_logger.debug('programs firebase listener...')
    if event.data:
        programs = programs_ref.get()
        module_logger.debug("PROGRAMS: ")
        module_logger.debug(programs)


def start_programs_listener():
    try:
        module_logger.debug("Starting Programs Listener")
        programs_ref.listen(programs_listener)
    except FirebaseError as e:
        module_logger.error('failed to start listener... trying again.')
        module_logger.error('FirebaseError: ' + str(e))
        sleep(5)
        start_programs_listener()


def set_running(val):
    global running
    if running != val:
        running_ref.set(val)
        running = val


def running_listener(event):
    global running
    module_logger.debug('running firebase listener...')
    if event.data:
        new_running = running_ref.get()
        if running != new_running:
            running = new_running
            if callback is not None:
                callback(running)
            module_logger.debug("RUNNING: " + str(running_ref.get()))


def start_running_listener():
    try:
        module_logger.debug("Starting Running Listener")
        running_ref.listen(running_listener)
    except FirebaseError as e:
        module_logger.error('failed to start listener... trying again.')
        module_logger.error('FirebaseError: ' + str(e))
        sleep(5)


def start_listeners():
    global timer, running_stream, programs_stream
    try:
        running_stream = running_ref.listen(running_listener)
        programs_stream = programs_ref.listen(programs_listener)
        module_logger.debug('streams open...')
    except FirebaseError as e:
        module_logger.error('failed to start listeners... ' + e.cause)

    timer = 100
    while True:
        if internet_on():
            if timer == 0:
                try:
                    running_stream.close()
                    programs_stream.close()
                    module_logger.debug('streams closed...')
                except:
                    module_logger.debug('no streams to close...')
                    pass
                try:
                    running_stream = running_ref.listen(running_listener)
                    programs_stream = programs_ref.listen(programs_listener)
                    module_logger.debug('streams open...')
                    timer = 100
                except FirebaseError as e:
                    module_logger.error('failed to start listeners... ' + e.cause)
                    timer = 0
            sleep(15)
        else:
            sleep(1)
            timer -= 1 if timer > 0 else 0


def get_programs():
    return programs


def start():
    start_programs_listener()
    start_running_listener()
