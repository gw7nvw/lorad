#Handles LoRA and PHY layers

from SX127x.LoRa import *
from SX127x.board_config import BOARD
from SX127x.LoRaArgumentParser import LoRaArgumentParser
import logging

BOARD.setup()
parser = LoRaArgumentParser("LoRaWAN sender")

class l1_LoRa(LoRa):

    def __init__(self, l3_receive_handler, verbose=False):
        super(l1_LoRa, self).__init__(verbose)
        self.set_mode(MODE.SLEEP)
        self.set_pa_config(pa_select=1)
        self.set_pa_config(max_power=0x0F, output_power=0x0E)
        self.set_sync_word(0x34)
        self.set_dio_mapping([0] * 6) #initialise DIO0 for rxdone
        self.set_rx_crc(True)
        self.l3_receive_handler=l3_receive_handler
        self.reset_endpoint()
        self.get_agc_auto_on()

    def reset_endpoint(self):
        logging.info("Resetting endpoint")
        self.appskey = ""
        self.nwskey = ""
        self.devaddr = ""
        self.am_last_tx_seq_acked=1
        self.am_last_tx_seq_sent=1
        self.rx_seq_count=0
        self.rx_requires_rnr=False
        self.am_tx_seq_count=1
        self.tx_retries=0
        self.joined = False
        self.join_required = False
        self.um_backlog=[]
        self.tx_backlog=[""] * 16
        self.am_response=[""] * 16
        self.am_status=[0] * 16
        self.frame_counter=1

    #send a pre-formed LORA packet
    def send_lora_packet(self, packet):
        logging.debug("Sending packet")
        self.set_mode(MODE.STDBY)
        self.set_freq(self.TX_FREQ)
        self.set_bw(self.TX_BW)
        self.set_spreading_factor(self.TX_SPREAD_FACTOR)
        self.write_payload(packet)
        self.set_dio_mapping([1,0,0,0,0,0]) # set DIO0 for txdone
        self.set_mode(MODE.TX)

    def select_rx1_mode(self):
        logging.debug("Listening RX1")
        self.set_mode(MODE.STDBY)
        self.set_dio_mapping([0] * 6)
        self.set_invert_iq(1)
        self.set_freq(self.RX1_FREQ)
        self.set_bw(self.RX1_BW)
        self.set_spreading_factor(self.RX1_SPREAD_FACTOR)
        self.set_mode(MODE.RXCONT)


    def select_rx2_mode(self):
        logging.debug("Listening RX2")
        self.set_mode(MODE.STDBY)
        self.set_dio_mapping([0] * 6)
        self.set_invert_iq(1)
        self.set_freq(self.RX2_FREQ)
        self.set_bw(self.RX2_BW)
        self.reset_ptr_rx()
        self.set_spreading_factor(self.RX2_SPREAD_FACTOR)
        self.set_mode(MODE.RXCONT)

    def select_standby_mode(self):
        logging.debug("Putting modem into standby")
        self.set_mode(MODE.STDBY)

    def select_sleep_mode(self):
        logging.debug("Putting modem into sleep")
        self.set_mode(MODE.SLEEP)


    # when data for the socket, send
    def handle_write(self):
        if self.databuffer:
            self.send(self.databuffer)
            self.databuffer = b""

    # Callback that runs when modem received a packet
    # Process packet, then reset the IRQ and remove packet from the buffer
    def on_rx_done(self):
        payload = self.read_payload(nocheck=True)
        self.l3_receive_handler(self,payload)
        
        # Mark RX as complete
        self.clear_irq_flags(RxDone=1) # clear rxdone IRQ flag
        self.reset_ptr_rx()


    # after LoRa modem says tx is complete, switch to RX mode for RX1 window
    # (callback called on TxDone)
    def on_tx_done(self):
        self.clear_irq_flags(TxDone=1) # clear txdone IRQ flag
        self.select_rx1_mode()

