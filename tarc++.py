# Import package
import paho.mqtt.client as mqtt
import ssl
import spidev
import time
import datetime
import sys
import json
import dweepy

from libsoc import gpio
from libsoc_zero.GPIO import Button
from libsoc_zero.GPIO import Tilt
from libsoc_zero.GPIO import LED
from time import sleep

# Define Variables
#as it is SSL the port is 8883
MQTT_PORT = 8883
MQTT_KEEPALIVE_INTERVAL = 600

#MQTT_HOST = "put your Custom Endpoint here"
MQTT_HOST = "xxxxxxxxxxxxx.iot.us-west-2.amazonaws.com"
#CA_ROOT_CERT_FILE = "put AWS IoT Root Certificate File Name here"
CA_ROOT_CERT_FILE = "/home/linaro/root-CA.crt"
#THING_CERT_FILE = "put your Thing's Certificate File Name here"
THING_CERT_FILE = "/home/linaro/xxxxxxxxxx-certificate.pem.crt"
#THING_PRIVATE_KEY = "put your Thing's Private Key File Name here"
THING_PRIVATE_KEY = "/home/linaro/xxxxxxxxxx-private.pem.key"


spi = spidev.SpiDev()
spi.open(0,0)
spi.max_speed_hz=10000
spi.mode = 0b00
spi.bits_per_word = 8
channel_select_temp=[0x01, 0xA0, 0x00] #1010 0000 ADC2 temperatura (CH 1) - terminal A2 e A3
channel_select_ldr=[0x01, 0xC0, 0x00] #1100 0000 ADC1 ldr (CH 2) - terminal A0 e A1
channel_select_potenciometro=[0x01, 0xE0, 0x00] #1110 0000 ADC2 potenciometro (CH 3) - terminal A2 e A3

arq = open('TARC.txt', 'w')

relay = LED('GPIO-A') #Saída digital D1 (saída de alarme)
water_level = Button('GPIO-C') #Entrada digital D2 (sensor de nível)
tilt = Tilt('GPIO-G') #Entrada digital D4 (terremoto)

x = 1
temp_value_old = 0
ldr_value_old = 0
shake_value = 0
shake_var = 0
shake_value_old = 0
temperature = 0
ldr = 0
state = 0
terremoto = "OK"
enchente = "OK"
tempestade = "OK"
timetopublish = 0
firstpass = 1
initial_value = 0
enchente_alarme = 0
tempestade_atenção = 0
tempestade_alarme = 0
terremoto_atenção = 0
terremoto_alarme = 0
high_ldr = 0
high_temp = 0
medium_ldr = 0
medium_temp = 0

# Define on_publish event function
def on_publish(client, userdata, mid):
    print ("Message Published...")

def on_connect(client, userdata, flags, rc):
    print("Connected with result code "+str(rc))

# Initiate MQTT Client
mqttc = mqtt.Client()

# Register publish callback function
mqttc.on_publish = on_publish

# Configure TLS Set
mqttc.tls_set(CA_ROOT_CERT_FILE, certfile=THING_CERT_FILE, keyfile=THING_PRIVATE_KEY, cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLSv1_2, ciphers=None)

# Connect with MQTT Broker
mqttc.connect(MQTT_HOST, MQTT_PORT, MQTT_KEEPALIVE_INTERVAL)
mqttc.loop_start()

if __name__=='__main__':
    gpio_cs = gpio.GPIO(18, gpio.DIRECTION_OUTPUT)
    with gpio.request_gpios([gpio_cs]):

        a = datetime.datetime.now()
        while True:

#Terremoto
            if tilt.is_tilted():
                terremoto = "ATENÇÃO"

#Enchente
            if water_level.is_pressed():
                enchente = "ALARME"
                relay.on()
            else:
                enchente = "OK"
                relay.off()

