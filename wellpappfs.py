#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

import fuse
import stat
import errno
import os
from dbclient import dbclient
import re
from time import time
from hashlib import md5
from struct import pack, unpack
from zlib import crc32
from xml.sax.saxutils import escape as xmlescape

if not hasattr(fuse, "__version__"):
	raise RuntimeError("No fuse.__version__, too old?")
fuse.fuse_python_api = (0, 2)
NOTFOUND = IOError(errno.ENOENT, "Not found")
md5re = re.compile(r"^(?:\d{6}\.)?([0-9a-f]{32})\.(\w+)$")
shortmd5re = re.compile(r"^([0-9a-f]{32})$")
metamd5re = re.compile(r"^(?:\d{6}\.)?([0-9a-f]{32})\.(\w+)\.gq\.xmp$")
sre = re.compile(r"[ /]+")
orient = {0: 1, 90: 6, 180: 3, 270: 8}

class WpStat(fuse.Stat):
	def __init__(self, mode, nlink, size):
		self.st_mode = mode
		self.st_ino = 0
		self.st_dev = 0
		self.st_nlink = nlink
		self.st_uid = 0
		self.st_gid = 0
		self.st_size = size
		self.st_atime = 0
		self.st_mtime = 0
		self.st_ctime = 0

class Cache:
	def __init__(self, ttl):
		self._data = {}
		self._time = time()
		self._ttl  = ttl

	def get(self, key, getter):
		if self._time < time() - self._ttl:
			self.clean()
		if key not in self._data:
			self._data[key] = (time(), getter(key))
		return self._data[key][1]

	def clean(self):
		self._time = time()
		t = self._time - (self._ttl / 1.5)
		for key in self._data.keys():
			if self._data[key][0] < t:
				del self._data[key]

_thumbpaths = ([".thumblocal", "normal"], [".thumblocal", "large"])
_cfgpath = "/.wellpapprc"
_cloudname = ".cloud"

