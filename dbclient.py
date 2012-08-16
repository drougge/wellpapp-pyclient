# -*- coding: iso-8859-1 -*-

import socket, base64, codecs, os, hashlib, re
from fractions import Fraction
from abc import ABCMeta, abstractmethod, abstractproperty

class EResponse(Exception): pass
class EDuplicate(EResponse): pass

def _uni(s):
	if type(s) is not unicode:
		try:
			s = s.decode("utf-8")
		except Exception:
			s = s.decode("iso-8859-1")
	return s
def _utf(s, allow_space=False):
	s = _uni(s)
	if not allow_space: assert u" " not in s
	return s.encode("utf-8")

def _tagspec(type, value):
	if value[0] in "~!":
		type = value[0] + type
		value = value[1:]
	return type + value

def _enc(str):
	str = _utf(str, True)
	while len(str) % 3: str += "\x00"
	return base64.b64encode(str, "_-")
def _dec(enc):
	if not enc: return u""
	enc = _utf(enc)
	str = base64.b64decode(enc, "_-")
	while str[-1] == "\x00": str = str[:-1]
	return str.decode("utf-8")
_p_hex = lambda x: int(x, 16)
_field_sparser = {
	"created"        : _p_hex,
	"imgdate"        : _p_hex,
	"imgdate_fuzz"   : int,
	"width"          : _p_hex,
	"height"         : _p_hex,
	"score"          : int,
	"rotate"         : int,
	"source"         : _dec,
	"title"          : _dec,
}
_p_int = lambda i: str(int(i))
_p_hexint = lambda i: "%x" % (int(i),)
def _p_str(val):
	val = _utf(val)
	assert " " not in val
	return val
def _p_date(val):
	if isinstance(val, basestring) and not val.isdigit():
		from time import strptime, mktime
		date = mktime(strptime(date, "%Y:%m:%d %H:%M:%S"))
	return _p_hexint(val)
_field_cparser = {
	"width"          : _p_hexint,
	"height"         : _p_hexint,
	"score"          : _p_int,
	"rotate"         : _p_int,
	"rating"         : _p_str,
	"created"        : _p_date,
	"imgdate"        : _p_date,
	"imgdate_fuzz"   : _p_int,
	"ext"            : _p_str,
	"source"         : _enc,
	"title"          : _enc,
}

class CommentWrapper:
	"""Wrap a file so readline/iteration skips comments
	and optionally empty lines"""
	def __init__(self, fh, allow_empty=False):
		self.fh = fh
		self.allow_empty = allow_empty
	def __iter__(self):
		return self
	def next(self):
		line = self.readline()
		if not line: raise StopIteration()
		return line
	def readline(self):
		while 42:
			line = self.fh.readline()
			if not line: return line
			s = line.strip()
			if s:
				if s[0] != "#": return line
			elif self.allow_empty:
				return line

class DotDict(dict):
	__setattr__ = dict.__setitem__
	__delattr__ = dict.__delitem__
	def __getattr__(self, name):
		if name[0] == "_":
			raise AttributeError(name)
		return self.get(name)
	def __repr__(self):
		return repr(type(self)) + dict.__repr__(self)

class Post(DotDict): pass

class Tag(DotDict):
	def populate(self, res):
		res = res.split()
		alias = []
		flaglist = []
		hexint = lambda s: int(s, 16)
		dummy = lambda s: s
		incl = {u"N": ("name", dummy),
		        u"T": ("type", dummy),
		        u"A": ("alias", alias.append),
		        u"P": ("posts", hexint),
		        u"W": ("weak_posts", hexint),
		        u"F": ("flags", flaglist.append),
		        u"G": ("guid", str),
		        u"V": ("valuetype", str),
		       }
		for data in res:
			if data[0] in incl:
				name, parser = incl[data[0]]
				self[name] = parser(data[1:])
		self.alias = alias
		if flaglist:
			del self.flags
			for flag in flaglist:
				self[flag] = True
		vt = (self.valuetype or "").split("=", 1)
		if len(vt) == 2:
			self.valuetype = vt[0]
			self.value = _vtparse(_dec, *vt)

