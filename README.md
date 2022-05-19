#Dependencies



#Usage
dbus-send --system --type=method_call --print-reply        --dest=org.cacophony.Lora /org/cacophony/Lora        org.cacophony.Lora.UnreliableMessage string:"I'm sure I saw a putty tat"
dbus-send --system --type=method_call --print-reply        --dest=org.cacophony.Lora /org/cacophony/Lora        org.cacophony.Lora.File string:'/home/pi/lora/LoRaWAN/thumbnail.png'
dbus-send --system --type=method_call --print-reply        --dest=org.cacophony.Lora /org/cacophony/Lora        org.cacophony.Lora.Message string:'{species': 'I thought I saw a putty cat'}
dbus-send --system --type=method_call --print-reply        --dest=org.cacophony.Lora /org/cacophony/Lora        org.cacophony.Lora.Connect
dbus-send --system --type=method_call --print-reply        --dest=org.cacophony.Lora /org/cacophony/Lora        org.cacophony.Lora.Disconnect

