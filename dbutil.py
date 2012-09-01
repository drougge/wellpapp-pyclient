# -*- coding: iso-8859-1 -*-

class TIFF:
	"""Pretty minimal TIFF container parser"""
	
	types = {1: (1, "B"),  # BYTE
		 2: (1, None), # ASCII
		 3: (2, "H"),  # SHORT
		 4: (4, "I"),  # LONG
		 5: (8, "II"), # RATIONAL
		 # No TIFF6 fields, sorry
		}
	
	def __init__(self, fh, short_header=False):
		from struct import unpack
		self._fh = fh
		d = fh.read(4)
		if short_header:
			if d[:2] not in ("II", "MM"): raise Exception("Not TIFF")
		else:
			if d not in ("II*\0", "MM\0*"): raise Exception("Not TIFF")
		endian = {"M": ">", "I": "<"}[d[0]]
		self._up = lambda fmt, *a: unpack(endian + fmt, *a)
		self._up1 = lambda *a: self._up(*a)[0]
		if short_header:
			next_ifd = short_header
		else:
			next_ifd = self._up1("I", fh.read(4))
		self.reinit_from(next_ifd, short_header)
	
	def reinit_from(self, next_ifd, short_header=False):
		self.ifd = []
		self.subifd = []
		while next_ifd:
			self.ifd.append(self._ifdread(next_ifd))
			if short_header: return
			next_ifd = self._up1("I", self._fh.read(4))
		subifd = self.ifdget(self.ifd[0], 0x14a) or []
		for next_ifd in subifd:
			self.subifd.append(self._ifdread(next_ifd))
	
	def ifdget(self, ifd, tag):
		if tag in ifd:
			type, vc, off = ifd[tag]
			if type not in self.types: return None
			if isinstance(off, int): # offset
				self._fh.seek(off)
				tl, fmt = self.types[type]
				off = self._fh.read(tl * vc)
				if fmt: off = self._up(fmt * vc, off)
			if isinstance(off, basestring):
				off = off.rstrip("\0")
			return off
	
	def _ifdread(self, next_ifd):
		ifd = {}
		self._fh.seek(next_ifd)
		count = self._up1("H", self._fh.read(2))
		for i in range(count):
			d = self._fh.read(12)
			tag, type, vc = self._up("HHI", d[:8])
			if type in self.types and self.types[type][0] * vc <= 4:
				tl, fmt = self.types[type]
				d = d[8:8 + (tl * vc)]
				if fmt:
					off = self._up(fmt * vc, d)
				else:
					off = d # ASCII
			else:
				off = self._up1("I", d[8:])
			ifd[tag] = (type, vc, off)
		return ifd

class FileWindow:
	"""A read only view of a range of an fh. You should not continue to use fh."""
	def __init__(self, fh, start=None, length=None):
		if start is None:
			start = fh.tell()
		if length is None or length < 0:
			fh.seek(0, 2)
			stop = fh.tell()
		else:
			stop = start + length
		self.fh = fh
		self.start = start
		self.stop = stop
		self.closed = False
		fh.seek(start)
		assert fh.tell() == start
	
	def read(self, size=-1):
		if size < 0: size = self.stop - self.fh.tell()
		if size <= 0: return ""
		return self.fh.read(size)
	
	def tell(self):
		return self.fh.tell() - self.start
	
	def seek(self, pos, whence=0):
		if whence == 0:
			pos += self.start
		elif whence == 1:
			pos += self.fh.tell()
		else:
			pos += self.stop
		pos = max(min(pos, self.stop), self.start)
		self.fh.seek(pos)
	
	def close(self):
		if not self.closed:
			self.fh.close()
			self.closed = True

