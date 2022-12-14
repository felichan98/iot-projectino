import serial
import serial.tools.list_ports

import configparser

import paho.mqtt.client as mqtt

id_temp_actuator = 2

"""
This bridge receives data from the cloud and sends them to actuators through serial port.

TESTING: I have to pilot the colors of a led strip. This script will subscribe to the topic "led_messages" on hivemqtt broker, translate the messages to set low level byte encoding (see doc), and send them on serial. 

Commands will be published by Windows MQTTX client.
"""

class Bridge():

	def __init__(self):
		self.config = configparser.ConfigParser()
		self.config.read('config_receiver.ini')
		self.setupSerial()
		self.setupMQTT()
  
	def setupSerial(self):
		self.ser = None

		if self.config.get("Serial","UseDescription", fallback=False):
			self.portname = self.config.get("Serial","PortName", fallback="COM5")
		else:
			print("list of available ports: ")
			ports = serial.tools.list_ports.comports()

			for port in ports:
				print (port.device)
				print (port.description)
				if self.config.get("Serial","PortDescription", fallback="arduino").lower() \
						in port.description.lower():
					self.portname = port.device

		try:
			if self.portname is not None:
				print ("connecting to " + self.portname)
				self.ser = serial.Serial(self.portname, 9600, timeout=0)
		except:
			self.ser = None

		# self.ser.open()

		# internal input buffer from serial
		self.inbuffer = []

	def setupMQTT(self):
		self.clientMQTT = mqtt.Client("ryanna")
		self.clientMQTT.on_connect = self.on_connect
		self.clientMQTT.on_message = self.on_message
		print("connecting to MQTT broker...")
		self.clientMQTT.connect("broker.hivemq.com",
			port= 1883, keepalive= 60)

		self.clientMQTT.loop_start()



	def on_connect(self, client, userdata, flags, rc):
		print("Connected with result code " + str(rc))

		# Subscribing in on_connect() means that if we lose the connection and
		# reconnect then subscriptions will be renewed.
		self.clientMQTT.subscribe("led_messages")
		self.clientMQTT.subscribe("smartoffice/building_1/room_1/actuators/temperature")


	# The callback for when a PUBLISH message is received from the server.
	def on_message(self, client, userdata, msg):
		print(msg.topic + " " + str(msg.payload))
  
		if msg.topic=='smartoffice/building_1/room_1/actuators/temperature':
			temperature = int(msg.payload.decode("utf-8"))
			print('{}{}'.format("Temperature: ", temperature))
   
			command = bytearray()
			command.append(id_temp_actuator)
			command.append(temperature)
			command.append(255) #ending byte
   
			self.ser.write(command)
  
		if msg.topic=='led_messages':
			print('{}{}'.format("Le payload", msg.payload))
   
		match msg.payload:
			case b'{\n  "msg": "RED"\n}':
				print("I'm in RED CASE!!")
				self.ser.write (b'\x01\xff')

			case b'{\n  "msg": "BLUE"\n}':
				self.ser.write (b'\x05\xff')

			case b'{\n  "msg": "GREEN"\n}':
				self.ser.write (b'\x04\xff')
    
	def loop(self):
		# infinite loop for serial managing
		#
		while (True):
			#look for a byte from serial
			if not self.ser is None:

				if self.ser.in_waiting>0:
					# data available from the serial port
					lastchar=self.ser.read(1)

					if lastchar==b'\xfe': #EOL
						print("\nValue received from light sensor!")
						print(int.from_bytes(self.inbuffer[1], byteorder='little'))
						self.clientMQTT.publish('smartoffice/building_1/room_1/sensors/light/', '{}:{}'.format('value', int.from_bytes(self.inbuffer[1], byteorder='little')))
           				#self.useData()
						self.inbuffer =[]
					else:
						# append
						self.inbuffer.append (lastchar)

	def useData(self):
		# I have received a packet from the serial port. I can use it
		if len(self.inbuffer)<3:   # at least header, size, footer
			return False
		# split parts
		if self.inbuffer[0] != b'\xff':
			return False

		numval = int.from_bytes(self.inbuffer[1], byteorder='little')

		for i in range (numval):
			val = int.from_bytes(self.inbuffer[i+2], byteorder='little')
			strval = "Sensor %d: %d " % (i, val)
			print(strval)
			self.clientMQTT.publish('smartoffice/building_1/room_1/sensors/light/',  self.inbuffer[1])

   
if __name__ == '__main__':
    print("Bridge Started")
    br=Bridge()
    br.loop()
    