class ValueType(object):
	"""Represents the value of a tag.
	v.value is the value as an apropriate type (str, float, int).
	v.exact is an exact representation of the value (str, int, Fraction).
	v.fuzz is how inexact the value is.
	v.exact_fuzz is like .exact but for the fuzz.
	v.str (or str(v)) is a string representation of exact value+-fuzz.
	v.format() is this value formated for sending to server."""
	
	__metaclass__ = ABCMeta
	
	@abstractmethod
	def __init__(self): pass
	
	@abstractproperty
	def type(self): pass
	
	str = ""
	value = 0
	exact = 0
	fuzz = None
	exact_fuzz = None
	
	def __str__(self):
		return self.str
	def __repr__(self):
		c = self.__class__
		return c.__module__ + "." + c.__name__ + "(" + repr(self.str) + ")"
	def format(self):
		return self.str

class VTstring(ValueType):
	"""Represents the value of a tag with valuetype string.
	v.value, v.exact and v.str are all the same string.
	There is no fuzz for strings."""
	
	type = "string"
	def __init__(self, val):
		self.str = self.value = self.exact = val
	def format(self):
		return _enc(self.str)

class VTnumber(ValueType):
	def _parse(self, v, vp, vp2, fp):
		self.str = v
		a = v.split("+-", 1)
		self.exact = vp(a[0])
		self.value = vp2(self.exact)
		if len(a) == 2:
			self.exact_fuzz = fp(a[1])
			self.fuzz = vp2(self.exact_fuzz)
		else:
			self.fuzz = self.exact_fuzz = 0

class VTint(VTnumber):
	__doc__ = ValueType.__doc__
	type = "int"
	
	def __init__(self, val):
		self._parse(val, int, int, _p_hex)

class VTuint(VTnumber):
	__doc__ = ValueType.__doc__
	type = "uint"
	
	def __init__(self, val):
		self._parse(val, _p_hex, int, _p_hex)

class VTfloat(VTnumber):
	__doc__ = ValueType.__doc__
	type = "float"
	
	def __init__(self, val):
		def intfrac(v):
			try:
				return int(v)
			except ValueError:
				return Fraction(v)
		self._parse(val, intfrac, float, intfrac)

class VTf_stop(VTfloat):
	__doc__ = ValueType.__doc__
	type = "f-stop"

class VTstop(VTfloat):
	__doc__ = ValueType.__doc__
	type = "stop"
	
	def __init__(self, val):
		VTfloat.__init__(self, val)
		if isinstance(self.exact, (int, long)):
			self.value = self.exact
		if isinstance(self.exact_fuzz, (int, long)):
			self.fuzz = self.exact_fuzz

valuetypes = {"string" : VTstring,
              "int"    : VTint,
              "uint"   : VTuint,
              "float"  : VTfloat,
              "f-stop" : VTf_stop,
              "stop"   : VTstop,
             }

def _vtparse(strparse, vtype, val):
	if vtype == "string": val = strparse(val)
	return valuetypes[vtype](val)

class dbcfg(DotDict):
	def __init__(self, RC_NAME=".wellpapprc", EXTRA_RCs=[]):
		DotDict.__init__(self, dict(tagwindow_width=840, tagwindow_height=600))
		RCs = []
		if RC_NAME:
			path = "/"
			RCs = [os.path.join(os.environ["HOME"], RC_NAME)]
			for dir in os.getcwd().split(os.path.sep):
				path = os.path.join(path, dir)
				RC = os.path.join(path, RC_NAME)
				if os.path.exists(RC): RCs.append(RC)
		for RC in RCs + EXTRA_RCs:
			self._load(RC)
	def _load(self, fn):
		for line in CommentWrapper(file(fn)):
			line = line.strip()
			a = line.split("=", 1)
			assert(len(a) == 2)
			self[a[0]] = a[1]

