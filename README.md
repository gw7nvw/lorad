#Purpose

A transport layer to carry events (e.g. animal IDs) and thumbnail images from Cacophony Project cameras to the Cacophony API via LoRaWAN networks

This is currently a proof-of-concept

It is designed to be used in conjunction with cacophony-lora-appserver running on an internet-connected server

It is designed to work via TheThingsNetwork, with the app-server as a webhook client



#Includes

This repository includes the python package LoRaWAN from the following location:
https://github.com/jeroennijhof/LoRaWAN

Bugfixes have been made to this package to pprovide better handling on corrupted packets - and as such the package is included here



#Dependencies

TODO

#Usage


dbus-send --system --type=method_call --print-reply        --dest=org.cacophony.Lora /org/cacophony/Lora        org.cacophony.Lora.File string:'/home/pi/puttytat.png'

dbus-send --system --type=method_call --print-reply        --dest=org.cacophony.Lora /org/cacophony/Lora        org.cacophony.Lora.UnreliableMessage string:"I tought I taw a putty tat"

dbus-send --system --type=method_call --print-reply        --dest=org.cacophony.Lora /org/cacophony/Lora        org.cacophony.Lora.Message string:'{species': 'I'm sure I taw a putty tat'}

dbus-send --system --type=method_call --print-reply        --dest=org.cacophony.Lora /org/cacophony/Lora        org.cacophony.Lora.Connect

dbus-send --system --type=method_call --print-reply        --dest=org.cacophony.Lora /org/cacophony/Lora        org.cacophony.Lora.Disconnect