#Tempestade
            gpio_cs.set_high()
            sleep(0.00001)
            gpio_cs.set_low()
            rx = spi.xfer(channel_select_potenciometro)
            gpio_cs.set_high()
            shake_value = (rx[1] << 8) & 0b1100000000
            shake_value = shake_value | (rx[2] & 0xff)
            if firstpass == 1:
                ldr_value_old = shake_value

            if shake_value > (initial_value + 200):
                terremoto = "ALARME"
                relay.on()
            else:
                relay.off()

            gpio_cs.set_high()
            sleep(0.00001)
            gpio_cs.set_low()
            rx = spi.xfer(channel_select_temp)
            gpio_cs.set_high()

            temp_value = (rx[1] << 8) & 0b1100000000
            temp_value = temp_value | (rx[2] & 0xff)
            temp_value = temp_value/10
            if firstpass == 1:
                temp_value_old = temp_value

            if temp_value > (temp_value_old + 0.7):
               high_temp = 1
            if temp_value > (temp_value_old + 0.2):
               medium_temp = 1
   
            if high_temp == 1:
                if temp_value < (temp_value_old + 0.35):
                    high_temp = 0
                    if tempestade == "ALARME":
                        tempestade = "ATENÇÃO"
            if medium_temp == 1:
                if temp_value < (temp_value_old + 0.1):
                    medium_temp = 0
                    tempestade = "OK"


            gpio_cs.set_high()
            sleep(0.00001)
            gpio_cs.set_low()
            rx = spi.xfer(channel_select_ldr)
            gpio_cs.set_high()

            ldr_value = (rx[1] << 8) & 0b1100000000
            ldr_value = ldr_value | (rx[2] & 0xff)
            ldr_value = ldr_value - 470
            if ldr_value < 0:
                ldr_value = 0
            if firstpass == 1:
                ldr_value_old = ldr_value

            firstpass = 0

            if ldr_value < (ldr_value_old - 80):
               high_ldr = 1
               medium_ldr = 1
            if ldr_value < (ldr_value_old - 50):
               medium_ldr = 1

            if high_ldr == 1:
                if ldr_value > (ldr_value_old - 40):
                    high_ldr = 0
                    if tempestade == "ALARME":
                        tempestade = "ATENÇÃO"
            if medium_ldr == 1:
                if ldr_value > (ldr_value_old - 25):
                    medium_ldr = 0
                    tempestade = "OK"
             
            if high_temp and high_ldr:
                tempestade = "ALARME"
            else:
                if medium_temp and medium_ldr:
                    tempestade = "ATENÇÃO"

            b = datetime.datetime.now()
            delta = b - a
            delta = int(delta.total_seconds()) # seconds
            if delta > 9:
                a = datetime.datetime.now()

                print ("time to publish")
                if enchente_alarme == 0:
                    if enchente == "ALARME":
                        evento = "ENCHENTE "+"http://www.google.pt/maps/place/-23.581497,-47.526555"
                        mqttc.publish("Enchente/alarme", evento, qos=1)
                        enchente_alarme = 1

                print("Published check")
                if terremoto_atenção == 0:
                    if terremoto == "ATENÇÃO":
                        print("Published ok")
                        evento = "TERREMOTO "+"http://www.google.pt/maps/place/-23.581497,-47.526555"
                        mqttc.publish("Terremoto/atenção", evento, qos=1)
                        terremoto_atenção = 1

                if terremoto_alarme == 0:
                    if terremoto == "ALARME":
                        evento = "TERREMOTO "+"http://www.google.pt/maps/place/-23.581497,-47.526555"
                        mqttc.publish("Terremoto/alarme", evento, qos=1)
                        terremoto_alarme = 1

                if tempestade_atenção == 0:
                    if tempestade == "ATENÇÃO":
                        evento = "TEMPESTADE "+"http://www.google.pt/maps/place/-23.581497,-47.526555"
                        mqttc.publish("Tempestade/atenção", evento, qos=1)
                        tempestade_atenção = 1

                if tempestade_alarme == 0:
                    if tempestade == "ALARME":
                        evento = "TEMPESTADE "+"http://www.google.pt/maps/place/-23.581497,-47.526555"
                        mqttc.publish("Tempestade/alarme", evento, qos=1)
                        tempestade_alarme = 1

#publish publish to device shadow
                payload = {
                   "state": {
                   "reported": {
                   "datetime": str(datetime.datetime.now()),
                   "temperature": temp_value,
                   "ldr": ldr_value
                              }
                          }
                       }
                mqttc.publish("$aws/things/TARC/shadow/update", json.dumps(payload), qos=1)

#publish for dynamodb
                payload = {
                   "datetime": str(datetime.datetime.now()),
                   "temperature": str(temp_value),
                   "ldr": str(ldr_value)
                       }
                mqttc.publish("TARC/sensors", json.dumps(payload), qos=1)

#registro em arquivo
                arq.write(str(x)+" -> temp = "+str(temp_value)+", ldr = "+str(ldr_value))
                arq.write("\n")
                x = x + 1

                dweepy.dweet_for(
                'tarc',
                {
                    'datetime': time,
                    'temperature': temp_value,
                    'ldr': ldr_value,
                    'terremoto': terremoto,
                    'enchente': enchente,
                    'tempestade': tempestade,
                    'latitude': -23.581497,
                    'longitude': -47.526555,
                })
