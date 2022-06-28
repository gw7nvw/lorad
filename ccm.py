from ctypes import *

RECEIVED=0
NOT_RECEIVED=1

STATUS_RUNNING = 1
STATUS_JOINED = 2
STATUS_REGISTERED = 3

MCLASS_RELIABLE = 1
MCLASS_UNRELIABLE = 0
MTYPE_INVALID=0
MTYPE_SABM=1
MTYPE_UA=2
MTYPE_DISC=3
MTYPE_DM=4
MTYPE_MESSAGE=5
MTYPE_FILE=6
MTYPE_PING=7
MTYPE_REGISTER=8
MTYPE_MULTIPART=9

STATUS_NONE=0
STATUS_QUEUED=1
STATUS_SENT=2
STATUS_ACKED=3
STATUS_PARTIAL=4
STATUS_SUCCESS=5
STATUS_WARNING=6
STATUS_FAIL=7

MAX_PAYLOAD_LEN=235
MAX_FILE_BLOCKS=127

TX_FREQ = 915.2
TX_BW = 7
TX_SPREAD_FACTOR = 7

RX1_FREQ = 923.3
RX1_BW = 9
RX1_SPREAD_FACTOR = 7

RX2_FREQ = 923.3
RX2_BW = 9
RX2_SPREAD_FACTOR = 10

#timings
RX1_START_OFFSET=5
RX1_WINDOW_LENGTH=2
RX2_START_OFFSET=3
RX2_WINDOW_LENGTH=5

# transmit retries (for reliable mesages and JOIN request)
MAX_RETRIES = 3

# ccm_packet class.  Packet consists of:
# 4-byte header:
# - 2 byte magic number (0x1773) - the year those exotic pests started arriving!
# - 4 bit tx sequence number
# - 4 bit rx sequence number
# - 1 bit Not Received flag
# - 1 bit reliable / not reliable flag
# - 6 bit message type

# Then the payload based on message type:
# MTYPE=FILE:
# - 1 byte sequence counter (cuurrent file part)
# - 1 byte length indicator (total parts in file)
# - 0..MAX_LEN payload (filepart)

# MTYPE=(UNRELIABLE_)MESSAGE
# - 0..MAX_LEN payload

#MTYPE = REGISTER
# - 0..3: DEVICEID
# - 4.. password

class ccm_register(Structure):
  _fields_ = [
    ("device_id", c_int),
    ("password", c_wchar_p)
  ]
  def to_str(self):
    payload = chr((self.device_id&0xff000000) >> 24)  + chr((self.device_id&0x00ff0000) >>16)  + chr((self.device_id&0x0000ff00) >> 8) + chr(self.device_id&0x000000ff)+(self.password or "")
    return payload
 
class ccm_message(Structure):
  _fields_ = [
    ("message", c_wchar_p)
  ]
  def to_str(self):
    payload = self.message or ""
    return payload

class ccm_file(Structure):
  _fields_ = [
    ("segc", c_int),
    ("len", c_int),
    ("filepart", c_wchar_p)
  ]
  def to_str(self):
    payload = chr(self.segc) + chr (self.len) + (self.filepart or "")
    return payload

class ccm_ua(Structure):
  _fields_ = [
    ("status", c_int),
    ("message", c_wchar_p)
  ]
  def to_str(self):
    payload = chr(self.status) + (self.message or "")
    return payload

class ccm_payload(Union):
  _fields_ = [
    ("ccm_message", ccm_message),
    ("ccm_file", ccm_file),
    ("ccm_register", ccm_register),
    ("ccm_ua", ccm_ua),
  ]

class ccm_packet(Structure):
  _fields_ = [
    ("id1", c_int),
    ("id2", c_int),
    ("txc", c_int),
    ("rxc", c_int),
    ("rnr", c_bool),
    ("mclass", c_bool),
    ("mtype", c_int),
    ("payload", ccm_payload)
  ]
  # Encode packet structure into bytes for tx 
  # Should be able to do this automatically (as-per C)
  def to_str(self):
    counters = chr(((self.txc&15) << 4) + (self.rxc&15))
    conf_mtype = chr(((self.rnr&1) << 7) + ((self.mclass&1) << 6) + (self.mtype&63))
    if self.mtype==MTYPE_MESSAGE:
       payload=self.payload.ccm_message.to_str()
    elif (self.mtype==MTYPE_FILE or self.mtype==MTYPE_MULTIPART):
       payload=self.payload.ccm_file.to_str()
    elif self.mtype==MTYPE_REGISTER:
       payload=self.payload.ccm_register.to_str()
    elif self.mtype==MTYPE_UA:
       payload=self.payload.ccm_ua.to_str()

    else: 
       payload="" 
    
    packet=chr(0x17)+chr(0x73)+counters+conf_mtype+payload

    return packet

# Decode received bytes (as string) into packet structure
# Should be able to do this automatically (as-per C)
def packet_from_str(data):
  packet=ccm_packet()
  packet.mtype=MTYPE_INVALID

  if len(data)>=4:
    #check for 0x1773 magic signature
    if data[0]==chr(0x17) and data[1]==chr(0x73):
      packet.txc=(ord(data[2])&0xf0) >> 4
      packet.rxc=ord(data[2])&0xf
      packet.mclass=(ord(data[3])&0x40) >> 6
      packet.mtype=ord(data[3])&0x3f
      packet.rnr=(ord(data[3])&0x80) >> 7
      payload=data[4:]
      if packet.mtype==MTYPE_MESSAGE:
           packet.payload.ccm_message.message=payload
      elif (packet.mtype==MTYPE_FILE or packet.mtype==MTYPE_MULTIPART):
           packet.payload.ccm_file.segc=ord(payload[0])      
           packet.payload.ccm_file.len=ord(payload[1])      
           packet.payload.ccm_file.filepart=payload[2:]
      elif packet.mtype==MTYPE_REGISTER:
           packet.payload.ccm_register.device_id = (ord(payload[0]) << 24) + (ord(payload[1]) << 16) + (ord(payload[2]) << 8) + ord(payload[3]) 
           packet.payload.ccm_register.password = payload[4:]
      elif packet.mtype==MTYPE_UA:
           packet.payload.ccm_ua.status = ord(payload[0])
           if len(payload)>0:
               packet.payload.ccm_ua.message = payload[1:]
           else:
               packet.payload.ccm_ua.message = ""

  
  return packet
