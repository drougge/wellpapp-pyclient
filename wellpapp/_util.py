from base64 import b64encode, b64decode
from functools import partial
import sys

__all__ = ("_uni", "_uniw", "_enc", "_dec", "_strenc", "_strdec")

if sys.version_info[0] > 2:
	unicode = str
	unichr = chr

def _uni(s, allow_space=True):
	if not isinstance(s, unicode):
		try:
			s = s.decode("utf-8")
		except UnicodeDecodeError:
			s = s.decode("iso-8859-1")
	if not allow_space: assert u" " not in s
	return s

_uniw = partial(_uni, allow_space=False)

def _utf(s, allow_space=False):
	s = _uni(s, allow_space)
	return s.encode("utf-8")

def _enc(s):
	s = _utf(s, True)
	while len(s) % 3: s += b"\x00"
	return b64encode(s, b"_-").decode("ascii")

def _dec(enc):
	if not enc: return u""
	enc = _utf(enc)
	s = b64decode(enc, b"_-")
	while s.endswith(b"\x00"): s = s[:-1]
	return s.decode("utf-8")

def _strenc(s):
	res = []
	for c in s.replace(u"\\", u"\\\\"):
		n = ord(c)
		if n < 33 or c.isspace() or c in u"'\"`=" or not c.isprintable():
			if n <= 0xff:
				res.append(u"\\%03o" % (n,))
			elif n <= 0xffff:
				res.append(u"\\u%04x" % (n,))
			else:
				res.append(u"\\U%08x" % (n,))
		else:
			res.append(c)
	return u"".join(res)

def _strdec(s):
	src = iter(s.split(u"\\"))
	res = [next(src)]
	for part in src:
		if part == u"":
			res.append(u"\\")
		elif part[0] in "01234567":
			res.append(unichr(int(part[0:3], 8)))
			res.append(part[3:])
		elif part[0] == u"u":
			res.append(unichr(int(part[1:5], 16)))
			res.append(part[5:])
		elif part[0] == u"U":
			res.append(unichr(int(part[1:9], 16)))
			res.append(part[9:])
		else:
			# not right, but let's be lenient
			res.append(u"\\")
			res.append(part)
	return u"".join(res)
