# -*- coding: iso-8859-1 -*-

class _tiff:
	"""Pretty minimal TIFF container parser"""
	
	def __init__(self, fh):
		from struct import unpack
		self._fh = fh
		d = fh.read(4)
		if d not in ("II*\0", "MM\0*"): raise Exception("Not TIFF")
		endian = {"M": ">", "I": "<"}[d[0]]
		self._up = lambda fmt, *a: unpack(endian + fmt, *a)
		self._up1 = lambda *a: self._up(*a)[0]
		next_ifd = self._up1("I", fh.read(4))
		self.reinit_from(next_ifd)
	
	def reinit_from(self, next_ifd):
		self.ifd = []
		while next_ifd:
			self.ifd.append(self._ifdread(next_ifd))
			next_ifd = self._up1("I", self._fh.read(4))
		self.subifd = []
		subifd = self.ifdget(self.ifd[0], 0x14a) or []
		for next_ifd in subifd:
			self.subifd.append(self._ifdread(next_ifd))
	
	def ifdget(self, ifd, tag):
		if tag in ifd:
			type, vc, off = ifd[tag]
			if type in (3, 4): # SHORT or LONG
				if vc == 1: return (off,)
				self._fh.seek(off)
				dt = {3: "H", 4: "I"}[type]
				return self._up(dt * vc, self._fh.read(4 * vc))
			elif type == 2: # STRING
				self._fh.seek(off)
				return self._fh.read(vc).rstrip("\0")
	
	def _ifdread(self, next_ifd):
		ifd = {}
		self._fh.seek(next_ifd)
		count = self._up1("H", self._fh.read(2))
		for i in range(count):
			d = self._fh.read(12)
			tag, type, vc = self._up("HHI", d[:8])
			if type == 3 and vc == 1:
				off = self._up1("H", d[8:10])
			else:
				off = self._up1("I", d[8:])
			ifd[tag] = (type, vc, off)
		return ifd

class exif_wrapper:
	"""Wrapper for several EXIF libraries.
	Tries to use two incompatible versions of pyexiv2, and then falls back
	to internal (less functional) EXIF parser. Presents the same interface
	to all three.
	
	Never fails, just returns empty data (even if file doesn't exist)."""
	
	def __init__(self, fn):
		try:
			self._pyexiv2_old(fn)
		except Exception:
			try:
				self._pyexiv2_new(fn)
			except Exception:
				try:
					self._internal(fn)
				except Exception:
					d = {}
					self.__getitem__ = d.__getitem__
					self.__contains__ = d.__contains__
	
	def _pyexiv2_old(self, fn):
		from pyexiv2 import Image
		exif = Image(fn)
		exif.readMetadata()
		keys = set(exif.exifKeys())
		self.__getitem__ = exif.__getitem__
		self.__contains__ = keys.__contains__
	
	def _pyexiv2_new(self, fn):
		from pyexiv2 import ImageMetadata
		exif = ImageMetadata(fn)
		exif.read()
		self._exif = exif
		self.__getitem__ = self._new_getitem
		self.__contains__ = exif.__contains__
	
	def _new_getitem(self, *a):
		return self._exif.__getitem__(*a).value
	
	def _internal(self, fn):
		fh = file(fn, "rb")
		try:
			data = fh.read(12)
			if data[:3] == "\xff\xd8\xff": # JPEG
				from struct import unpack
				from cStringIO import StringIO
				data = data[3:]
				while data and data[3:7] != "Exif":
					l = unpack(">H", data[1:3])[0]
					fh.seek(l - 7, 1)
					data = fh.read(9)
				if not data: return
				# Now comes a complete TIFF, with offsets relative to its' start
				l = unpack(">H", data[1:3])[0]
				data = fh.read(l)
				fh.close()
				fh = StringIO(data)
			# hopefully mostly TIFF (now)
			fh.seek(0)
			tiff = _tiff(fh) # This is the outer TIFF
			ifd0 = tiff.ifd[0]
			exif = tiff.ifdget(ifd0, 0x8769)[0]
			tiff.reinit_from(exif) # replace with Exif IFD(s)
			ifd0.update(tiff.ifd[0]) # merge back into original ifd0
			self._tiff = tiff
			self._ifd = ifd0
			d = {}
			for tag, name in ((0x010f, "Exif.Image.Make"),
					  (0x0110, "Exif.Image.Model"),
					  (0x0112, "Exif.Image.Orientation"),
					  (0x9003, "Exif.Photo.DateTimeOriginal"),
					  (0x9004, "Exif.Photo.CreateDate"),
					 ):
				val = self._get(tag)
				if val is not None: d[name] = val
			self.__contains__ = d.__contains__
			self.__getitem__ = d.__getitem__
		finally:
			fh.close()
	
	def _get(self, tag):
		d = self._tiff.ifdget(self._ifd, tag)
		if type(d) is tuple:
			if len(d) == 1: return d[0]
			return None
		return d
	
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
	return _identify_raw(fh, _tiff(fh))

class raw_wrapper:
	"""Wraps (read only) IO to an image, so that RAW images look like JPEGs.
	Handles DNG, NEF and PEF.
	Wraps fh as is if no reasonable embedded JPEG is found."""
	
	def __init__(self, fh):
		self._set_fh(fh)
		try:
			tiff = _tiff(self)
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
	
	def _set_fh(self, fh):
		self._fh = fh
		self.close = fh.close
		self.flush = fh.flush
		self.isatty = fh.isatty
		self.next = fh.next
		self.read = fh.read
		self.readline = fh.readline
		self.readlines = fh.readlines
		self.seek = fh.seek
		self.tell = fh.tell
	
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
			from cStringIO import StringIO
			self.seek(jpeg)
			data = self.read(jpeglen)
			self._set_fh(StringIO(data))
			return True

def make_pdirs(fn):
	"""Like mkdir -p `dirname fn`"""
	import os.path
	dn = os.path.dirname(fn)
	if not os.path.exists(dn): os.makedirs(dn)
