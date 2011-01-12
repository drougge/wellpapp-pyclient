# -*- coding: iso-8859-1 -*-

import socket, base64, codecs, os, hashlib

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

def _tagspec(type, value):
	if value[0] in "~!":
		type = value[0] + type
		value = value[1:]
	return type + value

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
		if line == u"OK\n": return True
		if line[0] != u"R": raise EResponse(line)
		tags = []
		guids = []
		impltags = []
		implguids = []
		f = {}
		md5 = None
		seen = set()
		for token in line[1:].split():
			type = token[0]
			data = token[1:]
			if type == u"P":
				md5 = str(data)
			elif type == u"T":
				tags.append(data)
			elif type == u"G":
				guids.append(str(data))
			elif type == u"I":
				type = data[0]
				data = data[1:]
				if type == u"T":
					impltags.append(data)
				if type == u"G":
					implguids.append(str(data))
			elif type == u"F":
				field, value = data.split(u"=", 1)
				field = str(field)
				if field in _field_parsers:
					f[field] = _field_parsers[field](value)
				else:
					f[field] = value
			else:
				raise EResponse(line)
		if not md5: raise EResponse(line)
		if md5 in seen: raise EDuplicate(md5)
		seen.add(md5)
		if not wanted or "tagname" in wanted: f["tagname"] = tags
		if not wanted or "tagguid" in wanted: f["tagguid"] = guids
		if wanted and "implied" in wanted:
			if "tagname" in wanted: f["impltagname"] = impltags
			if "tagguid" in wanted: f["impltagguid"] = implguids
		f["md5"] = md5
		posts.append(f)
	def _search_post(self, search, wanted = None):
		self._writeline(search)
		posts = []
		while not self._parse_search(self._readline(), posts, wanted): pass
		return posts
	def get_post(self, md5, separate_implied = False):
		md5 = str(md5)
		search = "SPM" + md5 + " Ftagname Ftagguid Fext Fcreated Fwidth Fheight"
		if separate_implied: search += " Fimplied"
		posts = self._search_post(search)
		if not posts or posts[0]["md5"] != md5: return None
		return posts[0]
	def _list(self, data, converter = _utf):
		if not data: return []
		if isinstance(data, basestring): return [converter(data)]
		return map(converter, data)
	def search_post(self, tags=None, guids=None, excl_tags=None,
	                excl_guids=None , wanted=None, order=None):
		search = "SP"
		for want in self._list(wanted, str):
			search += "F" + want + " "
		for tag in self._list(tags):
			search += "T" + _tagspec("N", tag) + " "
		for guid in self._list(guids, str):
			search += "T" + _tagspec("G", guid) + " "
		for tag in self._list(excl_tags):
			search += "t" + _tagspec("N", tag) + " "
		for guid in self._list(excl_guids, str):
			search += "t" + _tagspec("G", guid) + " "
		for o in self._list(order, str):
			search += "O" + o + " "
		return self._search_post(search, wanted)
	def _send_auth(self):
		self._writeline("a" + self.userpass[0] + " " + self.userpass[1], False)
		if self._readline() == "OK\n": self.auth_ok = True
	def auth(self, user, password):
		self.userpass = (_utf(user), _utf(password))
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
		cmd  = "AP" + str(md5)
		cmd += " width=" + self._hexstr(width)
		cmd += " height=" + self._hexstr(height)
		cmd += " filetype=" + str(filetype)
		if rating: cmd += " rating=" + _utf(rating)
		if source: cmd += " source=" + self._enc(source)
		if title:  cmd += " title=" + self._enc(title)
		if date:
			if type(date) is not int:
				date = int(date.strftime("%s"))
			cmd += " image_date=" + self._hexstr(date)
		self._writeline(cmd)
		res = self._readline()
		if res != u"OK\n": raise EResponse(res)
	def _rels(self, c, md5, rels):
		cmd = "R" + c + str(md5)
		for rel in self._list(rels, str):
			cmd += " " + rel
		self._writeline(cmd)
		res = self._readline()
		if res != u"OK\n": raise EResponse(res)
	def add_rels(self, md5, rels):
		self._rels("R", md5, rels)
	def remove_rels(self, md5, rels):
		self._rels("r", md5, rels)
	def _parse_rels(self, line, rels):
		if line == u"OK\n": return True
		if line[0] != u"R": raise EResponse(line)
		a = str(line[1:]).split()
		p = a[0]
		l = []
		if p in rels: l = rels[p]
		for rel in a[1:]:
			l.append(rel)
		rels[p] = l
	def post_rels(self, md5):
		md5 = str(md5)
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
		if res != u"OK\n": raise EResponse(res)
	def add_alias(self, name, origin_guid):
		cmd = "AAG" + str(origin_guid) + " N" + _utf(name)
		self._writeline(cmd)
		res = self._readline()
		if res != u"OK\n": raise EResponse(res)
	def add_implies(self, set_tag, implied_tag, priority):
		cmd = "II" + str(set_tag) + " I" + str(implied_tag) + ":" + str(priority)
		self._writeline(cmd)
		res = self._readline()
		if res != u"OK\n": raise EResponse(res)
	def tag_post(self, md5, full_tags, weak_tags):
		tags = map(str, full_tags) + map(lambda t: "~" + str(t), weak_tags)
		cmd = "TP" + str(md5) + " T".join([""] + tags)
		self._writeline(cmd)
		res = self._readline()
		if res != u"OK\n": raise EResponse(res)
	def find_tag(self, name, resdata = None):
		name = _utf(name)
		assert " " not in name
		cmd = "STEAN" + name
		self._writeline(cmd)
		res = self._readline()
		if res == u"OK\n": return None
		if res[:2] != u"RG": raise EResponse(res)
		guid = str(res.split()[0][2:])
		if resdata:
			hexint = lambda s: int(s, 16)
			dummy = lambda s: s
			incl = {u"N": ("name", dummy),
			        u"T": ("type", dummy),
			        u"P": ("posts", hexint),
			        u"W": ("weak_posts", hexint)}
			for data in res.split()[1:]:
				if data[0] in incl:
					name, parser = incl[data[0]]
					resdata[name] = parser(data[1:])
		res = self._readline()
		if res != u"OK\n": raise EResponse(res)
		return guid
	def thumb_path(self, md5, size):
		md5 = str(md5)
		return os.path.join(self.cfg.thumb_base, str(size), md5[0], md5[1:3], md5)
	def pngthumb_path(self, md5, ft, size):
		fn = str(md5) + "." + str(ft)
		md5 = hashlib.md5(fn).hexdigest()
		return os.path.join(self.cfg.thumb_base, str(size), md5[0], md5[1:3], md5)
	def image_path(self, md5):
		md5 = str(md5)
		return os.path.join(self.cfg.image_base, md5[0], md5[1:3], md5)
