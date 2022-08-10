from typing import Callable
from firebase_admin import db, credentials, initialize_app
from firebase_admin.exceptions import FirebaseError
import logging
from time import sleep
import os
import threading

"""
{
    "running": "none", 
    "status": {
        "temp": 40.1, 
        "humidity": 40,
        "pumpOn": false, 
        "lampOn": false, 
        "program": "none", 
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

p_dir = os.path.dirname(os.getcwd())
cred_obj = credentials.Certificate(p_dir + "/firebaseKey.json")

initialize_app(cred_obj, {
    'databaseURL': databaseURL
})

ref = db.reference(appKey)
status_ref = ref.child("status")
programs_ref = ref.child("programs")
running_ref = ref.child("running")

status = status_ref.get()
programs = programs_ref.get()
running: str

callback: Callable


def save_status():
    status_ref.update(status)


def temperature(t=-100):
    if -100 < t != status['temperature']:
        status['temperature'] = t
    else:
        t = status['temperature']
    return t


def humidity(h=-1):
    if -1 < h != status['humidity']:
        status['humidity'] = h
    else:
        h = status['humidity']
    return h


def lamp_on(is_on=None):
    if is_on is not None and status["lampOn"] != is_on:
        status["lampOn"] = is_on
    else:
        is_on = status["lampOn"]
    return is_on


def pump_on(is_on=None):
    if is_on is not None and status["pumpOn"] != is_on:
        status["pumpOn"] = is_on
    else:
        is_on = status["pumpOn"]
    return is_on


def programs_listener(event):
    global programs
    module_logger.debug('programs firebase listener...')
    if event.data:
        programs = programs_ref.get()
        module_logger.debug("PROGRAMS: ")
        module_logger.debug(programs)


def start_programs_listener():
    listening = False
    while not listening:
        try:
            module_logger.debug("Starting Programs Listener")
            programs_ref.listen(programs_listener)
            listening = True
        except FirebaseError as e:
            module_logger.error('failed to start listener... trying again.')
            module_logger.error('FirebaseError: ' + str(e))
            sleep(5)
            start_programs_listener()


def running_listener(event):
    global running
    module_logger.debug('running firebase listener...')
    if event.data:
        running = running_ref.get()
        if callback is not None:
            callback(running)
        module_logger.debug("RUNNING: " + str(running_ref.get()))


def start_running_listener():
    listening = False
    while not listening:
        try:
            module_logger.debug("Starting Running Listener")
            running_ref.listen(running_listener)
            listening = True
        except FirebaseError as e:
            module_logger.error('failed to start listener... trying again.')
            module_logger.error('FirebaseError: ' + str(e))
            sleep(5)


def get_programs():
    return programs


def start():
    start_programs_listener()
    start_running_listener()
