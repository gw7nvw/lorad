#!/usr/bin/env python
from http.server import BaseHTTPRequestHandler, HTTPServer
import socket
import json
import time
from datetime import datetime, timedelta
import logging
import base64
import requests
import ccm
import datetime

#TODO - read from a config file
#Api key for TheThingsNetwork
API_KEY = 'Bearer NNSXS.HLMTOF32K6D7YH52DNZCGVPLKJ67D3YHV45QBAA.TEXMXFZTUIIGLXPBFA3LTCGPYWH6NOSKFFKXVNTVK7MJWCFXJNUQ'

#Where uploaded files get put
UPLOAD_PATH = "/tmp"

# One endpoint per device managed / connected
class Endpoint():
    def __init__(self, euid):
          self.euid=euid
          self.their_last_scnt=0
          self.our_seq_cnt=0
          self.lastpart=0
          self.currentfile=""
          self.currentfilename="unnamed.txt"
          self.token=""

    def find(endpoints, euid):
        for index in range(0, len(endpoints)):
            if endpoints[index].euid == euid:
                return index

        return None

class CacophonyAPI():
    def register(endpoint):
        request={
                'deviceId': endpoint.device_id,
                'password': endpoint.password
          };
        #send response to end uee agent
        #note EUID must be hex value in lowercase
        url = "https://api-test.cacophony.org.nz/authenticate_device"
        myheaders = { 'Content-Type': 'application/json; charset=utf-8', 'User-Agent': 'my-integration/my-integration-version' }
        x = requests.post(url, headers = myheaders, json = request )
        if x.status_code==200:
           logging.info("Registered device with API server: "+str(endpoint.device_id))
           return x.json()['token']
        else:
           logging.error("Registration FAILED with API server: "+str(endpoint.device_id))
           return None

    def send_event(endpoint, event):
        print(event)
        try:
          eventJson=json.loads(event)
          eventType = eventJson["e"]
          eventDetails = eventJson["d"]
          eventTimes = eventJson["t"]
        except ValueError as e:
          eventType = "unknown"
          eventDetails = { "message" : event }
          eventTimes = [datetime.datetime.utcnow().isoformat()+"Z"]
        request={
          "description": {
            "type": eventType,
            "details": eventDetails,
          },
          "dateTimes": eventTimes,
        };
        #send response to end user agent
        url = "https://api-test.cacophony.org.nz/api/v1/events"
        myheaders = { 'Authorization': endpoint.token, 'Content-Type': 'application/json; charset=utf-8', 'User-Agent': 'my-integration/my-integration-version' }
        print(event)
        logging.info("Sending Event to API server "+event)
        x = requests.post(url, headers = myheaders, json = request )
  
        if x.status_code==200:
            status=ccm.STATUS_SUCCESS
            response=""
        else:
            status=ccm.STATUS_FAIL
            response=str(x.status_code)
            print(x)
        return {'status': status, 'response': response}

