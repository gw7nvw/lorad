# Purpose

A transport layer to carry events (e.g. animal IDs) and thumbnail images from Cacophony Project cameras to the Cacophony API via LoRaWAN networks

This is currently a proof-of-concept

It is designed to be used in conjunction with cacophony-lora-appserver running on an internet-connected server

It is designed to work via TheThingsNetwork, with the app-server as a webhook client



# Includes

This repository includes the python package LoRaWAN from the following location:
https://github.com/jeroennijhof/LoRaWAN

Bugfixes have been made to this package to pprovide better handling on corrupted packets - and as such the package is included here



# Dependencies

TODO


# Hardware setup

SX1276 or RFM95W modem wired as follows to use SPI1.0 (ALT4 pin mode):

| Modem Pin | Wire   | RPi Pin | Function  |
|-----------|--------|---------|-----------|
| GND       | Black  | 6       | Gnd       |
| MISO      | Orange | 35      | SPI1_MISO |
| MOSI      | Yellow | 38      | SPI1_MOSI |
| SCK       | Green  | 40      | SPI1_SCLK |
| NSS       | Blue   | 12      | SPI1_CE0  |
| Reset     | Pruple | 31      | GPIO6     |
| Vcc       | Red    | 1       | +5v       |
| DIO0       | Brown  | 7       | GPIO4     |

DIO1 through DIO3 are not used

RPi pinouts are here:
https://datasheets.raspberrypi.com/bcm2835/bcm2835-peripherals.pdf

Antenna of 82mm wire / track (for 915MHz tx frequency) - or appropriate commercial equivalent connected to modem ANT / ANA 
**DO not transmit without antenna connected, or you will damage the modem**

# Usage 

Use DBus to send messages from the RPi to the application server (and Cacphony API)

e.g.
**File:**
dbus-send --system --type=method_call --print-reply        --dest=org.cacophony.Lora /org/cacophony/Lora        org.cacophony.Lora.File string:'/home/pi/puttytat.png'

**Unreliable message (best effort, no retries):**
dbus-send --system --type=method_call --print-reply        --dest=org.cacophony.Lora /org/cacophony/Lora        org.cacophony.Lora.UnreliableMessage string:"I tought I taw a putty tat"

**Reliable message - (retry on fail)**
dbus-send --system --type=method_call --print-reply        --dest=org.cacophony.Lora /org/cacophony/Lora        org.cacophony.Lora.Message string:'{species': 'I'm sure I taw a putty tat'}

**Connect & register: **
dbus-send --system --type=method_call --print-reply        --dest=org.cacophony.Lora /org/cacophony/Lora        org.cacophony.Lora.Connect

**Disconnect:**
dbus-send --system --type=method_call --print-reply        --dest=org.cacophony.Lora /org/cacophony/Lora        org.cacophony.Lora.Disconnect

**Check result of previous command:**
dbus-send --system --type=method_call --print-reply        --dest=org.cacophony.Lora /org/cacophony/Lora        org.cacophony.Lora.GetResponse int16:1
*(where int16:1 is the sequence ID returned by any reliable message DBus request in above list)*

 
 # Testing / demonstrating
 
 The file lora_appserver.py can be run on an internet-visible server to act as an intermediary between the LoRaWAN network and the Cacoponhy API.
 
 The syntax is:
   python3 server.py <port number>

 The API_KEY in this script will need updating to match the Application API key in TheThingsNetwork.
  
 The lora_appserver pyhton script is intended as a proof of concept, or model - it is not a production-ready solution
  
# The Things Network
  
## Gateway configuration
  
 Your LORA gateway will need to be running on the NZ / AU_915_928_FSB_2 band.  Use of other configurations is supported, but you will need to edit the frequencies, bandwidths and spread-factors in ccm.py to correspond, verify they are allowed in your country, and verify they are supported by the modem hardware you have. 
  
 - Network Server must point to TTN V3 (au1) - or whatever service you end up using as network server
 - Channel plan  AU_915_928_FSB_2
 
 ....
  

## Application Server
  
  ## Webhooks
  
 -   Webhook must be enabled to use the lora_appserver.py
 -   Base URL and port must point to the application server
 -   Uplink and Join Accept must be enabled and routed to /
 -   Format is JSON

  ## End Devices
  
  - Each endpoint must be registered against the Application in TTN
  - APPEUI must match that on the camera and can be all 0
  - DEVEUI must be unique and must match
  - AppKey must match
  - Network layer - Frequemncy plan must match device & gateway (AU_915_928_FSB_2)
  - Network layer - LoRaWAN version = 1.0.1
  - Network layer - Activation - OTAA
  - Application later - Enforce Payload Encryption = Yes
  - Join - AppKey - must match the key on the device (Note: AppKey is manually assigned, AppsKey is generated durign OTAA - not the same thing!)
  
  Other parameters can be blank as they will by assigned during Over the air Activation (JOIN)
  
  
  
