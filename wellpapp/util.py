from __future__ import print_function

import sys

__all__ = ("FileMerge", "FileWindow", "MakeTIFF", "TIFF", "ExifWrapper",
           "identify_raw", "make_pdirs", "raw_exts", "RawWrapper",
           "CommentWrapper", "DotDict", "X3F",)

if sys.version_info[0] > 2:
	basestring = (bytes, str)
	unicode = str
	long = int

class TIFF:
	"""Pretty minimal TIFF container parser"""

	types = { 1: (1, "B"),  # BYTE
	          2: (1, None), # ASCII
	          3: (2, "H"),  # SHORT
	          4: (4, "I"),  # LONG
	          5: (8, "II"), # RATIONAL
	          6: (1, "b"),  # SBYTE
	          7: (1, None), # UNDEFINE
	          8: (2, "h"),  # SSHORT
	          9: (4, "i"),  # SLONG
	         10: (8, "ii"), # SRATIONAL
	         11: (4, "f"),  # FLOAT
	         12: (8, "d"),  # DOUBLE
	         13: (4, "I"),  # IFD
	        }

	def __init__(self, fh, allow_variants=True, short_header=False):
		from struct import unpack
		self._fh = fh
		d = fh.read(4)
		if short_header:
			if d[:2] not in (b"II", b"MM"): raise Exception("Not TIFF")
			self.variant = None
		else:
			good = [b"II*\0", b"MM\0*"]
			if allow_variants:
				# Olympus ORF, Panasonic RW2
				good += [b"IIRO", b"IIU\0"]
			if d not in good: raise Exception("Not TIFF")
			self.variant = d[2:4].strip(b"\0")
		endian = {b"M": ">", b"I": "<"}[d[:1]]
		self._up = lambda fmt, *a: unpack(endian + fmt, *a)
		self._up1 = lambda *a: self._up(*a)[0]
		if short_header:
			next_ifd = short_header
		else:
			next_ifd = self._up1("I", fh.read(4))
		# Be conservative with possibly mis-detected ORF
		if self.variant == b"RO":
			assert next_ifd == 8
		self.reinit_from(next_ifd, short_header)

	def reinit_from(self, next_ifd, short_header=False):
		self.ifd = []
		self.subifd = []
		seen_ifd = set()
		while next_ifd:
			self.ifd.append(self._ifdread(next_ifd))
			if short_header: return
			next_ifd = self._up1("I", self._fh.read(4))
			if next_ifd in seen_ifd:
				from sys import stderr
				print("WARNING: Looping IFDs", file=stderr)
				break
			seen_ifd.add(next_ifd)
			assert len(self.ifd) < 32 # way too many
		subifd = self.ifdget(self.ifd[0], 0x14a) or []
		assert len(subifd) < 32 # way too many
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
			if type == 2:
				from ._util import _uni
				off = _uni(off.rstrip(b"\0"))
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

def _parse_date(d):
	from time import strptime, mktime
	def parse(d):
		for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
			while len(fmt) > 6:
				try:
					return strptime(d, fmt)
				except ValueError:
					pass
				fmt = fmt[:-3]
	tt = parse(d)
	return int(mktime(tt))


