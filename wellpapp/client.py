import socket
import os
import hashlib
import re
from functools import partial
from collections import namedtuple
import sys

from wellpapp.vt import VTdatetime, VTuint, VTint, VTnull, valuetypes
from wellpapp._util import _uniw, _uni
from wellpapp.util import DotDict, CommentWrapper, make_pdirs, RawWrapper

__all__ = ("Client", "Config", "Post", "Tag", "WellpappError", "ResponseError",
           "DuplicateError", "InheritValue", "ImplicationTuple", "vtparse",
          )

if sys.version_info[0] > 2:
	basestring = (bytes, str)
	def itervalues(d):
		return iter(d.values())
else:
	def itervalues(d):
		return d.itervalues()

class WellpappError(Exception): pass
class ResponseError(WellpappError): pass
class DuplicateError(WellpappError): pass

class InheritValue:
	def __str__(self):
		return "<InheritValue>"
InheritValue = InheritValue()

ImplicationTuple = namedtuple("ImplicationTuple", "guid prio filter value")

def _rfindany(s, chars, pos=-1):
	if pos < 0: pos = len(s)
	for i in range(pos - 1, -1, -1):
		if s[i] in chars: return i
	return -1

def _tagspec(type, value):
	if value[0] in u"~!":
		type = value[0] + type
		value = value[1:]
	return type + value

class Post(DotDict): pass

class Tag(DotDict):
	def _populate(self, res, flags=""):
		res = res.split()
		alias = []
		flaglist = []
		hexint = partial(int, base=16)
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
			self.value = vtparse(*vt)
		if u"~" in flags:
			if self.name: self.pname = u"~" + self.name
			if self.guid: self.pguid = "~" + self.guid
		else:
			if self.name: self.pname = self.name
			if self.guid: self.pguid = self.guid

_nonetag = Tag()

class TagDict(dict):
	"""Dictionary-like object that holds the tag lists in Posts.
	Members are keyed on both .name and .guid (if they exist).
	A .guid always shadows a .name.
	Iterates over Tag objects, not names and/or guids.
	Use .names or .guids if you want dicts with just those keys.
	(Those are normal dicts, iterating over keys.)
	"""

	def __init__(self):
		self.names = {}
		self.guids = {}

	def _add(self, tag, name, guid):
		if name:
			if name not in self:
				dict.__setitem__(self, name, tag)
			self.names[name] = tag
		if guid:
			dict.__setitem__(self, guid, tag)
			self.guids[guid] = tag

	def __len__(self):
		return max(len(self.names), len(self.guids))

	def __iter__(self):
		if self.guids: return itervalues(self.guids)
		return itervalues(self.names)

	itervalues = __iter__

	def values(self):
		if self.guids: return self.guids.values()
		return self.names.values()

	def __setitem__(self, key, value):
		raise AttributeError("TagDicts are immutable-ish")

	def __delitem__(self, key):
		raise AttributeError("TagDicts are immutable-ish")

	def get(self, key, default=_nonetag):
		"""Just like get on dict, except the default is an empty Tag.
		This is still False as a bool, but you can do things like
		post.tags.get("foo").value which gives None if foo isn't set.
		"""
		return dict.get(self, key, default)

def vtparse(vtype, val, human=False):
	try:
		return valuetypes[vtype](val, human)
	except ValueError:
		if human and val == "":
			return VTnull()
		raise

_field_sparser = {
	"created"        : VTdatetime,
	"imgdate"        : VTdatetime,
	"width"          : VTuint,
	"height"         : VTuint,
	"rotate"         : VTint,
}

_p_int = lambda i: str(int(i))
_p_hexint = lambda i: "%x" % (int(i),)
def _p_date(val):
	if isinstance(val, basestring): return _uniw(val)
	return val.format()
