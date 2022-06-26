# Handles registration, flow control and payload encoding / decoding for cacophony data
# over an L3 LoRaWAN network layer

from l3_LoRaWAN import l3
import ccm
import logging
import base64

class l4():
    def queue_message(endpoint, message):
        if len(message)>ccm.MAX_PAYLOAD_LEN:
            #should use multi-part-message
            l4.queue_multipart_message(endpoint,message)
        else:
            packet=ccm.ccm_packet()
            packet.mtype=ccm.MTYPE_MESSAGE
            packet.mclass=ccm.MCLASS_RELIABLE
            packet.payload.ccm_message.message=message

            l3.queue_reliable_packet(endpoint,packet)

    def queue_unreliable_message(endpoint, message):
        if len(message)>ccm.MAX_PAYLOAD_LEN-1:
            #truncate as no multi-prt for unreliable mode
            message=message[0:ccm.MAX_PAYLOAD_LEN-1]

        packet=ccm.ccm_packet()
        packet.mtype=ccm.MTYPE_MESSAGE
        packet.mclass=ccm.MCLASS_UNRELIABLE
        packet.payload.ccm_message.message=message
        l3.queue_unreliable_packet(endpoint,packet)

    def queue_disconnect(endpoint):
        packet=ccm.ccm_packet()
        packet.mtype=ccm.MTYPE_DISC
        packet.mclass=ccm.MCLASS_RELIABLE

        l3.queue_reliable_packet(endpoint,packet)
        logging.info("Queueing DISC %d",endpoint.am_tx_seq_count)

    def queue_connect(endpoint):

        packet=ccm.ccm_packet()
        packet.mtype=ccm.MTYPE_REGISTER
        packet.mclass=ccm.MCLASS_RELIABLE
        packet.payload.ccm_register.device_id=endpoint.dev_id
        packet.payload.ccm_register.password=endpoint.dev_pw
        endpoint.registerQueued=True
        #reset tx counters to insert register at start of queue
        endpoint.am_last_tx_seq_acked=0
        endpoint.am_last_tx_seq_sent=0

        packet.txc=1
        endpoint.tx_backlog[1]=packet
        logging.debug("Queueing %d",1)

    def queue_multipart_message(endpoint, message):
        logging.info("Sending multipart")

        bllen=int((len(message)-1)/ccm.MAX_PAYLOAD_LEN)+1 #+1 for rounding
        if bllen>ccm.MAX_FILE_BLOCKS:
          logging.error("Message too long. "+str(bllen)+" blocks > maximum "+str(cm.MAX_FILE_BLOCKS))
          return 1

        blcnt=1
        while blcnt<=bllen:

          if len(message)>0:
            packet=ccm.ccm_packet()
            packet.mtype=ccm.MTYPE_MULTIPART
            packet.mclass=ccm.MCLASS_RELIABLE
            packet.payload.ccm_file.segc=blcnt
            packet.payload.ccm_file.len=bllen
            packet.payload.ccm_file.filepart=message[0:ccm.MAX_PAYLOAD_LEN]
            blcnt=blcnt+1
            #remove queue data from buffer
            logging.info("Queueing next file segment")
            logging.debug("Part %d of %d",blcnt,bllen)
            if len(message)>ccm.MAX_PAYLOAD_LEN:
              message=message[ccm.MAX_PAYLOAD_LEN:]
            else:
              message=""

            l3.queue_reliable_packet(endpoint,packet)


    def queue_file(endpoint, filename):
        logging.info("Sending file")
        file=open(filename,'rb')
        backlog=file.read()
        file.close()

        bl64=str(base64.b64encode(backlog),'utf-8')
        bllen=int((len(bl64)-1)/ccm.MAX_PAYLOAD_LEN)+2 #+1 for rounding, +1 for metadata
        if bllen>ccm.MAX_FILE_BLOCKS:
          logging.error("File too long. "+str(bllen)+" blocks > maximum "+str(cm.MAX_FILE_BLOCKS))
          return 1

        blcnt=1
        #queue metadata (currently just filename)
        packet=ccm.ccm_packet()
        packet.mtype=ccm.MTYPE_FILE
        packet.mclass=ccm.MCLASS_RELIABLE
        packet.payload.ccm_file.segc=blcnt
        packet.payload.ccm_file.len=bllen
        packet.payload.ccm_file.filepart=filename.split('/')[-1] #ignore path
        blcnt=blcnt+1
        l3.queue_reliable_packet(endpoint,packet)

        #now send file
        while blcnt<=bllen:

          if len(bl64)>0:
            packet=ccm.ccm_packet()
            packet.mtype=ccm.MTYPE_FILE
            packet.mclass=ccm.MCLASS_RELIABLE
            packet.payload.ccm_file.segc=blcnt
            packet.payload.ccm_file.len=bllen
            packet.payload.ccm_file.filepart=bl64[0:ccm.MAX_PAYLOAD_LEN]
            blcnt=blcnt+1

            #remove queue data from buffer
            logging.info("Queueing next file segment")
            if len(bl64)>ccm.MAX_PAYLOAD_LEN:
              bl64=bl64[ccm.MAX_PAYLOAD_LEN:]
            else:
              bl64=""

            l3.queue_reliable_packet(endpoint,packet)


