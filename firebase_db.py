import firebase_admin
from firebase_admin import db
from firebase_admin.exceptions import FirebaseError
import logging

"""
{
    "running": none, 
    "status": {
        "temp": 40.1, 
        "humidity": 40,
        "pumpOn": false, 
        "lampOn": false, 
        "program": none, 
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
    "history": {
        "xxxx": {
            "temp": 40.1, 
            "humidity": 40, 
            "pumpOn": true, 
            "lampOn": true, 
            "setTemp": 40.5, 
            "time": "2022-08-08 12:35:25"
        }
    }
}
"""

module_logger = logging.getLogger('main.firebase_db')

databaseURL = "https://rn5notifications-default-rtdb.firebaseio.com/"
appKey = "hotbox"

cred_obj = firebase_admin.credentials.Certificate("/home/pi/firebaseKey.json")
default_app = firebase_admin.initialize_app(cred_obj, {
    'databaseURL': databaseURL
})

ref = db.reference(appKey)
status_ref = ref.child("status")
programs_ref = ref.child("programs")

status = status_ref.get()
programs = programs_ref.get()

callback = None


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
    try:
        module_logger.debug("Starting Programs Listener")
        programs_ref.listen(programs_listener)
    except FirebaseError:
        module_logger.error('failed to start listener... trying again.')
        start_programs_listener()


def get_programs():
    return programs


