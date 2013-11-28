from threading import Thread
from Queue import Queue
from singletonmixin import Singleton
import logging
#from pydispatch import dispatcher

event_q = Queue()

signal_log_level_dict = {"Time Update Model": logging.NOTSET,
                         "Weather Update": logging.INFO,
                         "Fault Update Model": logging.WARNING,
                         "Input String Update Model": logging.DEBUG,
                         "Alarm Message": logging.INFO,
                         "Alarm Mode Update Model": logging.DEBUG,
                         "Grace Update Model": logging.NOTSET,
                         "Sensor Update Model": logging.DEBUG,
                         "Terminate": logging.WARNING}


class EventSerializer(Thread, Singleton):
    """ This serializes send events to ensure thread safety """
    #------------------------------------------------------------------------------
    def __init__(self):
        """ Init the event serializer """
        global logger
        logger = logging.getLogger('serializer')
        Thread.__init__(self)
        self.daemon = True
        self.start()
        logger.info("Event_Serializer started")

    def run(self):
        while True:
            try:
                [func, kwargs] = event_q.get()
                try:
                    log_level = signal_log_level_dict[kwargs["signal"]]
                    logger.log(log_level, "Event serializer sending signal: " + kwargs["signal"])
                except:
                    log_level = logging.NOTSET
                for key, value in kwargs.iteritems():
                    if not (log_level == logging.NOTSET):
                        if not (key == "signal") and not (key == "sender"):
                            logger.log(log_level, "Argument " + str(key) + " : " + str(value))
                func(**kwargs)
            except:
                logger.warning("Exception while dispatching an event.", exc_info=True)