class Wellpapp(fuse.Fuse):
	def __init__(self, *a, **kw):
		self._cache = Cache(30)
		self._client = dbclient()
		self._cfgfile = self._cfg2file()
		fuse.Fuse.__init__(self, *a, **kw)
		self.multithreaded = False

	def _cfg2file(self):
		cfg = self._client.cfg
		data = []
		for f in filter(lambda n: n[0] != "_", cfg.keys()):
			data.append(f + "=" + cfg[f] + "\n")
		return "".join(sorted(data))

	def getattr(self, path):
		spath = path.split("/")[1:]
		mode = stat.S_IFDIR | 0555
		nlink = 2
		size = 0
		m = md5re.match(spath[-1])
		metam = metamd5re.match(spath[-1])
		if spath[-3:-1] in _thumbpaths:
			if not m or not m.group(2) != ".png": raise NOTFOUND
			search = self._path2search("/" + " ".join(spath[:-3]))
			if not search: raise NOTFOUND
			if search[2]: # order specified
				orgmd5 = self._resolve_thumb(search, spath[-1])[0]
				if not orgmd5: raise NOTFOUND
				mode = stat.S_IFREG | 0444
				tfn = self._client.thumb_path(orgmd5, spath[-2])
				size = os.stat(tfn).st_size + 7
				# size of thumb, plus six digits and a period
			else:
				mode = stat.S_IFLNK | 0444
			nlink = 1
		elif m:
			mode = stat.S_IFLNK | 0444
			nlink = 1
		elif metam:
			mode = stat.S_IFREG | 0444
			size = len(self._generate_meta(metam.group(1)))
			nlink = 1
		elif path == "/" or spath[-1] in (".thumblocal", ".metadata") or \
		     spath[-2:] in _thumbpaths:
			pass
		elif path == _cfgpath:
			mode = stat.S_IFREG | 0444
			nlink = 1
			size = len(self._cfgfile)
		elif spath[-1][:len(_cloudname)] == _cloudname:
			mode = stat.S_IFREG | 0444
			nlink = 1
			size = len(self._generate_cloud(spath[:-1], spath[-1]))
		else:
			search = self._path2search(path)
			if not search: raise NOTFOUND
			try:
				self._cache.get(search, self._search)
			except Exception:
				m = shortmd5re.match(spath[-1])
				if m:
					mode = stat.S_IFLNK | 0444
					nlink = 1
				else:
					raise NOTFOUND
		return WpStat(mode, nlink, size)

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
		want = [self._client.find_tag(n, with_prefix=True) for n in want]
		range = (0, count - 1 + len(want))
		tags = self._client.find_tags("EI", "", range=range, guids=want,
		                              excl_tags=dontwant, order="-post")
		want = [g[-27:] for g in want]
		names = [t.name.encode("utf-8") for t in tags if t.guid not in want]
		return "\n".join(names) + "\n"

	def _generate_meta(self, m):
		data = """<?xml version="1.0" encoding="UTF-8"?><x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="XMP Core 4.1.1-Exiv2"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description rdf:about="" xmlns:tiff="http://ns.adobe.com/tiff/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/" """
		post = self._client.get_post(m, wanted=["tagname", "rotate"])
		if "rotate" in post and post["rotate"] in orient:
			data += "tiff:Orientation=\"" + str(orient[post["rotate"]]) + "\""
		data += "><dc:subject><rdf:Bag>"
		data += "".join(["<rdf:li>" + xmlescape(tn).encode("utf-8") + "</rdf:li>" \
		                 for tn in sorted(post["tagname"])])
		data += "</rdf:Bag></dc:subject></rdf:Description></rdf:RDF></x:xmpmeta>"
		return data

	def _resolve_thumb(self, search, thumbname):
		idx = 0;
		thumbmd5 = thumbname[:32]
		for fn in self._cache.get(search, self._search):
			if md5(fn).hexdigest() == thumbmd5:
				m = md5re.match(fn)
				ofn = m.group(1) + "." + m.group(2)
				return md5(ofn).hexdigest(), fn

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
		raise NOTFOUND

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
				list += self._cache.get(search, self._search)
			except Exception:
				raise NOTFOUND
		else:
			raise NOTFOUND
		for e in list:
			yield fuse.Direntry(e)

	def _search(self, search):
		order = search[2]
		s = self._client.search_post(tags=search[0],
		                             excl_tags=search[1],
		                             wanted=["ext"],
		                             order=order,
		                             range=search[3])[0]
		r = []
		idx = 0
		prefix = ""
		for p in s:
			if order:
				prefix = "%06d." % (idx,)
				idx += 1
			r.append(prefix + p["md5"] + "." + p["ext"])
		return map(str, r)

	def _path2search(self, path):
		if path == "/": return None
		want = set()
		dontwant = set()
		order = []
		first = None
		range = None
		for e in filter(None, sre.split(path[1:])):
			if e[0] == "-":
				dontwant.add(e[1:])
			elif e[:2] == "O:":
				order.append(e[2:])
			elif e[:2] == "R:":
				range = tuple(map(int, e[2:].split(":")))
			else:
				want.add(e)
				if not first: first = e
		if "group" in order:
			want.remove(first)
			want = [first] + list(want)
		return tuple(want), tuple(dontwant), tuple(order), range

	def main(self, *a, **kw):
		wp = self
		class FakeFile:
			keep_cache = False
			direct_io = False
			def __init__(self, path, flags, *mode):
				rwflags = flags & (os.O_RDONLY | os.O_WRONLY | os.O_RDWR)
				if rwflags != os.O_RDONLY: raise NOTFOUND
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
				search = wp._path2search("/".join(spath[:-3]))
				if not search: raise NOTFOUND
				orgmd5, fn = wp._resolve_thumb(search, spath[-1])
				tfn = wp._client.thumb_path(orgmd5, spath[-2])
				fh = open(tfn)
				data = fh.read()
				fh.close()
				data = data.split("tEXtThumb::URI\0")
				if len(data) != 2: raise NOTFOUND
				pre, post = data
				clen, = unpack(">I", pre[-4:])
				pre = pre[:-4] + pack(">I", clen + 7)
				post = post[clen - 7:]
				tEXt = "tEXtThumb::URI\0" + fn
				crc = crc32(tEXt)
				if crc < 0: crc += 0x100000000
				tEXt += pack(">I", crc)
				data = pre + tEXt + post
				self.data = data
			def read(self, length, offset):
				return self.data[offset:offset + length]
		self.file_class = FakeFile
		return fuse.Fuse.main(self, *a, **kw)

server = Wellpapp()
server.parse(errex = 1)
server.main()
