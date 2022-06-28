#!/home/pi/lora/bin/python3 -u

""" An asynchronous socket <-> LoRaWAN interface """

# Losely based on an original LoRa transceiver by bjcarne.  The original license is 
# attached below.
#
# Listen on dbus org.cacophony.Lora for following commands (methods)
# Send the result of those commands to the app-server via LoRaWAN
# Supported commands are:
# Connect  
#    Send JOIN to LoRaWAN gateway 
#    Then send REGISTER to app-server to authenticate with Cacophony API. 
#    Returns seqId
# UnreliableMessage <string: message> 
#    Send unreliable (unACK'd) message (event)
# Message <string: message> 
#    Send reliable message (event), check for ACK and retry if required. 
#    Returns seqId
# File <string: filename> 
#    Upload a file using reliable messaging. 
#    Returns seqId
# Disconnect 
#    Disconnect and clear message queue
# GetResponse <int16: seqId> - query the status of a previous message.
#    Returns an int16 who's values are defined in ccm.STATUS
#    Possible statuses: QUEUED, SENT, ACKED, PARTIAL, SUCCESS, FAILED, 
#                       NONE (disconnected or connect rejected)
#    May return a string with further info



# Server runs two transmit queues:
# - unreliable messages
# - reliable messages
# Queues are both FIFO and checked in the above order
# Reliable packets (MCLASS=RELIABLE)
# - Use a 4 bit sequence counter. Last 15 packets are buffered in cicular
#   buffer and can be retransmitted upon request (RNR)
# - Transceiver listens in both RX1 and RX2 windows for ACKnowledgements /
#   incoming messages - so 2x incoming messages supported (i.e. ACK and one other)
# - Next packet is only sent once a RR (ACK) is received for the previous packet
# Unreliable packets (MCLASS = UNRELIABLE)
# - are queued in a FIFO and oldest available is sent in the next TX window
# - transceiver listens in RX1 window (as-per LoRaWAN spec) for incoming messages 
# - does not expect an ACK to these messages
# - does not listen in RX2 window (so only 1 incoming message per TX supported)
# DISConnect expects a DM resonse (or will be retried).
# - Client will reset to initial state following disconnect
# DM received at any other time from appserver also causes client to disconnect and reset 
# JOIN_ACCEPT, UA and DM are the only supported incoming messages at this time.
# For reliable messages, if tx_retries>=ccm.MAX_RETRIES we assume we have been DM - disconnected

import sys, signal
from time import sleep
import threading
import datetime

#logging
import logging
from ml_tools.logs import init_logging
init_logging()

#hardware modem
#from SX127x.LoRa import *

#various network layers
from l4 import l4
from l3_LoRaWAN import l3
from l1_LoRa import l1_LoRa
from SX127x.board_config import BOARD
import ccm


#dbus stuff
import dbus
import dbus.service

#config files
import toml






class TrackingReporter:
    DBUS_NAME = "org.cacophony.thermalrecorder"
    DBUS_PATH = "/org/cacophony/thermalrecorder"

    def signal_tracking_callback(self, what, confidence, region, tracking):
      if tracking==0:
        print(
            "Received a tracking signal and it says " + what,
            confidence,
            "%"
        )
    
        self.connected=True
        timestamp = datetime.datetime.utcnow().isoformat()+"Z"
        l4.queue_unreliable_message(self.endpoint, '{"t": ["'+timestamp+'"], "e": "classifier", "d": {"what": "'+what+'", "conf": '+str(confidence)+'}}')

    def __init__(self, endpoint):
        self.endpoint=endpoint
        self.loop = GLib.MainLoop()
        self.t = threading.Thread(
            target=self.run_server,
        )
        self.t.start()
        self.connected=False

    def quit(self):
        self.loop.quit()

    def run_server(self):
        while True:
          try:
            bus = dbus.SystemBus()
            object = bus.get_object(self.DBUS_NAME, self.DBUS_PATH)
            break
          except:
            logging.error("Failed to subscribe to "+self.DBUS_NAME+". Sleeping 60 secs.")
            sleep(60)
            continue

        logging.info("Subscribeed to DBUS")

        bus.add_signal_receiver(
            self.signal_tracking_callback,
            dbus_interface=self.DBUS_NAME,
            signal_name="Tracking",
        )
        self.loop.run()


class LoraService(dbus.service.Object):
    def __init__(self, lora):
        print("init DBUS")
        self.bus = dbus.SystemBus()
        self.endpoint=lora
        name = dbus.service.BusName('org.cacophony.Lora', bus=self.bus)
        self.connected = False
        super().__init__(name, '/org/cacophony/Lora')
        self.endpoint.status = ccm.STATUS_RUNNING

    @dbus.service.method('org.cacophony.Lora', out_signature='n', in_singature='')
    def Connect(self):
        self.connected=True
        l4.queue_connect(self.endpoint)
        return self.endpoint.am_tx_seq_count

    @dbus.service.method('org.cacophony.Lora', out_signature='n', in_singature='s')
    def Message(self, message):
        self.connected=True
        l4.queue_message(self.endpoint, message)
        return self.endpoint.am_tx_seq_count

    @dbus.service.method('org.cacophony.Lora', out_signature='n', in_singature='s')
    def File(self, filename):
        self.connected=True
        l4.queue_file(self.endpoint, filename)
        return self.endpoint.am_tx_seq_count

    @dbus.service.method('org.cacophony.Lora', out_signature='n', in_singature='s')
    def UnreliableMessage(self, message):
        self.connected=True
        l4.queue_unreliable_message(self.endpoint, message)
        return 0

    @dbus.service.method('org.cacophony.Lora', out_signature='n', in_singature='')
    def Disconnect(self):
        self.connected=True
        l4.queue_disconnect(self.endpoint)
        return 0

    @dbus.service.method('org.cacophony.Lora', out_signature='n', in_singature='')
    def GetStatus(self):
        return lora_service.endpoint.status

    @dbus.service.method('org.cacophony.Lora', out_signature='ns', in_singature='s')
    def GetResponse(self, seq):
        self.connected=True
        return self.endpoint.am_status[seq], self.endpoint.am_response[seq]

