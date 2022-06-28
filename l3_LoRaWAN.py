#Handles LoRaWAN network layer (queueing, transmitting and receiving)
import ccm
import logging
import LoRaWAN
from LoRaWAN.MHDR import MHDR
from random import randrange
from time import sleep

class l3():

    MAX_RETRIES=ccm.MAX_RETRIES

    def queue_reliable_packet(endpoint, packet):
        #increment ccm tx sequence counter
        endpoint.am_tx_seq_count=(endpoint.am_tx_seq_count+1)&15
        packet.txc=endpoint.am_tx_seq_count
        endpoint.tx_backlog[endpoint.am_tx_seq_count]=packet
        logging.info("Queueing %d",endpoint.am_tx_seq_count)

        #set status to queued
        endpoint.am_status[endpoint.am_tx_seq_count]=ccm.STATUS_QUEUED
        endpoint.am_response[endpoint.am_tx_seq_count]=""

    def queue_unreliable_packet(endpoint, packet):
        endpoint.um_backlog.append(packet)
        logging.info("Queueing unreliable packet")

    def send_join(endpoint):
        #generate JOIN message
        endpoint.devnonce = [randrange(256), randrange(256)]
        logging.info("Sending LoRaWAN join request\n")
        lorawan = LoRaWAN.new(endpoint.appkey)
        lorawan.create(MHDR.JOIN_REQUEST, {'deveui': endpoint.deveui, 'appeui': endpoint.appeui, 'devnonce': endpoint.devnonce})
        endpoint.send_lora_packet(lorawan.to_raw())

        #allow for incoming message in RX1 window
        sleep(ccm.RX1_START_OFFSET + ccm.RX1_WINDOW_LENGTH)

        #put modem to sleep
        endpoint.select_sleep_mode()

    def send_unreliable_packet(endpoint):
        packet=endpoint.um_backlog.pop(0)
        lorawan = LoRaWAN.new(endpoint.nwskey, endpoint.appskey)
        packet_as_list=[ord(ele) for ele in packet.to_str()]
        lorawan.create(MHDR.UNCONF_DATA_UP, {'devaddr': endpoint.devaddr, 'fcnt': endpoint.frame_counter, 'data': packet_as_list})
        endpoint.frame_counter=endpoint.frame_counter+1

        #send the packet
        endpoint.send_lora_packet(lorawan.to_raw())

        #allow for incoming message in RX1 window
        sleep(ccm.RX1_START_OFFSET + ccm.RX1_WINDOW_LENGTH)

        #put modem to sleep
        endpoint.select_sleep_mode()

    def send_reliable_packet(endpoint):
        #send next message for which an ack has not been received
        endpoint.am_last_tx_seq_sent=(endpoint.am_last_tx_seq_acked+1)&15

        lorawan = LoRaWAN.new(endpoint.nwskey, endpoint.appskey)
        packet=endpoint.tx_backlog[endpoint.am_last_tx_seq_sent]
        packet.rxc=endpoint.rx_seq_count
        #Set RNR flag if we missed a packet from them
        if endpoint.rx_requires_rnr:
          paxket.rnr=ccm.NOT_RECEIVED
          endpoint.rx_requires_rnr=False

        logging.info('Sending: '+str(packet.txc)+", RR: "+str(packet.rxc))
        packet_as_list=[ord(ele) for ele in packet.to_str()]
        lorawan.create(MHDR.UNCONF_DATA_UP, {'devaddr': endpoint.devaddr, 'fcnt': endpoint.frame_counter, 'data': packet_as_list})
        endpoint.frame_counter=endpoint.frame_counter+1

        #send the packet
        endpoint.send_lora_packet(lorawan.to_raw())

        #set status to sent
        endpoint.am_status[endpoint.am_last_tx_seq_sent]=ccm.STATUS_SENT

        #allow reception in RX1 window
        sleep(ccm.RX1_START_OFFSET+ccm.RX1_WINDOW_LENGTH)

        #switch to rx2 mode
        endpoint.select_rx2_mode()

        #allow for reception in RX2 window (where our ACK's arrive)
        sleep(ccm.RX2_START_OFFSET+ccm.RX2_WINDOW_LENGTH)

        #put modem back to sleep
        endpoint.select_sleep_mode()

    def receive_packet_callback(endpoint, payload):
        #use the appropriate encryption key
        if endpoint.joined:
          lorawan = LoRaWAN.new(endpoint.nwskey, endpoint.appskey)
        else:
          lorawan = LoRaWAN.new([], endpoint.appkey)

        # decode / decrypt the packet
        logging.info("Received packet")
        lorawan.read(payload)
        lorawan.get_payload()
        lorawan.get_mhdr().get_mversion()

        #Check MHeader MTYPE for JOIN message
        if lorawan.get_mhdr().get_mtype() == MHDR.JOIN_ACCEPT:
            logging.info("Got LoRaWAN join accept")
            endpoint.devaddr = lorawan.get_devaddr()
            endpoint.nwskey = lorawan.derive_nwskey(endpoint.devnonce)
            endpoint.appskey = lorawan.derive_appskey(endpoint.devnonce)
            endpoint.joined = True
            endpoint.status = ccm.STATUS_JOINED
            endpoint.join_required = False

        #All other LORA message types, look at our own payload MTYPE to determine action
        else:
            rxdata=''.join(list(map(chr, lorawan.get_payload())))

            packet=ccm.packet_from_str(rxdata)

            #process only valid massages
            if packet.mtype!=ccm.MTYPE_INVALID:
              #get reply from appserver, so reset our tx retry counter
              endpoint.tx_retries=0

              #check their tx seq counter matches expected
              if packet.mclass==ccm.MCLASS_RELIABLE:
                their_expected_seq=(endpoint.rxseqcnt+1)&15
                if packet.txc!=their_expected_seq:
                  endpoint.rx_requires_rnr=True
                
              #get their tx seq counter (our rx sequence counter) unless they sent OOS packet
              if not endpoint.rx_requires_rnr:
                  endpoint.rxseqcnt=packet.txc

              #Check for DM 'disconnected'
              if packet.mtype==ccm.MTYPE_DM:
                logging.info("Received DM - disconnected")
                endpoint.reset_endpoint()

              else:
                #check for acks to our transmissions
                if packet.rnr==ccm.RECEIVED:
                   endpoint.am_last_tx_seq_acked=packet.rxc
                   logging.info("Received RR: %d ",endpoint.am_last_tx_seq_acked)
                   endpoint.am_status[endpoint.am_last_tx_seq_acked]=ccm.STATUS_ACKED
                   endpoint.status = ccm.STATUS_REGISTERED
               
                #handle missed past packets (move pointer back to that position in
                #circular tx FIFO)
                if packet.rnr==ccm.NOT_RECEIVED:
                   unacked=packet.rxc
                   logging.info("Received RNR: resending from %d",unacked)
                   #resend from #
                   endpoint.am_last_tx_seq_acked=(unacked-1)&15

                #process incoming message types
                #Response to sent message
                if packet.mtype==ccm.MTYPE_UA:
                   endpoint.am_status[endpoint.am_last_tx_seq_acked]=packet.payload.ccm_ua.status
                   endpoint.am_response[endpoint.am_last_tx_seq_acked]=packet.payload.ccm_ua.message                   
                #currently none supported

