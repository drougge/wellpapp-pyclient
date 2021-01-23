from __future__ import print_function

import fuse
import stat
import errno
import os
import sys
from wellpapp import Client, Tag, raw_exts
import re
from time import time, sleep
from hashlib import md5
from struct import pack, unpack
from zlib import crc32
from xml.sax.saxutils import escape as xmlescape
from os.path import exists
from threading import Thread, RLock, Lock
from collections import namedtuple

if not hasattr(fuse, "__version__"):
	raise RuntimeError("No fuse.__version__, too old?")
fuse.fuse_python_api = (0, 2)

if sys.version_info[0] == 2:
	PY3 = False
else:
	PY3 = True
	unicode = str
	if fuse.__version__ < "1.0.0":
		raise RuntimeError("Needs at least fuse 1.0.0 on python 3")

md5re = re.compile(r"^(?:\d{6}\.)?([0-9a-f]{32})\.(\w+)$")
shortmd5re = re.compile(r"^(?:\d{6}\.)?([0-9a-f]{32})$")
metamd5re = re.compile(r"^(?:\d{6}\.)?([0-9a-f]{32})\.(\w+)\.gq\.xmp$")
sre = re.compile(r"[ /]+")
orient = {0: 1, 90: 6, 180: 3, 270: 8}
default_range = (0, 10000)

_stat_t = namedtuple("stat_t", ["version", "size", "mtime", "dest", "jpegsize"])
_search_t = namedtuple("search_t", ["want", "dontwant", "order", "range", "clean"])

def NOTFOUND():
	raise IOError(errno.ENOENT, "Not found")

class WpStat(fuse.Stat):
	def __init__(self, mode, nlink, size, time):
		self.st_mode = mode
		self.st_ino = 0
		self.st_dev = 0
		self.st_nlink = nlink
		self.st_uid = 0
		self.st_gid = 0
		self.st_size = size
		self.st_atime = time
		self.st_mtime = time
		self.st_ctime = time

def _str_tagcmp(t):
	if t[-1] is not None:
		return u"".join(t[:-1] + (t[-1].format(),))
	else:
		return t[0]

class Cache:
	def __init__(self, ttl):
		self._data = {}
		self._time = time()
		self._ttl  = ttl
		self._lock = RLock()

	def get(self, get_key, getter):
		# The VT types in the search are hashable, but compare fuzzily, which is wrong here
		key = (
			tuple(_str_tagcmp(tc) for tc in get_key.want),
			tuple(_str_tagcmp(tc) for tc in get_key.dontwant),
			get_key.order,
			get_key.range,
			get_key.clean,
		)
		with self._lock:
			if self._time < time() - self._ttl:
				self._clean()
			if key not in self._data:
				self._data[key] = (time(), getter(get_key))
			return self._data[key][1]

	def _clean(self):
		self._time = time()
		t = self._time - (self._ttl / 1.5)
		too_old = [k for k, v in self._data.items() if v[0] < t]
		for key in too_old:
			del self._data[key]

_thumbpaths = ([".thumblocal", "normal"], [".thumblocal", "large"])
_cfgpath = "/.wellpapprc"
_cloudname = ".cloud"
_rawext = dict(zip(raw_exts, ("Jpg", "jPg", "jpG", "JPg", "JPG", "JpG", "jPG", "jpg")))
assert len(_rawext) == len(raw_exts)
_rawext_r = {v: k for k, v in _rawext.items()}

