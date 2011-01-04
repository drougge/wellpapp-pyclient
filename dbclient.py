# -*- coding: iso-8859-1 -*-

import socket, base64, codecs, os

class EResponse(Exception): pass
class EDuplicate(EResponse): pass

_field_parsers = {
	"created": lambda x: int(x, 16),
	"width"  : lambda x: int(x, 16),
	"height" : lambda x: int(x, 16),
	"score"  : int,
}

def _utf(s):
	if type(s) is not unicode:
		try:
			s = s.decode("utf-8")
		except Exception:
			s = s.decode("iso-8859-1")
	assert u" " not in s
	return s.encode("utf-8")

class dbcfg:
	def __init__(self):
		RC_NAME = ".wellpapprc"
		path = "/"
		RCs = [os.path.join(os.environ["HOME"], RC_NAME)]
		for dir in os.getcwd().split(os.path.sep):
			path = os.path.join(path, dir)
			RC = os.path.join(path, RC_NAME)
			if os.path.exists(RC): RCs.append(RC)
		for RC in RCs:
			self._load(RC)
	def _load(self, fn):
		for line in file(fn):
			line = line.strip()
			if line[0] != "#":
				a = line.split("=", 1)
				assert(len(a) == 2)
				self.__dict__[a[0]] = a[1]

class dbclient:
	def __init__(self, cfg = None):
		if not cfg:
			cfg = dbcfg()
		self.cfg = cfg
		self.server = (cfg.server, int(cfg.port))
		self.userpass = None
		self.auth_ok = False
		self.is_connected = False
	def _reconnect(self):
		if self.is_connected: return
		self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.sock.connect(self.server)
		self.utfdec = codecs.getdecoder("utf8")
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
		return self.utfdec(self.fh.readline())[0]
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
				if field in _field_parsers:
					f[field] = _field_parsers[field](value)
				else:
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
		post = posts[md5]
		post["md5"] = md5
		return post
	def _list(self, data):
		if not data: return []
		if isinstance(data, basestring): return [data]
		return data
	def search_post(self, tags=None, guids=None, excl_tags=None, excl_guids=None , wanted=None):
		search = "SP"
		for want in self._list(wanted):
			search += "F" + want + " "
		for tag in self._list(tags):
			search += "TN" + _utf(tag) + " "
		for guid in self._list(guids):
			search += "TG" + guid + " "
		for tag in self._list(excl_tags):
			search += "tN" + _utf(tag) + " "
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
	def _enc(self, str):
		while len(str) % 3: str += "\x00"
		return base64.b64encode(str, "_-")
	def _dec(self, enc):
		str = base64.b64decode(enc, "_-")
		while str[-1] == "\x00": str = str[:-1]
	def _hexstr(self, val):
		return "%x" % val;
	def add_post(self, md5, width, height, filetype, rating=None,
	             source=None, title=None, date=None):
		cmd  = "AP" + md5
		cmd += " width=" + self._hexstr(width)
		cmd += " height=" + self._hexstr(height)
		cmd += " filetype=" + filetype
		if rating: cmd += " rating=" + rating
		if source: cmd += " source=" + self._enc(source)
		if title:  cmd += " title=" + self._enc(title)
		if date:
			if type(date) is not int:
				date = int(date.strftime("%s"))
			cmd += " image_date=" + self._hexstr(date)
		self._writeline(cmd)
		res = self._readline()
		if res != "OK\n": raise EResponse(res)
	def _rels(self, c, md5, rels):
		cmd = "R" + c + md5
		for rel in self._list(rels):
			cmd += " " + rel
		self._writeline(cmd)
		res = self._readline()
		if res != "OK\n": raise EResponse(res)
	def add_rels(self, md5, rels):
		self._rels("R", md5, rels)
	def remove_rels(self, md5, rels):
		self._rels("r", md5, rels)
	def _parse_rels(self, line, rels):
		if line == "OK\n": return True
		if line[0] != "R": raise EResponse(line)
		a = line[1:].split()
		p = a[0]
		l = []
		if p in rels: l = rels[p]
		for rel in a[1:]:
			l.append(rel)
		rels[p] = l
	def post_rels(self, md5):
		cmd = "RS" + md5
		self._writeline(cmd)
		rels = {}
		while not self._parse_rels(self._readline(), rels): pass
		if not md5 in rels: return None
		return rels[md5]
	def add_tag(self, name, type = None):
		cmd = "ATN" + _utf(name)
		if type:
			cmd += " T" + _utf(type)
		self._writeline(cmd)
		res = self._readline()
		if res != "OK\n": raise EResponse(res)
	def add_alias(self, name, origin_guid):
		cmd = "AAG" + origin_guid + " N" + _utf(name)
		self._writeline(cmd)
		res = self._readline()
		if res != "OK\n": raise EResponse(res)
	def tag_post(self, md5, full_tags, weak_tags):
		tags = full_tags + map(lambda t: "~" + t, weak_tags)
		cmd = "TP" + md5 + " T".join([""] + tags)
		self._writeline(cmd)
		res = self._readline()
		if res != "OK\n": raise EResponse(res)
	def find_tag(self, name):
		name = _utf(name)
		assert " " not in name
		cmd = "STEAN" + name
		self._writeline(cmd)
		res = self._readline()
		if res == "OK\n": return None
		if res[:2] != "RG": raise EResponse(res)
		guid = res.split()[0][2:]
		res = self._readline()
		if res != "OK\n": raise EResponse(res)
		return guid
	def thumb_path(self, md5, size):
		return os.path.join(self.cfg.thumb_base, str(size), md5[0], md5[1:3], md5)
	def image_path(self, md5):
		return os.path.join(self.cfg.image_base, md5[0], md5[1:3], md5)
