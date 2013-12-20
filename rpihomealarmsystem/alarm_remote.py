#!/usr/bin/env python

import sys, getopt
import rpyc


def main(argv):
    try:
        opts, args = getopt.getopt(argv, "hpe:m:s:f:", ["printAlarm", "event=", "msg=", "state=", "function="])
    except getopt.GetoptError:
        print 'test.py -e <signal> -m <msg> | -s <state_name> | -f <function_name> | -p'
        sys.exit(2)

    signal = ""
    msg = ""

    for opt, arg in opts:
        if opt == '-h':
            print 'test.py -e <signal_name> -m <msg> | -s <state_name> | -f <function_name> | -p'
            sys.exit()
        elif opt in ("-e", "--event"):
            signal = arg
        elif opt in ("-m", "--msg"):
            msg = arg
        elif opt in ("-s", "--state"):
            state = arg
            c = rpyc.connect("localhost", 18861)
            c.root.set_alarm_state(state)
        elif opt in ("-p", "--printAlarm"):
            c = rpyc.connect("localhost", 18861)
            print c.root.get_model()
        elif opt in ("-f", "--function"):
            c = rpyc.connect("localhost", 18861)
            c.root.exposed_execute_model_function(arg)

    if (not signal == "" and not msg == ""):
        c = rpyc.connect("localhost", 18861)
        c.root.exposed_create_event(signal, msg)

# Run the program
if __name__ == "__main__":
    main(sys.argv[1:])       