class Server(BaseHTTPRequestHandler):

    # Send OK200 acknowledgement to network server
    # If required, send reply (tx_packet) to endpoint too
    def _set_headers(self, tx_packet, euid = ""):
        #ack to network server
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

        if tx_packet.mtype!=ccm.MTYPE_INVALID:
          print("Sending response to LoRa")  
          response=tx_packet.to_str()
          #send response to end user agent
          #note EUID must be hex value in lowercase
          url = "https://au1.cloud.thethings.network/api/v3/as/applications/cacophony/webhooks/test-webhook/devices/eui-"+euid.lower()+"/down/replace"
          myobj = {"downlinks":[{ "frm_payload":str(base64.b64encode(response.encode('utf-8')),'utf-8'), "f_port":1, "priority":"NORMAL"}]}
          myheaders = { 'Authorization': API_KEY, 'Content-Type': 'application/json; charset=utf-8', 'User-Agent': 'my-integration/my-integration-version' }
          print(response)
          x = requests.post(url, headers = myheaders, json = myobj )
          print(x)  

    def do_POST(self):

        global endpoints 

        try:
            endpoints
        except NameError:
            endpoints = []

        #prepare a blank reponse packet (marked as INVALID unless updated)
        tx_packet=ccm.ccm_packet()

        #execute on receiving HTTP POST
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        json_data=json.loads(post_data)
  
        #get general lora device info:
        lora_deveui=json_data['end_device_ids']['dev_eui']

        #process JOIN
        if 'join_accept' in json_data:
          logging.info("Receiveed JOIN request from endpoint :"+lora_deveui)
          index=Endpoint.find(endpoints,lora_deveui)
          if index!=None:
              logging.info("Removing previously registered endpoint")
              endpoints.pop(index)
          endpoints.append(Endpoint(lora_deveui))

        #process any uplink messages
        if 'uplink_message' in json_data:

          #check if endpoint is registered with us
          endpoint=Endpoint.find(endpoints,lora_deveui)
          if endpoint == None:
            logging.info("Received message from unregistered endpoint: "+lora_deveui)
            #send a DM - you are disconnected - message
            tx_packet.mtype=ccm.MTYPE_DM
            logging.info("Sending DM")

          #for registered endpoints, process the ccm message in the 
          #LoRaWAN payload
          else:
            lora_payload=json_data['uplink_message']['frm_payload']
            lora_fport=json_data['uplink_message']['f_port']
            lora_fcnt=json_data['uplink_message']['f_cnt']
            lora_devaddr=json_data['end_device_ids']['dev_addr']
  
            logging.info("Received LoRa data: DevEUI: %s - DevAddr: %s ",lora_deveui,lora_devaddr)
            hex_payload=base64.b64decode(lora_payload)
            str_payload=''.join(list(map(chr,hex_payload)))
            packet=ccm.packet_from_str(str_payload)
  
            #process only packets with our magic number in the header
            #necessary as 3rd party network servers send all sorts of other
            #not-in-the-LoRaWAN-specs messages
            if packet.mtype!=ccm.MTYPE_INVALID:

              #Handle ACKing of reliable message types
              logging.info("Reliable?: "+str(packet.mclass))
              if packet.mclass==ccm.MCLASS_RELIABLE:
                their_seq_cnt=packet.txc
                logging.info("rx: "+str(their_seq_cnt)+", tx: "+ str(endpoints[endpoint].our_seq_cnt))
                #This was the next message sequence we expected 
                if (int(their_seq_cnt)==0 or int(their_seq_cnt)==(endpoints[endpoint].their_last_scnt+1)&15):
                  tx_packet.mtype=ccm.MTYPE_UA
                  tx_packet.rnr=ccm.RECEIVED
                  tx_packet.rxc=their_seq_cnt
                  tx_packet.txc=endpoints[endpoint].our_seq_cnt
                  tx_packet.payload.ccm_ua.status = ccm.STATUS_ACKED
                  tx_packet.payload.ccm_ua.message = ""
                  logging.info("Sending RR: "+str(their_seq_cnt))
                  endpoints[endpoint].their_last_scnt=their_seq_cnt
         
                #This was not the message sequence we expected
                else:
                  #So request the message sequence we did expect
                  tx_packet.mtype=ccm.MTYPE_UA
                  tx_packet.rnr=ccm.NOT_RECEIVED
                  tx_packet.rxc=(endpoints[endpoint].their_last_scnt+1)&15
                  tx_packet.txc=endpoints[endpoint].our_seq_cnt
                  tx_packet.payload.ccm_ua.status = ccm.STATUS_NONE
                  tx_packet.payload.ccm_ua.message = ""
                  logging.info("Sending RNR: "+str((endpoints[endpoint].their_last_scnt+1)&15))
                  #And invalidate / ignore this message
                  packet.mtype=ccm.MTYPE_INVALID

              #Handle register
              if packet.mtype==ccm.MTYPE_REGISTER:
                logging.info("Received REGISTER")

                endpoints[endpoint].device_id=packet.payload.ccm_register.device_id
                endpoints[endpoint].password=packet.payload.ccm_register.password
                response=CacophonyAPI.register(endpoints[endpoint])
                if response==None:
                  #If register failed, send DM back to client
                  tx_packet.mtype=ccm.MTYPE_DM
                else:
                  #otherwise store token to use in later requests
                  endpoints[endpoint].token=response
                  tx_packet.payload.ccm_ua.status=ccm.STATUS_SUCCESS

              # Handle disconnect request
              if packet.mtype==ccm.MTYPE_DISC:
                logging.info("Received DISC")
                tx_packet.mtype=ccm.MTYPE_DM
                logging.info("Sending DM")
 
                #Deregister the endpoint
                index=Endpoint.find(endpoints,lora_deveui)
                if index!=None:
                   logging.info("Removing previously registered endpoint")
                   endpoints.pop(index)
     
              # Handle simple messages 
              elif packet.mtype==ccm.MTYPE_MESSAGE:
                message=packet.payload.ccm_message.message
                result=CacophonyAPI.send_event(endpoints[endpoint],message)
                tx_packet.payload.ccm_ua.status=result['status']
                tx_packet.payload.ccm_ua.response=result['response']

              #Handle multipart
              elif packet.mtype==ccm.MTYPE_MULTIPART:
                thispart=packet.payload.ccm_file.segc
                length=packet.payload.ccm_file.len
                data=packet.payload.ccm_file.filepart

                #New mutipart
                if thispart==1:
                  endpoints[endpoint].currentfile = [""] * length
                  endpoints[endpoint].lastpart=0
                  logging.info ("New multipart")
           
                #Out of sequence multipart - abort (can only happen  
                #if we lose len(lora_sequence_counter) packets
                if thispart!=endpoints[endpoint].lastpart+1:
                  logging.error("ERROR: out of sequnce. Aborting. Got "+str(thispart)+", expeted "+str(endpoints[endpoint].lastpart+1))
                  currentfile=None
                  endpoints[endpoint].lastpart=0

  
                #Expected multipart - append to received message
                else:
                  logging.info("Multipart continuation")
                  endpoints[endpoint].currentfile[thispart-1]=data
                  endpoints[endpoint].lastpart=thispart
                  tx_packet.payload.ccm_ua.status=ccm.STATUS_PARTIAL
                
                  #Last part
                  if thispart==length:
                    logging.info("Multipart complete")
                    thisfile=''.join(endpoints[endpoint].currentfile)
                    currentfile=None
                    lastpart=0
                    tx_packet.payload.ccm_ua.status=ccm.STATUS_SUCCESS
                    result=CacophonyAPI.send_event(endpoints[endpoint],thisfile)

              #Handle file uploads
              elif packet.mtype==ccm.MTYPE_FILE:
                thispart=packet.payload.ccm_file.segc
                length=packet.payload.ccm_file.len
                data=packet.payload.ccm_file.filepart

                #New file
                if thispart==1:
                  endpoints[endpoint].currentfile = [""] * length
                  endpoints[endpoint].lastpart=0
                  endpoints[endpoint].currentfilename = data
                  endpoints[endpoint].lastpart=thispart
                  logging.info ("New file: "+endpoints[endpoint].currentfilename)
           
                else:
                  #Out of sequence filepart - abort (can only happen  
                  #if we lose len(lora_sequence_counter) packets
                  if thispart!=endpoints[endpoint].lastpart+1:
                    logging.error("ERROR: out of sequnce. Aborting. Got "+str(thispart)+", expeted "+str(endpoints[endpoint].lastpart+1))
                    currentfile=None
                    endpoints[endpoint].lastpart=0
  
                  #Expected filepart - append to received file
                  else:
                    logging.info("File continuation")
                    endpoints[endpoint].currentfile[thispart-1]=data
                    endpoints[endpoint].lastpart=thispart
                    tx_packet.payload.ccm_ua.status=ccm.STATUS_PARTIAL
                  
                    #Last part
                    if thispart==length:
                      logging.info("File complete")
                      thisfile=''.join(endpoints[endpoint].currentfile)
                      thisbinaryfile=base64.b64decode(thisfile)
                      file = open(UPLOAD_PATH+"/"+endpoints[endpoint].currentfilename, "wb")
                      file.write(thisbinaryfile)
                      file.close
                      currentfile=None
                      lastpart=0
                      tx_packet.payload.ccm_ua.status=ccm.STATUS_SUCCESS
        

        self._set_headers(tx_packet, lora_deveui)

#Run the websocket server.  Syntax: lora_appserver.py <port>
def run(server_class=HTTPServer, handler_class=Server, port=3123):

    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    logging.info('Starting webserver and waiting for post on port: %s',port)
    httpd.serve_forever()

if __name__ == "__main__":
    from sys import argv
    logging.basicConfig(level=logging.DEBUG,format="%(asctime)s - %(levelname)s - %(message)s")
    #logging.basicConfig(filename="lora_appserver.log",level=logging.DEBUG,format="%(asctime)s - %(levelname)s - %(message)s")
    logging.info("Starting lora_appserver.py")

    if len(argv) == 2:
        run(port=int(argv[1]))
    else:
        run()