# Background thread - checks each second for data to transmit via LoRaWAN.
# First sends JOIN and REGISTER requests if we have not yet joined a network and registered with API
# Handles transmitting packets, and timing of the switch of transceiver from rx1 to rx2 window
# Switch from TX to RX1 is handled by tx_done() 
class txLoop(threading.Thread):
   def __init__(self, threadID, name, counter, lora):
      logging.info("Init TX loop")
      threading.Thread.__init__(self)
      self.threadID = threadID
      self.name = name
      self.counter = counter
      self.event=threading.Event()
      self.endpoint=lora
      self.registerQueued=False

   def run(self):
      logging.info("Start TX loop")
      self.exit_requested=False
      while not self.event.is_set():
        if lora_service.connected or tracking_service.connected:
          self.check_tx_queue()
        sleep(1)
 
   # main loop - check if we have packets to tx in either unreliable or reliable 
   # message queue, and if so send them
   def check_tx_queue(self):
      logging.debug("Check TX loop")
      if len(self.endpoint.um_backlog)>0 or self.endpoint.am_tx_seq_count!=self.endpoint.am_last_tx_seq_acked or self.endpoint.join_required==True:

        # if we have exceeded our retry limit, assume we are disconnected, reset the
        # state of the endpoint and discard everything in our queue
        if self.endpoint.tx_retries>l3.MAX_RETRIES:
          self.endpoint.status=ccm.STATUS_RUNNING
          self.endpoint.joined=False
          self.endpoint.reset_endpoint()

        else: 
          #we have message(s) to send
          
          # if we have not joined a network, then send a JOIN and REGISTER
          if self.endpoint.joined==False:
            self.endpoint.tx_retries+=1
            l3.send_join(self.endpoint)
            l4.queue_connect(self.endpoint)
            self.registerQueued=True

          # Otherwise, check for unreliable messages to send (we
          # prioritise these are they are faster than reliable messaging) 
          elif self.registerQueued==False and len(self.endpoint.um_backlog)>0:
            logging.info("Send next unreliable message")
            l3.send_unreliable_packet(self.endpoint)
 
          # Otherwise, check if there are reliable messages not yet acknowledged to (re)send 
          elif self.endpoint.am_tx_seq_count!=self.endpoint.am_last_tx_seq_acked:
            self.endpoint.tx_retries+=1
            #send next message for which an ack has not been received
            l3.send_reliable_packet(self.endpoint)
            self.registerQueued=False


if __name__ == "__main__":

        logging.error ("test error")
        import dbus.mainloop.glib 
        from gi.repository import GLib

        def terminateProcess(signalNumber=None, frame=None):
            #raise Exception('GracefulExit')
            sys.exit(0)

        signal.signal(signal.SIGTERM, terminateProcess)

        lora = l1_LoRa(l3.receive_packet_callback, verbose=False)

        config = toml.load("/etc/cacophony/config.toml")
        lora.dev_pw = config['secrets']['device-password']
        lora.dev_id = config['device']['id']
        lora.deveui = config['lora']['deveui']
        lora.appeui = config['lora']['appeui']
        lora.appkey = config['lora']['appkey']
        lora.TX_FREQ = config['lora']['tx_freq']
        lora.TX_BW = config['lora']['tx_bw']
        lora.TX_SPREAD_FACTOR = config['lora']['tx_spread_factor']
        lora.RX1_FREQ = config['lora']['rx1_freq']
        lora.RX1_BW = config['lora']['rx1_bw']
        lora.RX1_SPREAD_FACTOR = config['lora']['rx1_spread_factor']
        lora.RX2_FREQ = config['lora']['rx2_freq']
        lora.RX2_BW = config['lora']['rx2_bw']
        lora.RX2_SPREAD_FACTOR = config['lora']['rx2_spread_factor']


        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

        mainloop = GLib.MainLoop()
 
        lora_service = LoraService(lora)
        tracking_service = TrackingReporter(lora)
    
        try:
            # Start tx handler loop
            thread1 = txLoop(1, "Thread-1", 1, lora)
            thread1.daemon  = True
            thread1.start()

            # Start interrupt handlers for socket and modem callbacks
            logging.info ("Starting LoRa DBus service")
            mainloop.run()
        except SystemExit:
            logging.warning("Graceful Exit")

        finally:
            logging.error("Forced exit")
            logging.info("Terminate transmit handler")
            thread1.event.set()
            logging.warning("Turn off LoRa radio")
            l1_LoRa.select_sleep_mode(lora)
            logging.info("Closing socket connection")
            #lora_service.close()
            logging.info("End Tracking service")
            tracking_service.quit()
            logging.info("Disable hardware")
            BOARD.teardown()
            logging.error("Teardown complete - safe to exit")