class ExifWrapper:
	"""Wrapper for several EXIF libraries.
	Starts out with an internal parser, falls back to GExiv2 for fields
	(and formats) it doesn't know about. (Only works if given a filename.)

	Never fails, just returns empty data (even if file doesn't exist)."""

	def __init__(self, fn):
		self._d = {}
		self._gexiv2_loaded = None
		if isinstance(fn, str):
			self.fn = fn
			fh = None
		else:
			self.fn = None
			fh = fn
		try:
			self._internal(fh)
		except Exception:
			pass

	def _getitem(self, name): # usually overridden from gexiv2
		raise KeyError(name)
	def _contains(self, name): # usually overridden from gexiv2
		return False

	def __getitem(self, name):
		if name in self._d: return self._d[name]
		self._gexiv2()
		v = self._getitem(name)
		if name in ("Exif.Photo.FNumber", "Exif.Photo.FocalLength"):
			a, b = map(int, v.split("/"))
			v = (a, b)
		elif name in (
			"Exif.Image.Orientation", "Exif.Photo.ISOSpeedRatings",
			"Exif.Photo.FocalLengthIn35mmFilm", "Exif.GPSInfo.GPSAltitudeRef",
		):
			v = int(v)
		elif name in ("Exif.GPSInfo.GPSLatitude", "Exif.GPSInfo.GPSLongitude"):
			from fractions import Fraction
			v = [Fraction(*map(int, vv.split("/"))) for vv in v.split()]
		elif name == "Exif.GPSInfo.GPSAltitude":
			a, b = map(float, v.split("/"))
			v = a / b
		return v
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
			if len(v) > 2:
				res = []
				for r in zip(v[::2], v[1::2]):
					r = self._fmtrational(*r)
					if r is None:
						r = "-"
					res.append(r)
				return " ".join(res)
			else:
				return self._fmtrational(*v)
		if hasattr(v, "numerator") and not isinstance(v, (int, long)):
			return self._fmtrational(v.numerator, v.denominator)
		return v

	def __contains__(self, name):
		if name in self._d:
			return True
		self._gexiv2()
		return self._contains(name)

	def _gexiv2(self):
		if self._gexiv2_loaded is not None or not self.fn:
			return
		try:
			import gi
			gi.require_version('GExiv2', '0.10')
			from gi.repository import GExiv2
		except Exception as e:
			self._gexiv2_loaded = False
			print("Failed to load GExiv2:", str(e), file=sys.stderr)
			print("(Maybe you need to install gir1.2-gexiv2-0.10 or similar?)", file=sys.stderr)
			return
		try:
			exif = GExiv2.Metadata(self.fn)
			self._getitem = exif.__getitem__
			self._contains = exif.__contains__
			self._gexiv2_loaded = True
		except Exception:
			self._gexiv2_loaded = False

	def _internal(self, fh=None):
		fh = fh or open(self.fn, "rb")
		try:
			data = fh.read(12)
			if data.startswith(b"FOVb"): # X3F
				fh.seek(0)
				x3f = X3F(fh)
				if x3f.jpegs:
					j = x3f.jpegs[-1]
					fh = FileWindow(fh, j.offset, j.length)
					data = fh.read(12)
				x3f2exif = dict(
					FLENGTH="Exif.Photo.FocalLength",
					FLEQ35MM=("Exif.Photo.FocalLengthIn35mmFilm", lambda v: int(round(float(v))),),
					ISO=("Exif.Photo.ISOSpeedRatings", int,),
					SH_DESC="Exif.Photo.ExposureTime",
					AP_DESC="Exif.Photo.FNumber",
					CAMMODEL="Exif.Image.Model",
					CAMMANUF="Exif.Image.Make",
				)
				for key in set(x3f2exif) & set(x3f.prop):
					value = x3f.prop[key]
					conv = x3f2exif[key]
					if isinstance(conv, tuple):
						value = conv[1](value)
						conv = conv[0]
					self._d[conv] = value
				self._d.update(("X3F." + k, v) for k, v in x3f.prop.items())
			elif data.startswith(b"FUJI"): # RAF
				try:
					offset, length = _RAF_jpeg(fh)
					fh.seek(offset)
					data = fh.read(12)
				except Exception:
					pass
			if data[:3] == b"\xff\xd8\xff": # JPEG
				from struct import unpack
				data = data[3:]
				while data and data[3:7] != b"Exif":
					l = unpack(">H", data[1:3])[0]
					fh.seek(l - 7, 1)
					data = fh.read(9)
					if data[0] == b"\xDA": # Start of Scan
						return
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
			                     (0xa430, "Exif.Photo.OwnerName", False),
			                     (0xa431, "Exif.Photo.SerialNumber", False),
			                     (0xa432, "Exif.Photo.LensInfo", True),
			                     (0xa433, "Exif.Photo.LensMake", False),
			                     (0xa434, "Exif.Photo.LensModel", False),
			                     (0xa435, "Exif.Photo.LensSerialNumber", False),
			                    ):
				val = self._get(tag, t)
				if val is not None: self._d[name] = val
			try:
				self._parse_makernotes()
			except Exception:
				pass
			fl = "Exif.Photo.FocalLength"
			fl135 = "Exif.Photo.FocalLengthIn35mmFilm"
			if (fl135 not in self._d or not self._d[fl135]) and fl in self._d:
				model = self._d.get("Exif.Image.Model")
				n, d = self._d[fl]
				if model.startswith("Canon EOS 5D"):
					self._d[fl135] = int(n / float(d))
				elif model.startswith("E-P") or model.startswith("E-M") or model.startswith("DMC-G"):
					self._d[fl135] = int(n * 2.0 / d)
				elif model == 'Canon PowerShot A590 IS':
					self._d[fl135] = int(n * 5.9 / d)
				elif model == 'Canon PowerShot A610':
					self._d[fl135] = int(n * 4.7 / d)
			gps = self._get(0x8825)
			if gps:
				tiff.reinit_from(gps)
				self._ifd = tiff.ifd[0]
				for tag, name, t in ((0x0001, "Exif.GPSInfo.GPSLatitudeRef", False),
				                     (0x0002, "Exif.GPSInfo.GPSLatitude", True),
				                     (0x0003, "Exif.GPSInfo.GPSLongitudeRef", False),
				                     (0x0004, "Exif.GPSInfo.GPSLongitude", True),
				                     (0x0005, "Exif.GPSInfo.GPSAltitudeRef", False),
				                     (0x0006, "Exif.GPSInfo.GPSAltitude", False),
				                    ):
					val = self._get(tag, t)
					if val is not None:
						from fractions import Fraction
						if t:
							val = [Fraction(*v) for v in  zip(val[::2], val[1::2])]
						self._d[name] = val
		finally:
			fh.close()

	def _get(self, tag, tuple_ok=False):
		d = self._tiff.ifdget(self._ifd, tag)
		if type(d) is tuple:
			if len(d) == 1: return d[0]
			if not tuple_ok: return None
			if d == (): return None
		return d

	def _parse_makernotes(self):
		fh = self._tiff._fh
		if 0x927c in self._ifd:
			type, vc, off = self._ifd[0x927c]
			if type != 7: return
		elif 0xc634 in self._ifd:
			type, vc, off = self._ifd[0xc634]
			if type != 1: return
		elif self.fn: # This is not a wrapped embedded jpeg
			# No makernotes found - try again from embedded jpeg
			# (At least Panasonic RW2 needs this.)
			fh.seek(0)
			j_fh = RawWrapper(fh)._fh
			if j_fh == fh: return
			inner = ExifWrapper(j_fh)
			for k in set(inner._d) - set(self._d):
				self._d[k] = inner._d[k]
			return
		else:
			return
		fh.seek(off)
		data = fh.read(vc)
		if b"\0" not in data: return
		mid = data[:data.find(b"\0")]
		{
			b"AOC"      : self._pentax_makernotes,
			b"PENTAX "  : self._pentax_makernotes,
			b"OLYMPUS"  : self._olympus_makernotes,
			b"Panasonic": self._panasonic_makernotes,
		}.get(mid, lambda _: _)(data, off)
		if self._d.get("Exif.Image.Make") == "Canon" and data[1:4] == "\x00\x01\x00":
			self._canon_makernotes(off)

	def _panasonic_makernotes(self, data, offset):
		# Headerless IFD after "Panasonic\0\0\0"
		# Offsets relative to EXIF block
		if not data.startswith("Panasonic\0\0\0"):
			return
		tiff = self._tiff
		b_ifd, b_subifd = tiff.ifd, tiff.subifd
		try:
			tiff.reinit_from(offset + 12, True)
			lens = tiff.ifdget(tiff.ifd[0], 0x0051)
			if lens:
				self._d["Exif.Panasonic.LensType"] = lens.strip()
		finally:
			tiff.ifd, tiff.subifd = b_ifd, b_subifd

	def _canon_makernotes(self, off):
		# stupid Canon, no header, and offsets relative to EXIF block.
		tiff = self._tiff
		b_ifd, b_subifd = tiff.ifd, tiff.subifd
		try:
			tiff.reinit_from(off)
			lens = tiff.ifdget(tiff.ifd[0], 0x0095)
			if lens:
				self._d["Exif.Canon.LensModel"] = lens
		finally:
			tiff.ifd, tiff.subifd = b_ifd, b_subifd

	def _olympus_makernotes(self, data, offset):
		from io import BytesIO
		fh = BytesIO(data)
		try:
			fh.seek(8)
			t = TIFF(fh, short_header=12)
			offset = t.ifdget(t.ifd[0], 0x2010)[0]
			t.reinit_from(offset)
			data = t.ifdget(t.ifd[0], 0x0203)
			assert isinstance(data, bytes)
			self._d["Exif.OlympusEq.LensModel"] = data.strip()
		except Exception:
			pass

	def _pentax_makernotes(self, data, offset):
		from io import BytesIO
		fh = BytesIO(data[data.find(b"\0") + 1:])
		try:
			t = TIFF(fh, short_header=2)
			lens = " ".join(map(str, t.ifdget(t.ifd[0], 0x3f)))
			self._d["Exif.Pentax.LensType"] = lens
		except Exception:
			pass

	def date(self, tz=None):
		"""Return some reasonable EXIF date field as VTdatetime, or None
		Will guess the timezone (based on environment) if not specified.
		"""
		from wellpapp.vt import VTdatetime
		from time import gmtime, localtime, mktime, strftime
		fields = ("Exif.Photo.DateTimeOriginal", "Exif.Photo.CreateDate", "Exif.Image.DateTime")
		for f in fields:
			try:
				if isinstance(self[f], basestring):
					dt = self[f].strip()
					d, t = dt.split(" ", 1)
					if " " in t:
						t, ltz = t.split(" ")
						ltz = tz or ltz
					elif tz:
						ltz = tz
					else:
						ut = _parse_date(dt)
						lt = list(localtime(ut))
						lt[8] = 0 # ignore dst
						td = int(mktime(gmtime(ut)) - mktime(tuple(lt))) // 60
						ltz = "%s%02d%02d" % ("+" if td <= 0 else "-", abs(td // 60), abs(td % 60))
					date = d.replace(":", "-") + "T" + t + ltz
				else:
					t = int(self[f].strftime("%s"))
					date = strftime("%Y-%m-%dT%H:%M:%SZ", gmtime(t))
				return VTdatetime(date)
			except Exception:
				pass

	def rotation(self):
		if "Exif.Image.Orientation" not in self: return -1
		o = self["Exif.Image.Orientation"]
		orient = {1: 0, 3: 180, 6: 90, 8: 270}
		if o not in orient: return -1
		return orient[o]

raw_exts = ("dng", "pef", "nef", "cr2", "orf", "rw2", "x3f", "raf",)

def _identify_raw(fh, tiff):
	ifd0 = tiff.ifd[0]
	if 0xc612 in ifd0: return "dng"
	if 0x010f in ifd0:
		type, count, off = ifd0[0x010f]
		if type == 2:
			fh.seek(off)
			make = fh.read(min(count, 10))
			if tiff.variant == "*":
				if make[:7] == b"PENTAX ":
					return "pef"
				if make[:6] == b"NIKON ":
					return "nef"
				if make[:5] == b"Canon":
					return "cr2"
			elif tiff.variant == b"RO" and make[:8] == b"OLYMPUS ":
				return "orf"
			elif tiff.variant == b"U" and make == b"Panasonic\0":
				return "rw2"
def identify_raw(fh):
	"""A lower case file extension (e.g. "dng") or None."""
	fh.seek(0)
	data4 = fh.read(4)
	if data4 == b"FOVb":
		return "x3f"
	if data4 == b"FUJI":
		try:
			offset, length = _RAF_jpeg(fh)
			return "raf"
		except Exception:
			pass
	fh.seek(0)
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
					c[0].close()
				except Exception:
					pass
		self.closed = True

	def read(self, size=-1):
		if self.closed: raise ValueError("I/O operation on closed file")
		max_size = self.size - self.pos
		if size < 0 or size > max_size: size = max_size
		data = b""
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

	# IOError instead of AttributeError
	def readline(self):
		raise IOError("FileMerge does not support readline")

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
	types = { 1: "B", # BYTE
	          3: "H", # SHORT
	          4: "I", # LONG
	          5: "I", # RATIONAL
	          6: "b", # SBYTE
	          8: "h", # SSHORT
	          9: "i", # SLONG
	         10: "i", # SRATIONAL
	         11: "f", # FLOAT
	         12: "d", # DOUBLE
	        }

	def __init__(self):
		self.entries = {}

	def add(self, tag, values):
		self.entries[tag] = values

	def _one(self, tag, data):
		from struct import pack
		type, values = data
		if isinstance(values, unicode):
			values = values.encode("utf-8")
		if isinstance(values, bytes):
			d = pack(">HHI", tag, 2, len(values))
		else:
			f = self.types[type]
			z = len(values)
			if type == 5: z //= 2
			values = pack(">" + (f * len(values)), *values)
			d = pack(">HHI", tag, type, z)
			if len(values) <= 4:
				d += (values + b"\x00\x00\x00")[:4]
				values = None
		if values:
			d += pack(">I", self._datapos)
			values = (values + b"\x00\x00\x00")[:((len(values) + 3) // 4) * 4]
			self._data += values
			self._datapos += len(values)
		return d

	def serialize(self, offset=0):
		from struct import pack
		data = pack(">ccHIH", b"M", b"M", 42, 8, len(self.entries))
		self._datapos = 10 + 12 * len(self.entries) + 4 + offset
		self._data = b""
		for tag in sorted(self.entries):
			data += self._one(tag, self.entries[tag])
		data += pack(">I", 0)
		data += self._data
		return data

def _rawexif(raw, fh):
	from struct import pack, unpack
	from io import BytesIO
	fm = FileMerge()
	def read_marker():
		while 42:
			d = fh.read(1)
			if d != b"\xFF": return d
	fh.seek(0)
	assert read_marker() == b"\xD8"
	first = fh.tell()
	marker = read_marker()
	while marker == b"\xE0": # APP0, most likely JFIF
		first = fh.tell() + unpack(">H", fh.read(2))[0] - 2
		fh.seek(first)
		marker = read_marker()
	fm.add(fh, 0, first)
	if marker == b"\xE1": # APP1, most likely Exif
		candidate = fh.tell() + unpack(">H", fh.read(2))[0] - 2
		if fh.read(5) == b"Exif\x00":
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
		if k == 0x927c: continue # Skip makernotes
		d = raw_exif.ifdget(k)
		if d: exif1.add(k, d)
	exif = b"Exif\x00\x00"
	exif += exif0.serialize() + exif1.serialize(offset - 8)[8:]
	exif = b"\xFF\xE1" + pack(">H", len(exif) + 2) + exif
	fm.add(BytesIO(exif))
	fm.add(fh, first)
	return fm

def _RAF_jpeg(fh):
	from struct import unpack
	fh.seek(84)
	offset, length = unpack(">II", fh.read(8))
	fh.seek(offset)
	if fh.read(3) == "\xff\xd8\xff":
		return offset, length

class X3F:
	"""Find JPEG sections and metadata in X3F files
	.jpegs is a list from smallest to largest.
	.prop is a dict {field: value}
	"""

	def __init__(self, fh):
		from collections import defaultdict, namedtuple
		self.X3F_JPEG = namedtuple("X3F_JPEG", "offset length cols rows")
		from struct import unpack
		assert fh.read(4) == b"FOVb"
		self.vminor, self.vmajor = unpack("<HH", fh.read(4))
		assert self.vmajor == 2
		fh.seek(-4, 2)
		index, = unpack("<I", fh.read(4))
		fh.seek(index)
		assert fh.read(4) == b"SECd" # section header
		secvminor, secvmajor = unpack("<HH", fh.read(4))
		assert secvmajor == 2
		nentries, = unpack("<I", fh.read(4))
		sections = defaultdict(list)
		for i in range(nentries):
			offset, length = unpack("<II", fh.read(8))
			typ = fh.read(4)
			sections[typ].append((offset, length,))
		self.jpegs = []
		for offset, length in sections[b"IMAG"] + sections[b"IMA2"]:
			fh.seek(offset)
			self._read_img(fh, length)
		self.jpegs.sort(key=lambda j: j.cols * j.rows)
		self.prop = {}
		for offset, length in sections[b"PROP"]:
			self._read_prop(fh, offset)

	def _read_img(self, fh, length):
		from struct import unpack
		assert fh.read(4) == b"SECi"
		vminor, vmajor = unpack("<HH", fh.read(4))
		assert vmajor == 2
		typ, = unpack("<I", fh.read(4))
		if typ != 2:
			return
		fmt, cols, rows, rowz = unpack("<IIII", fh.read(16))
		if fmt != 18:
			return
		offset = fh.tell()
		length -= 28
		self.jpegs.append(self.X3F_JPEG(offset=offset, length=length, cols=cols, rows=rows))

	def _read_prop(self, fh, offset):
		from struct import unpack
		fh.seek(offset)
		assert fh.read(4) == b"SECp"
		vminor, vmajor = unpack("<HH", fh.read(4))
		assert vmajor == 2
		nentries, fmt, _, totlen = unpack("<IIII", fh.read(16))
		if fmt != 0:
			return
		hdrs = fh.read(nentries * 8)
		offset = fh.tell()
		# Stupid format
		def getstr(str_off):
			fh.seek(offset + str_off*2)
			def reader():
				while True:
					v = fh.read(2)
					if v == b"\0\0" or not v:
						raise StopIteration
					yield v
			return b"".join(reader()).decode("utf-16le")
		while hdrs:
			name_off, value_off = unpack("<II", hdrs[:8])
			hdrs = hdrs[8:]
			self.prop[getstr(name_off)] = getstr(value_off)

class RawWrapper:
	"""Wraps (read only) IO to an image, so that RAW images look like JPEGs.
	Handles DNG, NEF, PEF, CR2, ORF, X3F and RAF.
	Wraps fh as is if no reasonable embedded JPEG is found."""

	def __init__(self, fh, make_exif=False):
		self.closed = False
		self._set_fh(fh)
		fh.seek(0)
		data4 = fh.read(4)
		if data4 == b"FOVb":
			try:
				fh.seek(0)
				x3f = X3F(fh)
				if x3f.jpegs:
					j = x3f.jpegs[-1]
					self._test_jpeg([j.offset], [j.length])
					# No make_exif support, but at least Sigma SD14 puts exif in this JPEG.
					return
			except Exception:
				pass
		elif data4 == b"FUJI":
			try:
				offset, length = _RAF_jpeg(fh)
				self._test_jpeg([offset], [length])
				# No make_exif support, but at least X-T2 puts exif in this JPEG.
				return
			except Exception:
				pass
		fh.seek(0)
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
			elif fmt == "pef":
				self._test_pef(tiff)
			elif fmt == "cr2":
				self._test_cr2(tiff)
			elif fmt == "orf":
				self._test_orf(tiff)
			elif fmt == "rw2":
				self._test_rw2(tiff)
		except Exception:
			pass
		self.seek(0)
		if make_exif and self._fh != fh:
			self._set_fh(_rawexif(fh, self._fh))

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
				if self._test_jpeg(jpeg, jpeglen):
					return True

	def _test_cr2(self, tiff):
		for ifd in tiff.ifd:
			w, h = tiff.ifdget(ifd, 0x100), tiff.ifdget(ifd, 0x101)
			if w and h and max(w[0], h[0]) > 1000: # looks like a real image
				jpeg = tiff.ifdget(ifd, 0x111)
				jpeglen = tiff.ifdget(ifd, 0x117)
				if self._test_jpeg(jpeg, jpeglen):
					return True

	def _test_orf(self, tiff):
		try:
			exif = tiff.ifdget(tiff.ifd[0], 0x8769)[0]
			tiff.reinit_from(exif)
			makernotes = tiff.ifd[0][0x927c][2]
			tiff._fh.seek(makernotes)
			assert tiff._fh.read(10) == b"OLYMPUS\0II"
			tiff.reinit_from(makernotes + 12)
			jpegifd = tiff.ifdget(tiff.ifd[0], 0x2020)[0]
			tiff.reinit_from(makernotes + jpegifd)
			jpegpos = tiff.ifdget(tiff.ifd[0], 0x101)[0]
			jpeglen = tiff.ifdget(tiff.ifd[0], 0x102)[0]
			return self._test_jpeg([makernotes + jpegpos], [jpeglen])
		except Exception:
			pass

	def _test_rw2(self, tiff):
		try:
			type, vc, off = tiff.ifd[0][0x2e]
			if type == 7:
				return self._test_jpeg([off], [vc])
		except Exception:
			pass

	def _test_jpeg(self, jpeg, jpeglen):
		if not jpeg or not jpeglen: return
		if len(jpeg) != len(jpeglen): return
		jpeg, jpeglen = jpeg[-1], jpeglen[-1]
		self.seek(jpeg)
		if self.read(3) == b"\xff\xd8\xff":
			self._set_fh(FileWindow(self._fh, jpeg, jpeglen))
			return True

	# This is needed so PIL gives an IOError and not an AttributeError on some files.
	def readline(self):
		raise IOError("RawWrapper doesn't support readline.")

def make_pdirs(fn):
	"""Like mkdir -p `dirname fn`"""

	import os.path
	dn = os.path.dirname(fn)
	if not os.path.exists(dn): os.makedirs(dn)

class CommentWrapper:
	"""Wrap a file so readline/iteration skips comments
	and optionally empty lines"""

	def __init__(self, fh, allow_empty=False):
		self.fh = fh
		self.allow_empty = allow_empty
		self.close = fh.close

	def __iter__(self):
		return self

	def __next__(self):
		line = self.readline()
		if not line: raise StopIteration()
		return line
	next = __next__

	def readline(self):
		while 42:
			line = self.fh.readline()
			if not line: return line
			s = line.strip()
			if s:
				if s[0] != "#": return line
			elif self.allow_empty:
				return line

	def __enter__(self):
		return self

	def __exit__(self, *exc):
		self.close()

class DotDict(dict):
	"""Like a dict, but with d.foo as well as d["foo"]."""

	__setattr__ = dict.__setitem__
	__delattr__ = dict.__delitem__
	def __getattr__(self, name):
		if name[0] == "_":
			raise AttributeError(name)
		return self.get(name)
	def __repr__(self):
		return repr(type(self)) + dict.__repr__(self)

