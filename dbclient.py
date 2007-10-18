# -*- coding: iso-8859-1 -*-

import socket

class EResponse(Exception): pass

class dbclient:
	def __init__(self, host, port):
		self.server = (host, port)
		self.is_connected = False
	def _reconnect(self):
		if self.is_connected: return
		self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.sock.connect(self.server)
		self.fh = self.sock.makefile()
		self.is_connected = True
	def _writeline(self, line):
		self._reconnect()
		line = line + "\n"
		try:
			self.sock.send(line)
		except:
			self.is_connected = False
			self._reconnect()
			self.sock.send(line)
	def _readline(self):
		return self.fh.readline()
	def _parse_search(self, line, posts):
		if line == "OK\n": return True
		if line[0] != "R": raise EResponse(line)
		tags = []
		guids = []
		ext = None
		md5 = None
		for token in line[1:].split():
			type = token[0]
			data = token[1:]
			if type == "P":
				md5 = data
			elif type == "T":
				tags.append(data)
			elif type == "G":
				guids.append(data)
			elif type == "E":
				ext = data
			else:
				raise EResponse(line)
		if not md5: raise EResponse(line)
		if md5 in posts: raise "Duplicate response " + md5
		posts[md5] = (tags, guids, ext)
	def _search_post(self, search):
		self._writeline(search)
		posts = {}
		while not self._parse_search(self._readline(), posts): pass
		return posts
	def get_post(self, md5):
		posts = self._search_post("SPM" + md5 + " Fext Ftagname Ftagid")
		if not md5 in posts: return None
		return posts[md5]
	def search_post(self, tags=None, guids=None, excl_tags=None, excl_guids=None , wanted=None):
		search = "SP"
		for want in wanted or []:
			search += "F" + want + " "
		for tag in tags or []:
			search += "TN" + tag + " "
		for guid in guids or []:
			search += "TG" + guid + " "
		for tag in excl_tags or []:
			search += "tN" + tag + " "
		for guid in excl_guids or []:
			search += "tG" + guid + " "
		return self._search_post(search)