class Wellpapp(fuse.Fuse):
	def __init__(self, *a, **kw):
		fuse.Fuse.__init__(self, *a, **kw)
		self._raw2jpeg = False
		self._default_search = None
		self.parser.add_option(mountopt="raw2jpeg", action="store_true", dest="_raw2jpeg",
		                       help="Present RAW files as JPEG")
		self.parser.add_option(mountopt="default_search", dest="_default_search",
		                       help="Default search (added to all searches)")

	def _cfg2file(self):
		cfg = self._client.cfg
		data = []
		for k, v in cfg.items():
			if not k.startswith("_"):
				data.append(k + "=" + v + "\n")
		res = "".join(sorted(data))
		if PY3:
			res = res.encode("utf-8")
		return res

	def _cache_read(self):
		self._cache_fh.seek(0, 1)
		for line in self._cache_fh:
			try:
				v, m, size, mtime, dest = line.rstrip("\n").split(" ", 4)
				if v == "1":
					jz, dest = dest.split(" ", 1)
				else:
					jz = 0
					assert v == "0"
				self._stat_cache[m] = _stat_t(int(v), int(size), int(mtime), dest, int(jz))
			except Exception:
				print("Bad line in cache:", line)

	def _cache_thread(self):
		while True:
			sleep(1)
			self._cache_read()

	def _prime_stat_cache(self):
		fn = self._client.cfg.image_base + "/cache"
		if not exists(fn): return
		try:
			print("Loading stat-cache..")
			self._cache_fh = open(fn, "r", encoding="utf-8") if PY3 else open(fn, "r")
			self._stat_cache = {}
			self._cache_read()
			self._use_cache = True
		except Exception as e:
			print("Failed to load cache:", e)

	# Starting threads doesn't work from __init__.
	def fsinit(self):
		if self._use_cache:
			t = Thread(target=self._cache_thread)
			t.name = "cache loader"
			t.daemon = True
			t.start()
		print("Ready")

	def _stat(self, m):
		if m not in self._stat_cache:
			print(m, "not in cache")
			p = self._client.image_path(m)
			dest = os.readlink(p)
			st = os.stat(dest)
			self._stat_cache[m] = _stat_t(0, st.st_size, st.st_mtime, dest, 0)
		return self._stat_cache[m]

	def getattr(self, path):
		spath = path.split("/")[1:]
		mode = stat.S_IFDIR | 0o555
		nlink = 2
		size = 0
		m = md5re.match(spath[-1])
		metam = metamd5re.match(spath[-1])
		time = 0
		if spath[-3:-1] in _thumbpaths:
			if not m or not m.group(2) != ".png": NOTFOUND()
			search = self._path2search("/" + " ".join(spath[:-3]))
			if not search: NOTFOUND()
			if search.order or self._raw2jpeg: # order specified or potentially unwrapped
				orgmd5 = self._resolve_thumb(search, spath[-1])
				if not orgmd5: NOTFOUND()
				mode = stat.S_IFREG | 0o444
				tfn = self._client.thumb_path(orgmd5[0], spath[-2])
				size = os.stat(tfn).st_size
				if search.order:
					# plus six digits and a period
					size += 7
			else:
				mode = stat.S_IFLNK | 0o444
			nlink = 1
		elif m:
			if self._use_cache:
				mode = stat.S_IFREG | 0o444
				version, size, time, dest, jpeg = self._stat(m.group(1))
				if self._raw2jpeg and spath[-1][-3:] in _rawext_r: # wrapped RAW
					size = jpeg
			else:
				mode = stat.S_IFLNK | 0o444
			nlink = 1
		elif metam:
			mode = stat.S_IFREG | 0o444
			size = len(self._generate_meta(metam.group(1)))
			nlink = 1
		elif path == "/" or spath[-1] in (".thumblocal", ".metadata") or \
		     spath[-2:] in _thumbpaths:
			pass
		elif path == _cfgpath:
			mode = stat.S_IFREG | 0o444
			nlink = 1
			size = len(self._cfgfile)
		elif spath[-1][:len(_cloudname)] == _cloudname:
			mode = stat.S_IFREG | 0o444
			nlink = 1
			size = len(self._generate_cloud(spath[:-1], spath[-1]))
		else:
			search = self._path2search(path)
			if not search: NOTFOUND()
			try:
				self._cache.get(search, self._search)
			except Exception:
				m = shortmd5re.match(spath[-1])
				if m:
					mode = stat.S_IFLNK | 0o444
					nlink = 1
				else:
					NOTFOUND()
		return WpStat(mode, nlink, size, time)

	def _generate_cloud(self, spath, fn):
		fn = fn[len(_cloudname):]
		count = 20
		if fn and fn[0] == ":":
			try:
				count = int(fn[1:])
			except ValueError:
				pass
			if count < 1: count = 1
		want, dontwant = self._path2search("/" + "/".join(spath))[:2]
		with self._client_lock:
			range = (0, count - 1 + len(want))
			tags = self._client.find_tags("EI", "", range=range, guids=want,
			                              excl_guids=dontwant, order="-post",
			                              flags="-datatag")
		want = [w[0][-27:] for w in want]
		names = [t.name for t in tags if t.guid not in want]
		res = "\n".join(names) + "\n"
		return res.encode("utf-8")

	def _generate_meta(self, m):
		data = u"""<?xml version="1.0" encoding="UTF-8"?><x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="XMP Core 4.1.1-Exiv2"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description rdf:about="" xmlns:tiff="http://ns.adobe.com/tiff/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/" """
		with self._client_lock:
			post = self._client.get_post(m, wanted=["tagname", "tagdata", "rotate"])
		if "rotate" in post and post.rotate.value in orient:
			data += u"tiff:Orientation=\"" + unicode(orient[post.rotate.value]) + u"\""
		data += u"><dc:subject><rdf:Bag>"
		tags = [tag.pname + ((u"=" + unicode(tag.value)) if tag.value else u"") for tag in post.tags]
		data += u"".join([u"<rdf:li>" + xmlescape(tn) + u"</rdf:li>" \
		                 for tn in sorted(tags)])
		data += u"</rdf:Bag></dc:subject></rdf:Description></rdf:RDF></x:xmpmeta>"
		return data.encode("utf-8")

	def _resolve_thumb(self, search, thumbname):
		thumbmd5 = thumbname[:32]
		fns, pcache = self._cache.get(search, self._search)
		if not pcache:
			for fn in fns:
				m = md5re.match(fn)
				ext = m.group(2)
				ofn = m.group(1) + "." + _rawext_r.get(ext, ext)
				tmd5 = md5(fn.encode("utf-8")).hexdigest()
				pcache[tmd5] = (md5(ofn.encode("utf-8")).hexdigest(), fn)
		return pcache.get(thumbmd5)

	def readlink(self, path):
		path = path.split("/")[1:]
		m = md5re.match(path[-1])
		if m:
			if path[-3:-1] in _thumbpaths:
				return self._client.thumb_path(m.group(1), path[-2])
			else:
				return self._client.image_path(m.group(1))
		if path[-3:-1] not in _thumbpaths:
			m = shortmd5re.match(path[-1])
			if m: return self._client.image_path(m.group(1))
		NOTFOUND()

	def readdir(self, path, offset):
		list = [".", ".."]
		search = self._path2search(path)
		path = path.split("/")[1:]
		if path[-1] == ".thumblocal":
			list += ["normal", "large"]
		elif path == [""] or path[-2:] in _thumbpaths:
			pass
		elif search:
			try:
				list += self._cache.get(search, self._search)[0]
			except Exception:
				NOTFOUND()
		else:
			NOTFOUND()
		for e in list:
			yield fuse.Direntry(e)

	def _search(self, search):
		order = search.order
		range = search.range
		if not range: range = default_range
		assert None not in search.want
		assert None not in search.dontwant
		with self._client_lock:
			s = self._client.search_post(guids=search.want,
			                             excl_guids=search.dontwant,
			                             wanted=["ext"],
			                             order=order,
			                             range=range)
		r = []
		idx = 0
		prefix = ""
		for p in s:
			if order:
				prefix = "%06d." % (idx,)
				idx += 1
			if search.clean:
				r.append(prefix + p.md5)
			else:
				m = p.md5
				ext = p.ext
				if self._raw2jpeg and ext in _rawext and self._stat(m).jpegsize:
					r.append(prefix + m + "." + _rawext[ext])
				r.append(prefix + m + "." + ext)
		if not PY3:
			r = map(str, r)
		return r, {}

	def _path2search(self, path):
		if path == "/": return None
		want = set()
		dontwant = set()
		order = []
		first = None
		range = None
		clean = False
		nodefault = False
		for e in filter(None, sre.split(path[1:])):
			if e[0] == "-":
				with self._client_lock:
					e = self._client.parse_tag(e[1:], True)
				dontwant.add(e)
			elif e[:2] == "O:":
				o = e[2:]
				if o != "group":
					t = Tag()
					with self._client_lock:
						o = self._client.find_tag(o, t, True)
					assert t.valuetype
				order.append(o)
			elif e[:2] == "R:":
				range = tuple(map(int, e[2:].split(":")))
			elif e == "C:":
				clean = True
			elif e == "N:":
				nodefault = True
			else:
				with self._client_lock:
					e = self._client.parse_tag(e, True)
				want.add(e)
				if not first: first = e
		if self._default_search and not nodefault:
			def bare(tg):
				if tg[0] in "~!":
					return tg[1:]
				return tg
			allguids = {bare(t[0]) for t in want | dontwant if t}
			for n in ("want", "dontwant"):
				for t in getattr(self._default_search, n):
					if bare(t[0]) not in allguids:
						locals()[n].add(t)
		if "group" in order:
			want.remove(first)
			want = [first] + list(want)
		return _search_t(tuple(want), tuple(dontwant), tuple(order), range, clean)

	def main(self, *a, **kw):
		self._cache = Cache(30)
		self._client = Client()
		self._client_lock = RLock()
		self._cfgfile = self._cfg2file()
		self._use_cache = False
		self._prime_stat_cache()
		if self._raw2jpeg and not self._use_cache:
			raise Exception("raw2jpeg only works with a stat-cache")
		if self._raw2jpeg:
			from wellpapp import RawWrapper
		if self._default_search:
			ds = "/" + self._default_search
			self._default_search = None
			self._default_search = self._path2search(ds)
			if None in self._default_search.want or None in self._default_search.dontwant:
				raise Exception("Default search broken (%r)" % (self._default_search,))
		wp = self
		class FakeFile:
			keep_cache = False
			direct_io = False
			_fh = None
			data = ""
			def __init__(self, path, flags, *mode):
				rwflags = flags & (os.O_RDONLY | os.O_WRONLY | os.O_RDWR)
				if rwflags != os.O_RDONLY: NOTFOUND()
				if path == _cfgpath:
					self.data = wp._cfgfile
					return
				spath = path.split("/")
				metam = metamd5re.match(spath[-1])
				if metam:
					self.data = wp._generate_meta(metam.group(1))
					return
				if spath[-1][:len(_cloudname)] == _cloudname:
					self.data = wp._generate_cloud(spath[1:-1], spath[-1])
					return
				if spath[-3:-1] in _thumbpaths:
					self.data = self._make_thumb(spath)
				else:
					fn = spath[-1].split(".")
					m = fn[-2][-32:]
					fh = self._open(m)
					if fh:
						if wp._raw2jpeg and fn[-1] in _rawext_r:
							# @@ Check wp._stat(m).version
							self._fh = RawWrapper(fh, True)
						else:
							self._fh = fh
					self._lock = Lock()
			def _open(self, m):
				try:
					dest = wp._stat(m).dest
					return open(dest, "rb")
				except Exception:
					pass
				try:
					p = wp._client.image_path(m)
					dest = os.readlink(p)
					fh = open(dest, "rb")
					wp._stat_cache[m] = wp._stat(m)._replace(dest=dest)
					return fh
				except Exception:
					pass
			# FUSE doesn't seem to like destroying these objects.
			# But it does call release, so I'll do what I can.
			def __del__(self):
				self.release(0)
			def release(self, flags):
				if self._fh: self._fh.close()
				self.data = self._fh = self._Lock = None
			def _make_thumb(self, spath):
				search = wp._path2search("/".join(spath[:-3]))
				if not search: NOTFOUND()
				orgmd5, fn = wp._resolve_thumb(search, spath[-1])
				ext = fn.split(".")[-1]
				tfn = wp._client.thumb_path(orgmd5, spath[-2])
				fh = open(tfn, "rb")
				data = fh.read()
				fh.close()
				if not (search.order or ext in _rawext_r):
					return data
				data = data.split(b"tEXtThumb::URI\0")
				if len(data) != 2: NOTFOUND()
				pre, post = data
				clen, = unpack(">I", pre[-4:])
				if search.order: # It's longer only of search was ordered
					pre = pre[:-4] + pack(">I", clen + 7)
				post = post[clen - 7:]
				tEXt = b"tEXtThumb::URI\0" + fn.encode("utf-8")
				crc = crc32(tEXt)
				if crc < 0: crc += 0x100000000
				tEXt += pack(">I", crc)
				return pre + tEXt + post
			def read(self, length, offset):
				if self._fh:
					with self._lock:
						self._fh.seek(offset)
						return self._fh.read(length)
				else:
					return self.data[offset:offset + length]
		self.file_class = FakeFile
		return fuse.Fuse.main(self, *a, **kw)

def main(arg0, argv):
	server = Wellpapp(prog=arg0)
	server.parse(argv, errex=1, values=server)
	server.main()
