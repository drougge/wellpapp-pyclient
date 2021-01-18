from base64 import b64encode, b64decode
from functools import partial
import sys

__all__ = ("_uni", "_uniw", "_enc", "_dec")

if sys.version_info[0] > 2:
	unicode = str

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
