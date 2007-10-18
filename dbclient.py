# -*- coding: iso-8859-1 -*-

import socket

class dbclient:
	def __init__(self, host, port):
		self.server = (host, port)
		self.is_connected = False
	def reconnect(self):
		if self.is_connected: return
		self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.sock.connect(self.server)
		self.fh = self.sock.makefile()
		self.is_connected = True
	def get_tags(self, md5):
		self.reconnect()
		self.sock.send("SPM" + md5 + " Fext Ftagname Ftagid\n")
		tags = []
		guids = []
		ext = None
		found = None
		while True:
			line = self.fh.readline()
			if line == "OK\n": break
			if line[0] != "R": raise line
			for token in line[1:].split():
				type = token[0]
				data = token[1:]
				if type == "P":
					found = data
				elif type == "T":
					tags.append(data)
				elif type == "G":
					guids.append(data)
				elif type == "E":
					ext = data
				else:
					raise "Bad response: " + line
		if not found: return None
		if md5 != found: raise "Wrong post"
		return (tags, guids, ext)