class exif_wrapper:
	"""Wrapper for several EXIF libraries.
	Starts out with an internal parser, falls back to two incompatible
	versions of pyexiv2 for fields it doesn't know about.
	
	Never fails, just returns empty data (even if file doesn't exist)."""
	
	def __init__(self, fn):
		self._d = {}
		try:
			self._internal(fn)
		except Exception:
			pass
		try:
			self._pyexiv2_old(fn)
		except Exception:
			try:
				self._pyexiv2_new(fn)
			except Exception:
				pass
	
	def _getitem(self, name): # usually overridden from pyexiv2
		raise KeyError(name)
	def _contains(self, name): # usually overridden from pyexiv2
		return False
	
	def __getitem(self, name):
		if name in self._d: return self._d[name]
		return self._getitem(name)
	def _fmtrational(self, n, d, intasint=True):
		if n == d == 0: return "0"
		if d == 0: return None # not valid
		if d < 0:
			n = -n
			d = -d
		if d == 1: return str(n)
		if intasint and not n % d: return str(n // d)
		def dec(n, d):
			pos = 0
			while d > 1:
				d //= 10
				pos -= 1
			v = str(n)
			return v[:pos] + "." + v[pos:]
		def rat():
			return "%d/%d" % (n, d)
		def isdec():
			return str(d).rstrip("0") == "1" # A nice decimal number
		if d > n: # < 1, probably a shutter speed, leave it.
			return rat()
		if isdec():
			return dec(n, d)
		if not n % d: return str(n // d) + ".0"
		gcd, tmp = n, d
		while tmp:
			gcd, tmp = tmp, gcd % tmp
		n //= gcd
		d //= gcd
		if isdec():
			return dec(n, d)
		fix = {2: 5, 4: 25, 5: 2, 8: 125, 16: 625, 20: 5, 25: 4, 32: 3125,
		       40: 25, 50: 2, 80: 125, 125: 8, 160: 625, 200: 5, 250: 4,
		       400: 25, 500: 2, 625: 16, 800: 125, 1250: 8, 2000: 5,
		       2500: 4, 3125: 32, 4000: 25, 5000: 2, 6250: 16, 12500: 8,
		       20000: 5, 25000: 4, 50000: 2}
		if d not in fix: return rat()
		return dec(n * fix[d], d * fix[d]).rstrip("0.")
	def __getitem__(self, name):
		v = self.__getitem(name)
		if isinstance(v, tuple):
			return self._fmtrational(*v)
		if hasattr(v, "numerator") and not isinstance(v, (int, long)):
			return self._fmtrational(v.numerator, v.denominator)
		return v
	
	def __contains__(self, name):
		return name in self._d or self._contains(name)
	
	def _pyexiv2_old(self, fn):
		from pyexiv2 import Image
		exif = Image(fn)
		exif.readMetadata()
		keys = set(exif.exifKeys())
		self._getitem = exif.__getitem__
		self._contains = keys.__contains__
	
	def _pyexiv2_new(self, fn):
		from pyexiv2 import ImageMetadata
		exif = ImageMetadata(fn)
		exif.read()
		self._exif = exif
		self._getitem = self._new_getitem
		self._contains = exif.__contains__
	
	def _new_getitem(self, *a):
		return self._exif.__getitem__(*a).value
	
	def _internal(self, fn):
		fh = file(fn, "rb")
		try:
			data = fh.read(12)
			if data[:3] == "\xff\xd8\xff": # JPEG
				from struct import unpack
				data = data[3:]
				while data and data[3:7] != "Exif":
					l = unpack(">H", data[1:3])[0]
					fh.seek(l - 7, 1)
					data = fh.read(9)
				if not data: return
				# Now comes a complete TIFF, with offsets relative to its' start
				l = unpack(">H", data[1:3])[0]
				fh = FileWindow(fh, length=l)
			# hopefully mostly TIFF (now)
			fh.seek(0)
			tiff = TIFF(fh) # This is the outer TIFF
			ifd0 = tiff.ifd[0]
			exif = tiff.ifdget(ifd0, 0x8769)[0]
			tiff.reinit_from(exif) # replace with Exif IFD(s)
			ifd0.update(tiff.ifd[0]) # merge back into original ifd0
			self._tiff = tiff
			self._ifd = ifd0
			for tag, name, t in ((0x010f, "Exif.Image.Make", False),
			                     (0x0110, "Exif.Image.Model", False),
			                     (0x0112, "Exif.Image.Orientation", False),
			                     (0x829a, "Exif.Photo.ExposureTime", True),
			                     (0x829d, "Exif.Photo.FNumber", True),
			                     (0x8827, "Exif.Photo.ISOSpeedRatings", True),
			                     (0x9003, "Exif.Photo.DateTimeOriginal", False),
			                     (0x9004, "Exif.Photo.CreateDate", False),
			                     (0x920a, "Exif.Photo.FocalLength", True),
			                     (0xa405, "Exif.Photo.FocalLengthIn35mmFilm", False),
			                    ):
				val = self._get(tag, t)
				if val is not None: self._d[name] = val
			try:
				self._parse_makernotes()
			except Exception:
				pass
		finally:
			fh.close()
	
	def _get(self, tag, tuple_ok=False):
		d = self._tiff.ifdget(self._ifd, tag)
		if type(d) is tuple:
			if len(d) == 1: return d[0]
			if not tuple_ok: return None
		return d
	
	def _parse_makernotes(self):
		if "Exif.Image.Make" not in self: return
		make = self["Exif.Image.Make"]
		if make[:7] == "PENTAX ":
			if 0x927c in self._ifd:
				type, vc, off = self._ifd[0x927c]
				if type != 7: return
			elif 0xc634 in self._ifd:
				type, vc, off = self._ifd[0xc634]
				if type != 1: return
			else:
				return
			fh = self._tiff._fh
			fh.seek(off)
			data = fh.read(vc)
			self._pentax_makernotes(data)
	
	def _pentax_makernotes(self, data):
		from cStringIO import StringIO
		if data[:4] == "AOC\0": # JPEG/PEF MakerNotes
			fh = StringIO(data[4:])
		elif data[:8] == "PENTAX \0": # DNG MakerNotes
			fh = StringIO(data[8:])
		else:
			return
		t = TIFF(fh, short_header=2)
		lens = " ".join(map(str, t.ifdget(t.ifd[0], 0x3f)))
		self._d["Exif.Pentax.LensType"] = lens
	
	def date(self):
		"""Return some reasonable EXIF date field as unix timestamp, or None"""
		fields = ("Exif.Image.Date", "Exif.Photo.DateTimeOriginal", "Exif.Photo.CreateDate")
		for f in fields:
			try:
				date = self[f]
				if isinstance(date, basestring):
					try:
						from time import strptime, mktime
						date = mktime(strptime(date, "%Y:%m:%d %H:%M:%S"))
					except Exception:
						pass
				try:
					date = int(date.strftime("%s"))
				except Exception:
					pass
				return int(date)
			except Exception:
				pass

raw_exts = ("dng", "pef", "nef")

def _identify_raw(fh, tiff):
	ifd0 = tiff.ifd[0]
	if 0xc612 in ifd0: return "dng"
	if 0x010f in ifd0:
		type, count, off = ifd0[0x010f]
		if type == 2:
			fh.seek(off)
			make = fh.read(min(count, 7))
			if make[:7] == "PENTAX ":
				return "pef"
			if make[:6] == "NIKON ":
				return "nef"
def identify_raw(fh):
	"""A lower case file extension (e.g. "dng") or None."""
	return _identify_raw(fh, TIFF(fh))

class FileMerge:
	"""Merge ranges of several files"""
	def __init__(self):
		self.contents = []
		self.pos = 0
		self.size = 0
		self.closed = False

	def add(self, fh, pos=0, z=-1):
		"""Add a file, from pos to pos + z"""
		assert pos >= 0
		if z < 0:
			fh.seek(0, 2)
			z = fh.tell() - pos
		assert z > 0
		self.contents.append((fh, pos, z))
		self.size += z

	def close(self):
		if self.closed: return
		done = set()
		for c in self.contents:
			if id(c[0]) not in done:
				done.add(id(c[0]))
				try:
					close(c[0])
				except Exception:
					pass
		self.closed = True

	def read(self, size=-1):
		if self.closed: raise ValueError("I/O operation on closed file")
		max_size = self.size - self.pos
		if size < 0 or size > max_size: size = max_size
		data = ""
		skip = self.pos
		for fh, pos, z in self.contents:
			if skip > z:
				skip -= z
			else:
				fh.seek(pos + skip)
				rsize = min(size, z - skip)
				r = fh.read(rsize)
				assert len(r) == rsize
				data += r
				size -= rsize
				skip = 0
			if not size: break
		self.pos += len(data)
		return data

	def seek(self, offset, whence=0):
		if self.closed: raise ValueError("I/O operation on closed file")
		if not 0 <= whence <= 2: raise IOError("bad whence: " + str(whence))
		if whence == 0:
			pos = offset
		elif whence == 1:
			pos = self.pos + offset
		elif whence == 2:
			pos = self.size + offset
		if pos > self.size: pos = self.size
		if pos < 0: pos = 0
		self.pos = pos

	def tell(self):
		return self.pos

class _ThinExif(TIFF):
	"""Pretty minimal TIFF container parser
	Even more minimal now - just for partial Exif parsing"""
	
	def reinit_from(self, next_ifd, short_header=False):
		self.ifd = self._ifdread(next_ifd)
	
	def ifdget(self, tag):
		if tag in self.ifd:
			type, vc, off = self.ifd[tag]
			if type not in self.types: return None
			if isinstance(off, int): # offset
				self._fh.seek(off)
				tl, fmt = self.types[type]
				off = self._fh.read(tl * vc)
				if fmt: off = self._up(fmt * vc, off)
			return type, off

class MakeTIFF:
	types = {1: "B", # BYTE
	         3: "H", # SHORT
	         4: "I", # LONG
	         5: "I", # RATIONAL
	        }

	def __init__(self):
		self.entries = {}

	def add(self, tag, values):
		self.entries[tag] = values

	def _one(self, tag, data):
		from struct import pack
		type, values = data
		if isinstance(values, str):
			d = pack(">HHI", tag, 2, len(values))
		else:
			f = self.types[type]
			z = len(values)
			if type == 5: z /= 2
			values = pack(">" + (f * len(values)), *values)
			d = pack(">HHI", tag, type, z)
			if len(values) <= 4:
				d += (values + "\x00\x00\x00")[:4]
				values = None
		if values:
			d += pack(">I", self._datapos)
			values = (values + "\x00\x00\x00")[:((len(values) + 3) // 4) * 4]
			self._data += values
			self._datapos += len(values)
		return d

	def serialize(self, offset=0):
		from struct import pack
		data = pack(">ccHIH", "M", "M", 42, 8, len(self.entries))
		self._datapos = 10 + 12 * len(self.entries) + 4 + offset
		self._data = ""
		for tag in sorted(self.entries):
			data += self._one(tag, self.entries[tag])
		data += pack(">I", 0)
		data += self._data
		return data

def _rawexif(raw, fh):
	from struct import pack, unpack
	from cStringIO import StringIO
	fm = FileMerge()
	def read_marker():
		while 42:
			d = fh.read(1)
			if d != "\xFF": return d
	fh.seek(0)
	assert read_marker() == "\xD8"
	first = fh.tell()
	marker = read_marker()
	while marker == "\xE0": # APP0, most likely JFIF
		first = fh.tell() + unpack(">H", fh.read(2))[0] - 2
		fh.seek(first)
		marker = read_marker()
	fm.add(fh, 0, first)
	if marker == "\xE1": # APP1, most likely Exif
		candidate = fh.tell() + unpack(">H", fh.read(2))[0] - 2
		if fh.read(5) == "Exif\x00":
			# Already has EXIF, leave as is.
			fh.seek(0)
			return fh
		first = candidate
		fh.seek(first)
		marker = read_marker()
	raw.seek(0)
	exif0 = MakeTIFF()
	exif1 = MakeTIFF()
	raw_exif = _ThinExif(raw)
	for k in 0x010f, 0x0110, 0x0112, 0x0131, 0x0132, 0x013b, 0x8298, 0xc614:
		d = raw_exif.ifdget(k)
		if d: exif0.add(k, d)
	offset = len(exif0.serialize()) + 12
	exif0.add(0x8769, (4, (offset,)))
	exif_ifd = raw_exif.ifd[0x8769][2][0]
	raw_exif.reinit_from(exif_ifd)
	for k in raw_exif.ifd:
		d = raw_exif.ifdget(k)
		if d: exif1.add(k, d)
	exif = "Exif\x00\x00"
	exif += exif0.serialize() + exif1.serialize(offset - 8)[8:]
	exif = "\xFF\xE1" + pack(">H", len(exif) + 2) + exif
	fm.add(StringIO(exif))
	fm.add(fh, first)
	return fm

class raw_wrapper:
	"""Wraps (read only) IO to an image, so that RAW images look like JPEGs.
	Handles DNG, NEF and PEF.
	Wraps fh as is if no reasonable embedded JPEG is found."""
	
	def __init__(self, fh, make_exif=False):
		self._set_fh(fh)
		try:
			tiff = TIFF(self)
			fmt = _identify_raw(self, tiff)
			if fmt == "dng" and len(tiff.subifd) > 1:
				jpeg = tiff.ifdget(tiff.subifd[1], 0x111)
				jpeglen = tiff.ifdget(tiff.subifd[1], 0x117)
				self._test_jpeg(jpeg, jpeglen)
			elif fmt == "nef" and tiff.subifd:
				jpeg = tiff.ifdget(tiff.subifd[0], 0x201)
				jpeglen = tiff.ifdget(tiff.subifd[0], 0x202)
				self._test_jpeg(jpeg, jpeglen)
			elif fmt == "pef": self._test_pef(tiff)
		except Exception:
			pass
		self.seek(0)
		if make_exif and self._fh != fh:
			self._set_fh(_rawexif(fh, self._fh))
		self.closed = False
	
	def _set_fh(self, fh):
		self._fh = fh
		self.read = fh.read
		self.seek = fh.seek
		self.tell = fh.tell
	
	def close(self):
		if not self.closed:
			self._fh.close()
			self.closed = True
	
	def _test_pef(self, tiff):
		for ifd in tiff.ifd[1:]:
			w, h = tiff.ifdget(ifd, 0x100), tiff.ifdget(ifd, 0x101)
			if w and h and max(w[0], h[0]) > 1000: # looks like a real image
				jpeg = tiff.ifdget(ifd, 0x201)
				jpeglen = tiff.ifdget(ifd, 0x202)
				if self._test_jpeg(jpeg, jpeglen): return True
	
	def _test_jpeg(self, jpeg, jpeglen):
		if not jpeg or not jpeglen: return
		if len(jpeg) != len(jpeglen): return
		jpeg, jpeglen = jpeg[-1], jpeglen[-1]
		self.seek(jpeg)
		if self.read(3) == "\xff\xd8\xff":
			self._set_fh(FileWindow(self._fh, jpeg, jpeglen))
			return True

def make_pdirs(fn):
	"""Like mkdir -p `dirname fn`"""
	import os.path
	dn = os.path.dirname(fn)
	if not os.path.exists(dn): os.makedirs(dn)