class dbclient:
	_prot_max_len = 4096
	def __init__(self, cfg = None):
		if not cfg:
			cfg = dbcfg()
		self.cfg = cfg
		self.server = (cfg.server, int(cfg.port))
		self.userpass = None
		self.auth_ok = False
		self.is_connected = False
		self._md5re = re.compile(r"^[0-9a-f]{32}$", re.I)
		base = cfg.image_base
		if base[-1] == "/": base = base[:-1]
		base = re.escape(base)
		self._destmd5re = re.compile(r"^" + base + r"/[0-9a-f]/[0-9a-f]{2}/([0-9a-f]{32})$")
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
	def _parse_search(self, line, posts, wanted, props):
		if line == u"OK\n": return True
		if line[0] != u"R": raise EResponse(line)
		if line[1] == u"E": raise EResponse(line)
		if line[1] == u"R":
			if props != None: props["result_count"] = int(line[2:], 16)
			return
		f = Post()
		seen = set()
		pieces = line[1:].split(" :")
		for token in pieces[0].split():
			type = token[0]
			data = token[1:]
			if type == u"P":
				f.md5 = str(data)
			elif type == u"F":
				field, value = data.split(u"=", 1)
				field = str(field)
				if field in _field_sparser:
					f[field] = _field_sparser[field](value)
				else:
					f[field] = value
			else:
				raise EResponse(line)
		f.tags = []
		f.weaktags = []
		f.impltags = []
		f.implweaktags = []
		for piece in pieces[1:-1]:
			flags, data = piece.split(" ", 1)
			if flags == "I~" or flags == "~I":
				ta = f.implweaktags
			elif flags == "I":
				ta = f.impltags
			elif flags == "~":
				ta = f.weaktags
			else:
				ta = f.tags
			t = Tag()
			t.populate(data)
			ta.append(t)
		if not f.md5: raise EResponse(line)
		if f.md5 in seen: raise EDuplicate(f.md5)
		seen.add(f.md5)
		old = lambda n, full, weak: [t[n] for t in full] + [u"~" + t[n] for t in weak]
		if not wanted or "tagname" in wanted:
			f.tagname = old("name", f.tags, f.weaktags)
		if not wanted or "tagguid" in wanted:
			f.tagguid = old("guid", f.tags, f.weaktags)
		if wanted and "implied" in wanted:
			if "tagname" in wanted:
				f.impltagname = old("name", f.impltags, f.implweaktags)
			if "tagguid" in wanted:
				f.impltagguid = old("guid", f.impltags, f.implweaktags)
		else:
			del f.impltags
			del f.implweaktags
		posts.append(f)
	def _search_post(self, search, wanted = None, props = None):
		self._writeline(search)
		posts = []
		while not self._parse_search(self._readline(), posts, wanted, props): pass
		return posts
	def get_post(self, md5, separate_implied = False, wanted = None):
		md5 = str(md5)
		if not wanted:
			wanted = ["tagname", "tagguid", "tagdata", "ext", "created", "width", "height"]
		if separate_implied and "implied" not in wanted: wanted.append("implied")
		search = "SPM" + md5 + " F".join([""] + wanted)
		posts = self._search_post(search, wanted)
		if not posts or posts[0]["md5"] != md5: return None
		return posts[0]
	def delete_post(self, md5):
		md5 = str(md5)
		assert " " not in md5
		cmd = "DP" + md5
		self._writeline(cmd)
		res = self._readline()
		if res != u"OK\n": raise EResponse(res)
	def _list(self, data, converter = _utf):
		if not data: return []
		if isinstance(data, basestring): return [converter(data)]
		return map(converter, data)
	def _shuffle_minus(self, pos, neg, converter):
		pos = self._list(pos, converter)
		neg = self._list(neg, converter)
		pos1 = [t for t in pos if t[0] != "-"]
		neg1 = [t[1:] for t in pos if t[0] == "-"]
		pos2 = [t[1:] for t in neg if t[0] == "-"]
		neg2 = [t for t in neg if t[0] != "-"]
		return pos1 + pos2, neg1 + neg2
	def _build_search(self, tags=None, guids=None, excl_tags=None,
	                  excl_guids=None , wanted=None, order=None, range=None):
		search = ""
		tags, excl_tags = self._shuffle_minus(tags, excl_tags, _utf)
		guids, excl_guids = self._shuffle_minus(guids, excl_guids, str)
		for want in self._list(wanted, str):
			search += "F" + want + " "
		for tag in tags:
			search += "T" + _tagspec("N", tag) + " "
		for guid in guids:
			search += "T" + _tagspec("G", guid) + " "
		for tag in excl_tags:
			search += "t" + _tagspec("N", tag) + " "
		for guid in excl_guids:
			search += "t" + _tagspec("G", guid) + " "
		for o in self._list(order, str):
			search += "O" + o + " "
		if range != None:
			assert len(range) == 2
			search += "R" + ("%x" % range[0]) + ":" + ("%x" % range[1])
		return search
	def search_post(self, wanted=None, **kw):
		search = "SP" + self._build_search(wanted=wanted, **kw)
		props = DotDict()
		posts = self._search_post(search, wanted, props)
		return posts, props
	def _send_auth(self):
		self._writeline("a" + self.userpass[0] + " " + self.userpass[1], False)
		if self._readline() == "OK\n": self.auth_ok = True
	def auth(self, user, password):
		self.userpass = (_utf(user), _utf(password))
		self._send_auth()
		return self.auth_ok
	def _fieldspec(self, **kwargs):
		f = [_utf(f) + "=" + _field_cparser[_utf(f)](kwargs[f]) for f in kwargs]
		if not f: return ""
		return " " + " ".join(f)
	def modify_post(self, md5, **kwargs):
		md5 = str(md5)
		assert " " not in md5
		fspec = self._fieldspec(**kwargs)
		if fspec:
			cmd = "MP" + md5 + fspec
			self._writeline(cmd)
			res = self._readline()
			if res != u"OK\n": raise EResponse(res)
	def add_post(self, md5, **kwargs):
		cmd  = "AP" + str(md5)
		assert "width" in kwargs
		assert "height" in kwargs
		assert "ext" in kwargs
		cmd += self._fieldspec(**kwargs)
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
		if line[1] == u"E": raise EResponse(line)
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
	def add_tag(self, name, type = None, guid = None):
		cmd = "ATN" + _utf(name)
		if type:
			cmd += " T" + _utf(type)
		if guid:
			cmd += " G" + _utf(guid)
		self._writeline(cmd)
		res = self._readline()
		if res != u"OK\n": raise EResponse(res)
	def add_alias(self, name, origin_guid):
		cmd = "AAG" + str(origin_guid) + " N" + _utf(name)
		self._writeline(cmd)
		res = self._readline()
		if res != u"OK\n": raise EResponse(res)
	def remove_alias(self, name):
		cmd = "DAN" + _utf(name)
		self._writeline(cmd)
		res = self._readline()
		if res != u"OK\n": raise EResponse(res)
	def _addrem_implies(self, addrem, set_tag, implied_tag, priostr):
		assert " " not in set_tag
		assert " " not in implied_tag
		implied_tag = str(implied_tag)
		if implied_tag[0] == "-":
			add = " i" + implied_tag[1:]
		else:
			add = " I" + implied_tag
		cmd = "I" + addrem + str(set_tag) + add + priostr
		self._writeline(cmd)
		res = self._readline()
		if res != u"OK\n": raise EResponse(res)
	def add_implies(self, set_tag, implied_tag, priority=0):
		self._addrem_implies("I", set_tag, implied_tag, ":" + str(priority))
	def remove_implies(self, set_tag, implied_tag):
		self._addrem_implies("i", set_tag, implied_tag, "")
	def _parse_implies(self, data):
		res = self._readline()
		if res == u"OK\n": return
		set_guid, impl_guid = map(str, res.split(" ", 1))
		assert set_guid[:2] == "RI"
		set_guid = set_guid[2:]
		for impl_guid in impl_guid.split():
			impl_guid, prio = impl_guid.split(":")
			if impl_guid[0] == "i":
				impl_guid = "-" + impl_guid[1:]
			else:
				assert impl_guid[0] == "I"
				impl_guid = impl_guid[1:]
			if set_guid not in data: data[set_guid] = []
			data[set_guid].append((impl_guid, int(prio)))
		return True
	def tag_implies(self, tag, reverse=False):
		tag = str(tag)
		assert " " not in tag
		cmd = "IR" if reverse else "IS"
		self._writeline(cmd + tag)
		data = {}
		while self._parse_implies(data): pass
		if reverse:
			rev = []
			for itag in data:
				impl = data[itag]
				assert len(impl) == 1
				impl = impl[0]
				assert len(impl) == 2
				ttag = impl[0]
				if ttag[0] == "-":
					assert ttag[1:] == tag
					rev.append(("-" + itag, impl[1]))
				else:
					assert ttag == tag
					rev.append((itag, impl[1]))
			return rev or None
		if tag in data: return data[tag]
	def merge_tags(self, into_t, from_t):
		assert " " not in into_t
		assert " " not in from_t
		cmd = "MTG" + str(into_t) + " M" + str(from_t)
		self._writeline(cmd)
		res = self._readline()
		if res != u"OK\n": raise EResponse(res)
	def mod_tag(self, guid, name=None, type=None):
		guid = _utf(guid)
		assert " " not in guid
		cmd = "MTG" + guid
		if name:
			name = _utf(name)
			assert " " not in name
			cmd += " N" + name
		if type:
			type = _utf(type)
			assert " " not in type
			cmd += " T" + type
		self._writeline(cmd)
		res = self._readline()
		if res != u"OK\n": raise EResponse(res)
	def _tag2spec(self, t):
		if type(t) in (tuple, list):
			assert len(t) == 2
			g = str(t[0])
			if t[1] is None: return g
			return g + "=" + t[1].format()
		else:
			return str(t)
	def tag_post(self, md5, full_tags=None, weak_tags=None, remove_tags=None):
		tags = map(self._tag2spec, full_tags or []) + map(lambda t: "~" + self._tag2spec(t), weak_tags or [])
		remove_tags = map(str, remove_tags or [])
		init = "TP" + str(md5)
		cmd = init
		for tag in map(lambda t: " T" + t, tags) + map(lambda t: " t" + t, remove_tags):
			assert " " not in tag[1:]
			if len(cmd) + len(tag) > self._prot_max_len:
				self._writeline(cmd)
				res = self._readline()
				if res != u"OK\n": raise EResponse(res)
				cmd = init
			cmd += tag
		if cmd != init:
			self._writeline(cmd)
			res = self._readline()
			if res != u"OK\n": raise EResponse(res)
	def _parse_tagres(self, resdata = None):
		res = self._readline()
		if res == u"OK\n": return
		if res[0] != u"R": raise EResponse(res)
		if res[1] == u"E": raise EResponse(res)
		if res[1] == u"R": return True # ignore count for now
		t = Tag()
		t.populate(res[1:])
		if resdata != None: resdata.append(t)
		return t
	def find_tags(self, matchtype, name, range=None, order=None, **kw):
		if kw:
			filter = self._build_search(**kw)
			if filter:
				filter = " :" + filter
		else:
			filter = ""
		matchtype = str(matchtype)
		assert " " not in matchtype
		name = _utf(name)
		assert " " not in name
		cmd = "ST" + matchtype + name
		for o in self._list(order, str):
			assert " " not in o
			cmd += " O" + o
		if range != None:
			assert len(range) == 2
			cmd += " R%x:%x" % range
		self._writeline(cmd + filter)
		tags = []
		while self._parse_tagres(tags): pass
		return tags
	def parse_tag(self, spec):
		spec = _utf(spec)
		if spec[0] in "~-!":
			prefix = spec[0]
			spec = spec[1:]
		else:
			prefix = ""
		tag = self.find_tag(spec)
		if tag: return (prefix + tag, None)
		a = spec.split("=", 1)
		if len(a) == 2:
			tag = self.find_tag(a[0])
			if not tag: return None
			tag = self.get_tag(tag)
			if not tag or tag.valuetype in (None, "none"): return None
			if a[1]:
				val = _vtparse(_uni, tag.valuetype, a[1])
			else:
				val = None
			return (prefix + tag.guid, val)
	def find_tag(self, name, resdata=None, with_prefix=False):
		name = _utf(name)
		if with_prefix and name[0] in "~-!":
			prefix = str(name[0])
			name = name[1:]
		else:
			prefix = ""
		tags = self.find_tags("EAN", name)
		if not tags: return None
		assert len(tags) == 1
		guid = tags[0].guid
		if resdata != None: resdata.update(tags[0])
		return prefix + guid
	def get_tag(self, guid, with_prefix=False):
		guid = _utf(guid)
		if with_prefix and guid[0] in u"~-!":
			prefix = guid[0]
			guid = guid[1:]
		else:
			prefix = u""
		tags = self.find_tags("EAG", guid)
		if not tags: return None
		assert len(tags) == 1
		data = tags[0]
		assert guid == data.guid
		data["name"] = prefix + data["name"]
		return data
	def begin_transaction(self):
		self._writeline("tB")
		res = self._readline()
		return res == u"OK\n"
	def end_transaction(self):
		self._writeline("tE")
		res = self._readline()
		return res == u"OK\n"
	def thumb_path(self, md5, size):
		md5 = str(md5)
		return os.path.join(self.cfg.thumb_base, str(size), md5[0], md5[1:3], md5)
	def pngthumb_path(self, md5, ft, size):
		fn = str(md5) + "." + str(ft)
		md5 = hashlib.md5(fn).hexdigest()
		return os.path.join(self.cfg.thumb_base, str(size), md5[0], md5[1:3], md5)
	def image_dir(self, md5):
		md5 = str(md5)
		return os.path.join(self.cfg.image_base, md5[0], md5[1:3])
	def image_path(self, md5):
		md5 = str(md5)
		return os.path.join(self.image_dir(md5), md5)
	def postspec2md5(self, spec, default = None):
		if os.path.lexists(spec) and not os.path.isdir(spec):
			# some extra magic to avoid reading the files if possible
			if os.path.islink(spec):
				dest = os.readlink(spec)
				m = self._destmd5re.match(dest)
				if m: return m.group(1)
			# Even when the fuse fs returns files, bare IDs are links
			aspec = spec.split("/")
			afn = aspec[-1].split(".")
			if len(afn) == 2 and self._md5re.match(afn[0]):
				aspec[-1] = afn[0]
				shortspec = "/".join(aspec)
				if os.path.islink(shortspec):
					dest = os.readlink(shortspec)
					m = self._destmd5re.match(dest)
					if m: return m.group(1)
			# Oh well, hash the file.
			return hashlib.md5(file(spec).read()).hexdigest()
		if self._md5re.match(spec): return spec
		return default
	def order(self, tag, posts):
		tag = str(tag)
		assert " " not in tag
		init = "OG" + tag
		cmd = init
		anything = False
		for post in map(str, posts):
			cmd += " P" + post
			anything = True
			if len(cmd) + 64 > self._prot_max_len:
				self._writeline(cmd)
				res = self._readline()
				if res != u"OK\n": raise EResponse(res)
				cmd = init + " P" + post
				anything = False
		if anything:
			self._writeline(cmd)
			res = self._readline()
			if res != u"OK\n": raise EResponse(res)
	def metalist(self, name):
		cmd = "L" + _utf(name)
		self._writeline(cmd)
		res = self._readline()
		names = []
		while res != u"OK\n":
			if res[:2] != u"RN": raise EResponse(res)
			names.append(res[2:-1])
			res = self._readline()
		return names
	def thumb_fns(self, m, ft):
		sizes = self.cfg.thumb_sizes.split()
		jpeg_fns = map(lambda z: (self.thumb_path(m, int(z)), int(z)), sizes)
		png_fns = map(lambda n, z: (self.pngthumb_path(m, ft, n), z),
			      ("normal", "large"), (128, 256))
		return jpeg_fns, png_fns
	def save_thumbs(self, m, img, ft, rot, force=False):
		import Image
		from PIL import PngImagePlugin
		from dbutil import make_pdirs
		fn = self.image_path(m)
		mtime = os.stat(fn).st_mtime
		if not img:
			from dbutil import raw_wrapper
			img = Image.open(raw_wrapper(open(fn, "rb")))
		img.load()
		# PIL rotates CCW
		rotation = {90: Image.ROTATE_270, 180: Image.ROTATE_180, 270: Image.ROTATE_90}
		if rot in rotation: img = img.transpose(rotation[rot])
		w, h = img.size
		if img.mode == "1":
			# We want to scale B/W as grayscale.
			img = img.convert("L")
		if img.mode == "P" and "transparency" in img.info:
			# special case for transparent gif
			img = img.convert("RGBA")
		if img.mode not in ("RGB", "RGBA", "L", "LA"):
			# Are there other modes to worry about?
			img = img.convert("RGB")
		jpeg_fns, png_fns = self.thumb_fns(m, ft)
		jpeg_opts = {"format": "JPEG", "quality": 95, "optimize": 1}
		meta = PngImagePlugin.PngInfo()
		meta.add_text("Thumb::URI", str(m + "." + ft), 0)
		meta.add_text("Thumb::MTime", str(int(mtime)), 0)
		png_opts = {"format": "PNG", "pnginfo": meta}
		jpeg = map(lambda t: (t[0], t[1], jpeg_opts), jpeg_fns)
		png = map(lambda t: (t[0], t[1], png_opts), png_fns)
		z = max(map(lambda d: d[1], jpeg + png)) * 2
		if w > z or h > z:
			img.thumbnail((z, z), Image.ANTIALIAS)
		if img.mode[-1] == "A":
			# Images with transparency tend to have crap in the
			# tansparent pixel values. This is not handled well
			# when they are saved without transparency (jpeg).
			# So we put it on a white background.
			if img.mode == "LA":
				mode = "LA"
				col = 255
			else:
				mode = "RGBA"
				col = (255, 255, 255)
			bgfix = Image.new(mode, img.size, col)
			alpha = img.split()[-1]
			bgfix.paste(img, None, alpha)
			# It seems reasonable to assume that not everything
			# handles transparency properly in PNG thumbs, so
			# we want to use this as the data for them as well.
			# Just copy the alpha and call it good.
			bgfix.putalpha(alpha)
			img = bgfix
		for fn, z, opts in jpeg + png:
			if force or not os.path.exists(fn):
				t = img.copy()
				if w > z or h > z:
					t.thumbnail((z, z), Image.ANTIALIAS)
				make_pdirs(fn)
				if t.mode == "LA" and opts["format"] == "JPEG":
					# This is probably a PIL bug
					t = t.convert("L")
				t.save(fn, **opts)
