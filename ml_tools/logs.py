import sys
import logging
import logging.handlers

def init_logging(timestamps=False):
    """Set up logging for use by lorad

    Logs will go to stderr.
    """

    fmt = "%(process)d %(thread)s:%(levelname)7s %(message)s"
    if timestamps:
        fmt = "%(asctime)s " + fmt
    logging.basicConfig(
        stream=sys.stderr, level=logging.DEBUG, format=fmt, datefmt="%Y-%m-%d %H:%M:%S"
    )
#    handler = logging.handlers.SysLogHandler(address = '/dev/log')
#    logging.getLogger('').addHandler(handler) 
#    global logger
#    logger = logging.getLogger('MyLogger')
#    logger.setLevel(logging.DEBUG)
#    logger.addHandler(handler)

