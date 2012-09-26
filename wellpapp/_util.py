# -*- coding: iso-8859-1 -*-

from base64 import b64encode, b64decode

__all__ = ("_uni", "_utf", "_enc", "_dec")

def _uni(s):
	if not isinstance(s, unicode):
		try:
			s = s.decode("utf-8")
		except UnicodeDecodeError:
			s = s.decode("iso-8859-1")
	return s

def _utf(s, allow_space=False):
	s = _uni(s)
	if not allow_space: assert u" " not in s
	return s.encode("utf-8")

def _enc(str):
	str = _utf(str, True)
	while len(str) % 3: str += b"\x00"
	return b64encode(str, b"_-")

def _dec(enc):
	if not enc: return u""
	enc = _utf(enc)
	str = b64decode(enc, b"_-")
	while str.endswith(b"\x00"): str = str[:-1]
	return str.decode("utf-8")