_field_cparser = {
	"width"          : _p_hexint,
	"height"         : _p_hexint,
	"rotate"         : _p_int,
	"created"        : _p_date,
	"imgdate"        : _p_date,
	"ext"            : _uniw,
	"MD5"            : _uniw,
}

class Config(DotDict):
	def __init__(self, local_rc=False, **kw):
		DotDict.__init__(self, tagwindow_width=840, tagwindow_height=600, **kw)
		rcs = []
		rc_name = ".wellpapprc"
		path = "/"
		if local_rc:
			rcs = [rc_name]
		else:
			rcs = [os.path.join(os.environ["HOME"], rc_name)]
			for dir in os.getcwd().split(os.path.sep):
				path = os.path.join(path, dir)
				rc = os.path.join(path, rc_name)
				if os.path.exists(rc): rcs.append(rc)
		for rc in rcs:
			self._load(rc)

	def _load(self, fn):
		with CommentWrapper(open(fn)) as fh:
			for line in fh:
				line = line.strip()
				a = line.split("=", 1)
				assert(len(a) == 2)
				self[a[0]] = a[1]

class Client:
	_prot_max_len = 4096

	def __init__(self, cfg=None):
		if not cfg:
			cfg = Config()
		self.cfg = cfg
		if cfg.socket:
			self.server = cfg.socket
		else:
			self.server = (cfg.server, int(cfg.port))
		self.is_connected = False
		self._md5re = re.compile(r"^[0-9a-f]{32}$", re.I)
		base = cfg.image_base
		while base.endswith("/"): base = base[:-1]
		base = re.escape(base)
		self._destmd5re = re.compile(r"^" + base + r"/[0-9a-f]/[0-9a-f]{2}/([0-9a-f]{32})$")

	def _reconnect(self):
		if self.is_connected: return
		if isinstance(self.server, tuple):
			self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		else:
			self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
		self._sock.connect(self.server)
		self._fh = self._sock.makefile('rb')
		self.is_connected = True

	def _writeline(self, line, retry=True):
		assert u"\n" not in line
		self._reconnect()
		line = line.encode("utf-8") + b"\n"
		try:
			self._sock.sendall(line)
		except IOError:
			self.is_connected = False
			if retry:
				self._reconnect()
				self._sock.sendall(line)

	def _readline(self):
		return self._fh.readline()[:-1].decode("utf-8")

	def _parse_search(self, line, posts, wanted, props):
		if line == u"OK": return True
		if line[0] != u"R": raise ResponseError(line)
		if line[1] == u"E": raise ResponseError(line)
		if line[1] == u"R":
			if props != None: props["result_count"] = int(line[2:], 16)
			return
		f = Post()
		seen = set()
		pieces = line[1:].split(u" :")
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
				raise ResponseError(line)
		f.fulltags = TagDict()
		f.weaktags = TagDict()
		f.implfulltags = TagDict()
		f.implweaktags = TagDict()
		f.datatags = TagDict()
		for piece in pieces[1:-1]:
			flags, data = piece.split(u" ", 1)
			if u"I" in flags and u"~" in flags:
				ta = f.implweaktags
			elif u"I" in flags:
				ta = f.implfulltags
			elif u"~" in flags:
				ta = f.weaktags
			elif u"D" in flags:
				ta = f.datatags
			else:
				ta = f.fulltags
			t = Tag()
			t._populate(data, flags)
			ta._add(t, t.name, t.guid)
		if not f.md5: raise ResponseError(line)
		if f.md5 in seen: raise DuplicateError(f.md5)
		seen.add(f.md5)
		tagdicts = [f.fulltags, f.weaktags]
		if wanted and "implied" in wanted:
			settags = TagDict()
			for td in tagdicts:
				for tag in td:
					settags._add(tag, tag.pname, tag.pguid)
			idicts = [f.implfulltags, f.implweaktags]
			tagdicts += idicts
			impltags = TagDict()
			for td in idicts:
				for tag in td:
					impltags._add(tag, tag.pname, tag.pguid)
			f.settags = settags
			f.impltags = impltags
		else:
			del f.implfulltags
			del f.implweaktags
		if not wanted or "datatags" not in wanted:
			del f.datatags
		else:
			tagdicts.append(f.datatags)
		alltags = TagDict()
		for td in tagdicts:
			for tag in td:
				alltags._add(tag, tag.pname, tag.pguid)
		f.tags = alltags
		posts.append(f)

	def _search_post(self, search, wanted=None, props=None):
		self._writeline(search)
		posts = []
		while not self._parse_search(self._readline(), posts, wanted, props): pass
		return posts

	def get_post(self, md5, separate_implied=False, wanted=None):
		if wanted is None:
			wanted = ["tagname", "tagguid", "tagdata", "datatags", "ext", "created", "width", "height"]
		if separate_implied and "implied" not in wanted:
			wanted = ["implied"] + wanted
		search = u"SPM" + _uniw(md5) + " F".join([""] + self._filter_wanted(wanted))
		posts = self._search_post(search, wanted)
		if not posts: return None
		assert posts[0].md5 == md5
		return posts[0]

	def delete_post(self, md5):
		assert " " not in md5
		cmd = u"DP" + _uniw(md5)
		self._writeline(cmd)
		res = self._readline()
		if res != u"OK": raise ResponseError(res)

	def _list(self, data, converter=_uniw):
		if not data: return []
		if isinstance(data, basestring): return [converter(data)]
		return list(map(converter, data))

	def _guids2posneg(self, guids):
		pos, neg = [], []
		for g in guids:
			if g[0] == u"!":
				pos.append(g)
			elif g[0] == u"-":
				neg.append(g[1:])
			else:
				pos.append(g)
		return pos, neg

	def _filter_wanted(self, wanted):
		return [w for w in self._list(wanted, str) if w != "datatags"]

	def _build_search(self, guids=None, excl_guids=None, wanted=None, order=None, range=None):
		guids = self._list(guids, self._tag2spec)
		excl_guids = self._list(excl_guids, self._tag2spec)
		pos1, neg1 = self._guids2posneg(guids)
		neg2, pos2 = self._guids2posneg(excl_guids)
		search = []
		for want in self._filter_wanted(wanted):
			search += [u"F", want, u" "]
		for guid in pos1 + pos2:
			search += [u"T", _tagspec(u"G", guid), u" "]
		for guid in neg1 + neg2:
			search += [u"t", _tagspec(u"G", guid), u" "]
		for o in self._list(order, str):
			search += [u"O", o, u" "]
		if range != None:
			search += [u"R%x:%x" % tuple(range)]
		return u"".join(search)

	def search_post(self, wanted=None, props=None, **kw):
		search = u"SP" + self._build_search(wanted=wanted, **kw)
		posts = self._search_post(search, wanted, props)
		return posts

	def _fieldspec(self, **kwargs):
		f = [_uniw(f) + u"=" + _field_cparser[f](kwargs[f]) for f in kwargs]
		if not f: return u""
		return u" ".join([u""] + f)

	def modify_post(self, md5, **kwargs):
		fspec = self._fieldspec(**kwargs)
		if fspec:
			cmd = u"MP" + _uniw(md5) + fspec
			self._writeline(cmd)
			res = self._readline()
			if res != u"OK": raise ResponseError(res)

	def add_post(self, md5, **kwargs):
		cmd  = u"AP" + _uniw(md5)
		assert "width" in kwargs
		assert "height" in kwargs
		assert "ext" in kwargs
		cmd += self._fieldspec(**kwargs)
		self._writeline(cmd)
		res = self._readline()
		if res != u"OK": raise ResponseError(res)

	def _rels(self, c, md5, rels):
		cmd = [u"R", c, md5]
		for rel in self._list(rels, _uniw):
			cmd.append(u" " + rel)
		self._writeline(u"".join(cmd))
		res = self._readline()
		if res != u"OK": raise ResponseError(res)

	def add_rels(self, md5, rels):
		self._rels(u"R", md5, rels)

	def remove_rels(self, md5, rels):
		self._rels(u"r", md5, rels)

	def _parse_rels(self, line, rels):
		if line == u"OK": return True
		if line[0] != u"R": raise ResponseError(line)
		if line[1] == u"E": raise ResponseError(line)
		a = str(line[1:]).split()
		p = a[0]
		l = rels.setdefault(p, [])
		l += a[1:]

	def post_rels(self, md5):
		cmd = u"RS" + _uniw(md5)
		self._writeline(cmd)
		rels = {}
		while not self._parse_rels(self._readline(), rels): pass
		if not md5 in rels: return None
		return rels[md5]

	def add_tag(self, name, type=None, guid=None, valuetype=None):
		cmd = u"ATN" + _uniw(name)
		if type:
			cmd += u" T" + _uniw(type)
		if guid:
			cmd += u" G" + _uniw(guid)
		if valuetype:
			cmd += u" V" + _uniw(valuetype)
		self._writeline(cmd)
		res = self._readline()
		if res != u"OK": raise ResponseError(res)

	def add_alias(self, name, origin_guid):
		cmd = u"AAG" + _uniw(origin_guid) + u" N" + _uniw(name)
		self._writeline(cmd)
		res = self._readline()
		if res != u"OK": raise ResponseError(res)

	def remove_alias(self, name):
		cmd = u"DAN" + _uniw(name)
		self._writeline(cmd)
		res = self._readline()
		if res != u"OK": raise ResponseError(res)

	def _addrem_implies(self, addrem, set_tag, implied_tag, datastr, filter, value=None):
		set_tag = self._tag2spec(set_tag)
		implied_tag = self._tag2spec(implied_tag)
		assert u" " not in set_tag
		assert u" " not in implied_tag
		if implied_tag[0] == u"-":
			add = u" i" + implied_tag[1:]
		else:
			add = u" I" + implied_tag
		if filter:
			assert isinstance(filter, tuple) and len(filter) == 2
			filter = _uniw(filter[0]) + filter[1].format()
			assert u" " not in filter
			set_tag += filter
		if value:
			datastr += " V" + value.format()
		cmd = u"I" + addrem + set_tag + add + datastr
		self._writeline(cmd)
		res = self._readline()
		if res != u"OK": raise ResponseError(res)

	def add_implies(self, set_tag, implied_tag, priority=0, filter=None, value=None):
		datastr = u""
		if priority:
			datastr += u" P%d" % (priority,)
		self._addrem_implies("I", set_tag, implied_tag, datastr, filter, value)

	def remove_implies(self, set_tag, implied_tag, filter=None):
		self._addrem_implies("i", set_tag, implied_tag, "", filter)

	def _parse_implies(self, data):
		res = self._readline()
		if res == u"OK": return
		guid, impl = res.split(u" ", 1)
		assert guid[:2] == u"RI"
		guid = guid[2:]
		if len(guid) == 27:
			filter = None
		else:
			pt = self._parse_tag("", guid, 27, True, True)
			filter = pt[1:]
			if filter == (None, None): filter = None
			guid = pt[0]
		l = data.setdefault(guid, [])
		guid = None
		prio = 0
		value = None
		for part in impl.split():
			if part[0] in u"Ii":
				if guid:
					l.append(ImplicationTuple(guid, prio, filter, value))
				prio = 0
				value = None
				guid = str(part[1:])
				if part[0] == u"i":
					guid = "-" + guid
			elif part[0] == u"P":
				assert guid
				prio = int(part[1:])
			elif part[0] == u"V":
				assert guid
				value = part[1:]
				if value:
					valuetype, value = value.split("=", 1)
					value = vtparse(valuetype, value)
				else:
					value = InheritValue
			else:
				raise ResponseError(res)
		l.append(ImplicationTuple(guid, prio, filter, value))
		return True

	def tag_implies(self, tag, reverse=False):
		tag = _uniw(tag)
		cmd = u"IR" if reverse else u"IS"
		self._writeline(cmd + tag)
		data = {}
		while self._parse_implies(data):
			pass
		if reverse:
			rev = []
			for itag in data:
				for impl in data[itag]:
					assert len(impl) >= 2
					ttag = impl[0]
					if ttag[0] == "-":
						assert ttag[1:] == tag
						rev.append(impl._replace(guid="-" + itag))
					else:
						assert ttag == tag
						rev.append(impl._replace(guid=itag))
			return rev
		if tag in data:
			return data[tag]
		return []

	def merge_tags(self, into_t, from_t):
		cmd = u"MTG" + _uniw(into_t) + u" M" + _uniw(from_t)
		self._writeline(cmd)
		res = self._readline()
		if res != u"OK": raise ResponseError(res)

	def mod_tag(self, guid, name=None, type=None, valuetype=None):
		cmd = u"MTG" + _uniw(guid)
		for init, field in ((u" N", name), (u" T", type), (u" V", valuetype)):
			if field:
				cmd += init + _uniw(field)
		self._writeline(cmd)
		res = self._readline()
		if res != u"OK": raise ResponseError(res)

	def _tag2spec(self, t, value_allowed=True):
		if type(t) in (tuple, list):
			assert len(t) in (2, 3)
			g = _uniw(t[0])
			if t[-1] is None: return g
			assert value_allowed
			if len(t) == 2:
				return g + u"=" + t[1].format()
			else:
				return g + t[1] + t[2].format()
		else:
			return _uniw(t)

	def tag_post(self, md5, full_tags=None, weak_tags=None, remove_tags=None):
		tags = self._list(full_tags, lambda s: u" T" + self._tag2spec(s))
		tags += self._list(weak_tags, lambda s: u" T~" + self._tag2spec(s))
		tags += self._list(remove_tags, lambda s: u" t" + self._tag2spec(s, False))
		init = u"TP" + _uniw(md5)
		cmd = [init]
		clen = len(init)
		for tag in tags:
			assert u" " not in tag[1:]
			clen += len(tag.encode("utf-8"))
			if clen >= self._prot_max_len:
				self._writeline(u"".join(cmd))
				res = self._readline()
				if res != u"OK": raise ResponseError(res)
				cmd = [init]
				clen = len(init) + len(tag.encode("utf-8"))
			cmd.append(tag)
		if len(cmd) > 1:
			self._writeline(u"".join(cmd))
			res = self._readline()
			if res != u"OK": raise ResponseError(res)

	def _parse_tagres(self, resdata = None):
		res = self._readline()
		if res == u"OK": return
		if res[0] != u"R": raise ResponseError(res)
		if res[1] == u"E": raise ResponseError(res)
		if res[1] == u"R": return True # ignore count for now
		t = Tag()
		t._populate(res[1:])
		if resdata != None: resdata.append(t)
		return t

	def find_tags(self, matchtype, name, range=None, order=None, flags=None, **kw):
		if kw:
			filter = self._build_search(**kw)
			if filter:
				filter = u" :" + filter
		else:
			filter = u""
		matchtype = _uniw(matchtype)
		name = _uniw(name)
		cmd = [u"ST", matchtype, name]
		for o in self._list(order, _uniw):
			cmd.append(u" O" + o)
		for f in self._list(flags, _uniw):
			cmd.append(u" F" + f)
		if range is not None:
			assert len(range) == 2
			cmd.append(u" R%x:%x" % tuple(range))
		cmd.append(filter)
		self._writeline(u"".join(cmd))
		tags = []
		while self._parse_tagres(tags): pass
		return tags

	def _parse_tag(self, prefix, spec, pos, comparison, is_guid=False):
		if pos == -1:
			return None
		if is_guid:
			assert comparison
			ppos = -1
			tag = Tag()
			tag.guid = spec[:pos]
		else:
			tag = self.find_tag(spec[:pos])
			if comparison:
				ppos = _rfindany(spec, u"=<>", pos)
			else:
				ppos = spec.rfind(u"=", 0, pos)
			if not tag:
				return self._parse_tag(prefix, spec, ppos, comparison)
			tag = self.get_tag(tag)
			if not tag or tag.valuetype in (None, "none"):
				return self._parse_tag(prefix, spec, ppos, comparison)
		if comparison:
			if pos + 1 < len(spec) and spec[pos + 1] in u"=~":
				comp = spec[pos:pos + 2]
				val = spec[pos + 2:]
			else:
				comp = spec[pos]
				val = spec[pos + 1:]
			if is_guid:
				tag.valuetype, val = val.split("=", 1)
			if comp not in (u"=", u"<", u">", u"<=", u">=", u"=~"):
				return None
			val = vtparse(tag.valuetype, val, True)
			if comp != u"=" and isinstance(val, VTnull):
				return None
			return (prefix + tag.guid, comp, val)
		else:
			val = spec[pos + 1:]
			if val:
				val = vtparse(tag.valuetype, val, True)
			else:
				val = None
			return (prefix + tag.guid, val)

	def parse_tag(self, spec, comparison=False):
		spec = _uni(spec)
		if not spec: return None
		if spec[0] in u"~-!":
			prefix = spec[0]
			spec = spec[1:]
		else:
			prefix = u""
		if u" " not in spec and u"\n" not in spec:
			tag = self.find_tag(spec)
		else:
			tag = None
		if tag:
			if comparison:
				return (prefix + tag, None, None)
			else:
				return (prefix + tag, None)
		if comparison:
			ppos = _rfindany(spec, u"=<>", spec.find(u" "))
		else:
			ppos = spec.rfind(u"=", 0, spec.find(u" "))
		return self._parse_tag(prefix, spec, ppos, comparison)

	def _find_tag(self, matchtype, name, with_prefix):
		name = _uniw(name)
		if with_prefix and name[0] in u"~-!":
			prefix = name[0]
			name = name[1:]
		else:
			prefix = u""
		tags = self.find_tags(matchtype, name)
		if not tags: return None
		assert len(tags) == 1
		tag = tags[0]
		tag.pname = prefix + tag.name
		tag.pguid = prefix + tag.guid
		return tag

	def find_tag(self, name, resdata=None, with_prefix=False):
		tag = self._find_tag(u"EAN", name, with_prefix)
		if not tag: return None
		if resdata != None: resdata.update(tag)
		return tag.pguid

	def get_tag(self, guid, with_prefix=False):
		tag = self._find_tag(u"EAG", guid, with_prefix)
		if not tag: return None
		assert guid[-27:] == tag.guid
		return tag

	def begin_transaction(self):
		self._writeline(u"tB")
		res = self._readline()
		return res == u"OK"

	def end_transaction(self):
		self._writeline(u"tE")
		res = self._readline()
		return res == u"OK"

	def thumb_path(self, md5, size):
		md5 = str(md5)
		return os.path.join(self.cfg.thumb_base, str(size), md5[0], md5[1:3], md5)

	def pngthumb_path(self, md5, ft, size):
		fn = _uniw(md5) + u"." + _uniw(ft)
		md5 = hashlib.md5(fn.encode("utf-8")).hexdigest()
		return os.path.join(self.cfg.thumb_base, str(size), md5[0], md5[1:3], md5)

	def image_dir(self, md5):
		md5 = str(md5)
		return os.path.join(self.cfg.image_base, md5[0], md5[1:3])

	def image_path(self, md5):
		md5 = str(md5)
		return os.path.join(self.image_dir(md5), md5)

	def postspec2md5(self, spec, default=None):
		if os.path.lexists(spec) and not os.path.isdir(spec):
			# some extra magic to avoid reading the files if possible
			if os.path.islink(spec):
				dest = os.readlink(spec)
				m = self._destmd5re.match(dest)
				if m: return m.group(1)
			# Even when the fuse fs returns files, bare IDs are links
			aspec = spec.split("/")
			afn = aspec[-1].split(".")[-2:]
			if self._md5re.match(afn[0]):
				aspec[-1] = afn[0]
				shortspec = "/".join(aspec)
				if os.path.islink(shortspec):
					dest = os.readlink(shortspec)
					m = self._destmd5re.match(dest)
					if m: return m.group(1)
			# Oh well, hash the file.
			return hashlib.md5(open(spec, "rb").read()).hexdigest()
		if self._md5re.match(spec): return spec
		return default

	def order(self, tag, posts):
		init = u"OG" + _uniw(tag)
		cmd = [init]
		dolen = 2
		clen = len(init)
		for post in map(_uniw, posts):
			post = u" P" + post
			cmd.append(post)
			clen += len(post.encode("utf-8"))
			if clen >= self._prot_max_len - 35:
				self._writeline(u"".join(cmd))
				res = self._readline()
				if res != u"OK": raise ResponseError(res)
				# Overlap one, so previous ordering doesn't mess us up.
				cmd = [init, post]
				dolen = 3
				clen = len(init) + len(post.encode("utf-8"))
		if len(cmd) >= dolen:
			self._writeline(u"".join(cmd))
			res = self._readline()
			if res != u"OK": raise ResponseError(res)

	def metalist(self, name):
		cmd = u"L" + _uniw(name)
		self._writeline(cmd)
		res = self._readline()
		names = []
		while res != u"OK":
			if res[:2] != u"RN": raise ResponseError(res)
			names.append(res[2:])
			res = self._readline()
		return names

	def thumb_fns(self, m, ft):
		sizes = self.cfg.thumb_sizes.split()
		jpeg_fns = map(lambda z: (self.thumb_path(m, int(z)), int(z)), sizes)
		png_fns = map(lambda n, z: (self.pngthumb_path(m, ft, n), z),
		              ("normal", "large"), (128, 256))
		return list(jpeg_fns), list(png_fns)

	def save_thumbs(self, m, img, ft, rot, force=False):
		from PIL import Image, PngImagePlugin
		fn = self.image_path(m)
		mtime = os.stat(fn).st_mtime
		if not img:
			img = Image.open(RawWrapper(open(fn, "rb")))
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
		jpeg = list(map(lambda t: (t[0], t[1], jpeg_opts), jpeg_fns))
		png = list(map(lambda t: (t[0], t[1], png_opts), png_fns))
		z = max(map(lambda d: d[1], jpeg + png)) * 2
		if w > z or h > z:
			img = _thumb(img, z)
		for fn, z, opts in jpeg + png:
			if force or not os.path.exists(fn):
				t = _thumb(img.copy(), z)
				make_pdirs(fn)
				if opts["format"] == "JPEG":
					# Some versions of PIL care, some don't.
					if t.mode == "RGBA":
						t = t.convert("RGB")
					if t.mode == "LA":
						t = t.convert("L")
				t.save(fn, **opts)

def _thumb(img, z):
	from PIL import Image
	if max(img.size) > z:
		img.thumbnail((z, z), Image.ANTIALIAS)
	if img.mode[-1] == "A":
		# Images with transparency tend to have crap in the
		# tansparent pixel values. In some versions of PIL
		# this reappears after scaling.
		# So we put it on a white background every time.
		if img.mode == "LA":
			mode = "LA"
			col = 255
		else:
			mode = "RGBA"
			col = (255, 255, 255)
		bgfix = Image.new(mode, img.size, col)
		alpha = img.split()[-1]
		bgfix.paste(img, None, alpha)
		bgfix.putalpha(alpha)
		return bgfix
	else:
		return img
