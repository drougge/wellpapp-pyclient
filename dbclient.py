# -*- coding: iso-8859-1 -*-

import socket, types

class EResponse(Exception): pass
class EDuplicate(EResponse): pass

class dbclient:
	def __init__(self, host, port):
		self.server = (host, port)
		self.userpass = None
		self.auth_ok = False
		self.is_connected = False
	def _reconnect(self):
		if self.is_connected: return
		self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.sock.connect(self.server)
		self.fh = self.sock.makefile()
		self.is_connected = True
		self.auth_ok = False
		if self.userpass: self._send_auth()
	def _writeline(self, line, retry=True):
		self._reconnect()
		line = line + "\n"
		try:
			self.sock.send(line)
		except:
			self.is_connected = False
			if retry:
				self._reconnect()
				self.sock.send(line)
	def _readline(self):
		return self.fh.readline()
	def _parse_search(self, line, posts, wanted):
		if line == "OK\n": return True
		if line[0] != "R": raise EResponse(line)
		tags = []
		guids = []
		f = {}
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
			elif type == "F":
				field, value = data.split("=", 1)
				f[field] = value
			else:
				raise EResponse(line)
		if not md5: raise EResponse(line)
		if md5 in posts: raise EDuplicate(md5)
		if not wanted or "tagname" in wanted: f["tagname"] = tags
		if not wanted or "tagguid" in wanted: f["tagguid"] = guids
		posts[md5] = f
	def _search_post(self, search, wanted = None):
		self._writeline(search)
		posts = {}
		while not self._parse_search(self._readline(), posts, wanted): pass
		return posts
	def get_post(self, md5):
		posts = self._search_post("SPM" + md5 + " Ftagname Ftagguid Fext Fcreated Fwidth Fheight")
		if not md5 in posts: return None
		return posts[md5]
	def _list(self, data):
		if not data: return []
		if type(data) == types.StringType: return [data]
		return data
	def search_post(self, tags=None, guids=None, excl_tags=None, excl_guids=None , wanted=None):
		search = "SP"
		for want in self._list(wanted):
			search += "F" + want + " "
		for tag in self._list(tags):
			search += "TN" + tag + " "
		for guid in self._list(guids):
			search += "TG" + guid + " "
		for tag in self._list(excl_tags):
			search += "tN" + tag + " "
		for guid in self._list(excl_guids):
			search += "tG" + guid + " "
		return self._search_post(search, wanted)
	def _send_auth(self):
		self._writeline("a" + self.userpass[0] + " " + self.userpass[1], False)
		if self._readline() == "OK\n": self.auth_ok = True
	def auth(self, user, password):
		self.userpass = (user, password)
		self._send_auth()
		return self.auth_ok
