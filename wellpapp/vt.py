# -*- coding: iso-8859-1 -*-

import re
from fractions import Fraction
from decimal import Decimal
from abc import ABCMeta, abstractmethod, abstractproperty
from time import localtime, struct_time
from calendar import timegm
from math import log, log10

from wellpapp._util import _uni, _enc, _dec

__all__ = ("ValueType", 'VTstring', 'VTword', 'VTnumber', 'VTint', 'VTuint',
           'VTfloat', 'VTf_stop', 'VTstop', 'VTdatetime', 'VTgps', 'valuetypes',)

class ValueType(object):
	"""Represents the value of a tag.
	v.value is the value as an apropriate type (str, float, int).
	v.exact is an exact representation of the value (str, int, Fraction).
	v.fuzz is how inexact the value is.
	v.exact_fuzz is like .exact but for the fuzz.
	v.str (or str(v)) is a string representation of exact value+-fuzz.
	v.format() is this value formated for sending to server.
	
	Comparisons:
	== and != compare that both value and fuzz match,
	other comparisons apply the fuzz.
	Use value.overlap(other) to check for equality with fuzz."""
	
	__metaclass__ = ABCMeta
	
	@abstractmethod
	def __init__(self): pass
	
	@abstractproperty
	def type(self): pass
	
	@abstractproperty
	def _cmp_t(self): pass
	
	_repr_extra = ""
	_repr = None
	
	str = ""
	value = 0
	exact = 0
	fuzz = None
	exact_fuzz = None
	
	def __setattr__(self, name, value):
		raise AttributeError("ValueTypes are immutable")
	def __delattr__(self, name):
		raise AttributeError("ValueTypes are immutable")
	def __str__(self):
		return self.str
	def __repr__(self):
		c = self.__class__
		rs = repr(self._repr) if self._repr else repr(self.str)
		return c.__module__ + "." + c.__name__ + "(" + rs + self._repr_extra + ")"
	def __hash__(self):
		return hash(self.exact) ^ hash(self.exact_fuzz) ^ hash(self.type)
	def __cmp(self, other):
		if isinstance(self, VTnumber) and isinstance(other, (int, long, float)):
			return VTnumber(other)
		if not isinstance(other, ValueType) or self._cmp_t != other._cmp_t:
			raise TypeError("Can only compare to a " + self._cmp_t)
		return other
	def __eq__(self, other):
		return type(self) == type(other) and \
		       self.exact == other.exact and \
		       self.exact_fuzz == other.exact_fuzz
	def __ne__(self, other):
		if not isinstance(other, ValueType): return True
		return type(self) != type(other) or \
		       self.exact != other.exact or \
		       self.exact_fuzz != other.exact_fuzz
	def __lt__(self, other):
		other = self.__cmp(other)
		return self.min < other.max
	def __le__(self, other):
		other = self.__cmp(other)
		return self.min <= other.max
	def __gt__(self, other):
		other = self.__cmp(other)
		return self.max > other.min
	def __ge__(self, other):
		other = self.__cmp(other)
		return self.max >= other.min
	
	@property
	def min(self):
		f = self.fuzz or 0
		if f < 0:
			return self.value + f
		else:
			return self.value
	
	@property
	def max(self):
		if self.fuzz:
			return self.value + abs(self.fuzz)
		else:
			return self.value
	
	def overlap(self, other):
		other = self.__cmp(other)
		return self.min() <= other.max() and other.min() <= self.max()
	
	def format(self):
		return self.str

class VTstring(ValueType):
	"""Represents the value of a tag with valuetype string.
	v.value, v.exact and v.str are all the same string.
	There is no fuzz for strings."""
	
	type = "string"
	_cmp_t = "VTstring"
	_repr_extra = ", True"
	
	def __init__(self, val, human=False):
		if human:
			val = _uni(val)
		else:
			val = _dec(val)
		for name in ("str", "value", "exact"):
			self.__dict__[name] = val
	def __str__(self):
		return self.str.encode("utf-8")
	def __unicode__(self):
		return self.str
	def format(self):
		return _enc(self.str)

class VTword(VTstring):
	"""Represents the value of a tag with valuetype word.
	v.value, v.exact and v.str are all the same string.
	There is no fuzz for words."""
	
	type = "word"
	_repr_extra = ""
	
	def __init__(self, val, human=False):
		if " " in val: raise ValueError(val)
		val = _uni(val)
		for name in ("str", "value", "exact"):
			self.__dict__[name] = val
	def format(self):
		return self.str

class VTnumber(ValueType):
	_cmp_t = "VTnumber or simple number"
	type = "simple number wrapper"
	
	def __init__(self, number):
		if not isinstance(number, (int, long, float)):
			raise ValueError(number)
		self.__dict__["value"] = self.__dict__["exact"] = number
		self.__dict__["fuzz"] = self.__dict__["exact_fuzz"] = 0
	
	def _parse(self, v, vp, vp2, fp):
		v = str(v)
		self.__dict__["str"] = v
		a = v.split("+", 1)
		self.__dict__["exact"] = vp(a[0])
		self.__dict__["value"] = vp2(self.exact)
		if len(a) == 2:
			self.__dict__["exact_fuzz"] = fp(a[1])
			self.__dict__["fuzz"] = vp2(self.exact_fuzz)
		else:
			self.__dict__["fuzz"] = self.__dict__["exact_fuzz"] = 0
	
	def __int__(self):
		return int(self.exact)
	def __long__(self):
		return long(self.exact)
	def __float__(self):
		return float(self.exact)

class VTint(VTnumber):
	__doc__ = ValueType.__doc__
	type = "int"
	
	def __init__(self, val, human=False):
		self._parse(val, int, int, int)

class VTuint(VTnumber):
	__doc__ = ValueType.__doc__
	type = "uint"
	
	def __init__(self, val, human=False):
		p = int if human else lambda x: int(x, 16)
		self._parse(val, p, int, int)
		if self.fuzz:
			s = "%d+%d" % (self.value, self.fuzz)
			r = "%x+%d" % (self.value, self.fuzz)
		else:
			s = str(self.value)
			r = "%x" % (self.value,)
		self.__dict__["str"] = s
		self.__dict__["_repr"] = r
	def format(self):
		return self._repr

class VTfloat(VTnumber):
	__doc__ = ValueType.__doc__
	type = "float"
	
	def __init__(self, val, human=False):
		def intfrac(v):
			try:
				return int(v)
			except ValueError:
				return Fraction(v)
		self._parse(val, intfrac, float, intfrac)
	
	def _ffix(self, value, fuzzyfuzz):
		if self.fuzz > 0:
			value -= fuzzyfuzz
			self.__dict__["fuzz"] += 2 * fuzzyfuzz
		else:
			self.__dict__["fuzz"] -= fuzzyfuzz
		self.__dict__["value"] = value

class VTf_stop(VTfloat):
	__doc__ = ValueType.__doc__
	type = "f-stop"
	
	def __init__(self, val, human=False):
		VTfloat.__init__(self, val, human)
		self._ffix(2.0 * log(self.value, 2.0), 0.07)

class VTstop(VTfloat):
	__doc__ = ValueType.__doc__
	type = "stop"
	
	def __init__(self, val, human=False):
		VTfloat.__init__(self, val, human)
		self._ffix(10.0 * log10(self.value) / 3.0, 0.01)

class VTdatetime(ValueType):
	type = "datetime"
	_cmp_t = "VTdatetime"
	_ranges = (9999, 12, 31, 23, 59, 59)
	fres = r"(\+-?(?:\d+(?:\.\d+|/\d+)?))?"
	_re = re.compile(r"(\d{4})" + fres + (r"(?:-(\d\d)" + fres) * 2 + r"(?:([T ])" + \
	#                   YYYY                   mm + dd                      T
	                 r"(\d\d)" + fres + r"(?::(\d\d)" + fres + r"(?::(\d\d)" + \
	#                    HH                     MM                     SS
	                 r")?" * 5 + r"(\+-?(?:\d+(?:\.\d+|/\d+)?[YmdHMS]?))?$")
	#                                fuzz with unit
	del fres
	
	def __init__(self, val, human=False):
		try:
			strval = str(val)
		except Exception:
			raise ValueError(val)
		if not strval: raise ValueError(val)
		if strval[-1] == "Z":
			zone = "Z"
			offset = 0
			strval = strval[:-1]
		else:
			zone = strval[-5:]
			try:
				assert zone[0] in "+-"
				assert False not in [c in "0123456789" for c in zone[1:]]
				hour, minute = int(zone[1:3]), int(zone[3:])
				assert 0 <= hour <= 12 and 0 <= minute < 60
				offset = (hour * 60 + minute) * 60
				if zone[0] == "+": offset = -offset
				strval = strval[:-5]
			except Exception:
				zone = None
		m = self._re.match(strval)
		if not m: raise ValueError(val)
		allval = m.groups()
		if allval[6] == " " and not human: raise ValueError(val)
		values = allval[:6] + allval[7:12]
		datev = values[::2]
		date = [int(v) if v else 1 for v in datev[:3]] + [int(v) if v else 0 for v in datev[3:]]
		if 0 in date[:3]: raise ValueError(val)
		for iv, mv in zip(date, self._ranges):
			if iv > mv: raise ValueError(val)
		fuzz = list(values[1::2])
		steps = []
		with_steps = False
		for pos, v in enumerate(fuzz):
			if v:
				v = int(v[1:])
				with_steps = True
			steps.append(v)
		parsed = struct_time(date + [0, 0, 0])
		unit = None
		last_fuzz = allval[12]
		if last_fuzz:
			if last_fuzz == "+": raise ValueError(val)
			units = ["Y", "m", "d", "H", "M", "S"]
			if last_fuzz[1] == "-":
				mult = -1
				f = last_fuzz[2:]
			else:
				mult = 1
				f = last_fuzz[1:]
			if f[-1] in units:
				unit = f[-1]
				mults = [12.0, 30.5, 24, 60, 60]
				while unit != units.pop(): mult *= mults.pop()
				f = f[:-1] or "1"
			exact_fuzz = VTfloat(f).exact * mult
			fuzz = int(exact_fuzz)
			if fuzz != exact_fuzz:
				fuzz = float(exact_fuzz)
		else:
			exact_fuzz = fuzz = 0
		if not zone:
			lparsed = localtime(timegm(parsed))
			offset = timegm(parsed) - timegm(lparsed)
		value = timegm(parsed)
		lt = localtime(value + offset)
		lts = "%04d-%02d-%02dT%02d:%02d:%02d" % lt[:6]
		if None in datev:
			valid_steps = datev.index(None)
			lts = lts[:valid_steps * 3 + 1]
			self.__dict__["valid_steps"] = valid_steps
			t2 = self._step_end(parsed)
			implfuzz = t2 - value
		else:
			implfuzz = 0
			self.__dict__["valid_steps"] = 6
		if not unit and implfuzz: fuzz *= implfuzz * 2;
		fuzz += implfuzz
		value += offset
		if implfuzz and not exact_fuzz:
			exact_fuzz = implfuzz
		self.__dict__["_lts"] = lts
		self.__dict__["_fuzz"] = (last_fuzz or "")
		self.__dict__["time"] = parsed
		self.__dict__["_tz"] = offset if zone else None
		self.__dict__["str"] = val.replace(" ", "T")
		self.__dict__["value"] = value
		self.__dict__["exact"] = value
		self.__dict__["fuzz"] = fuzz
		self.__dict__["exact_fuzz"] = exact_fuzz
		self.__dict__["utcoffset"] = offset
		self.__dict__["steps"] = tuple(steps)
		self.__dict__["with_steps"] = with_steps
	
	def localtimestr(self, include_fuzz=True):
		if not include_fuzz: return self._lts
		return self._lts + self._fuzz
	
	@property
	def min(self):
		if self.with_steps:
			min_l = [v + min(s or 0, 0) for v, s in zip(self.time, self.steps + (0,))]
			parsed = struct_time(min_l + [0, 0, 0])
			value = timegm(parsed) + self.utcoffset
		else:
			value = self.value
		return value + min(self.fuzz or 0, 0)
	
	@property
	def max(self):
		if self.with_steps:
			max_l = [v + abs(s or 0) for v, s in zip(self.time, self.steps + (0,))]
			parsed = struct_time(max_l + [0, 0, 0])
			value = timegm(parsed) + self.utcoffset
		else:
			value = self.value
		return value + abs(self.fuzz or 0)
	
	def overlap(self, other):
		if not isinstance(other, VTdatetime):
			raise TypeError("Can only compare to a VTdatetime")
		if self.min > other.max or other.min > self.max:
			return False
		return self._cmp_step(self, other)
	
	def _cmp_step(self, a, b):
		if a.with_steps:
			if self.fuzz < 0:
				nsf = self.fuzz
				psf = nsf * -2
			else:
				psf = self.fuzz
				nsf = 0
			for f in range(5):
				fuzz = a.steps[f] or 0
				for i in range(min(fuzz, 0), abs(fuzz) + 1):
					l = list(self.time)
					l[f] += i
					unixtime = timegm(l)
					fuzz = psf
					if self.valid_steps < 6:
						t2 = self._step_end(l)
						fuzz += t2 - unixtime
					value = unixtime + nsf + self.utcoffset
					a_min = value + min(fuzz, 0)
					a_max = value + abs(fuzz)
					if a is self:
						if self._cmp_step(b, (a_min, a_max)):
							return True
					else:
						if a_min <= b[1] and b[0] <= a_max:
							return True
		else:
			if a is self:
				return self._cmp_step(b, (a.min, a.max))
			else:
				return a.min <= b[1] and b[0] <= a.max
		return False
	
	def _step_end(self, l):
		l = list(l)
		for i in range(self.valid_steps, len(self._ranges)):
			l[i] = self._ranges[i]
		if self.valid_steps == 2: # year + month specified
			# "day 0" of next month
			l[1] += 1
			l[2] = 0
			if l[1] == 13:
				l[1] = 1
				l[0] += 1
		return timegm(l)

class VTgps(ValueType):
	"""Represents the value of a tag with valuetype gps."""
	
	type = "gps"
	_cmp_t = "VTgps"
	
	v = r"(-?\d+(?:\.\d+)?)"
	_re = re.compile(v + r"(\+-?" + v + r")?$")
	del v
	def __init__(self, val, human=False):
		try:
			strval = str(val)
			s = strval.split(",")
			assert len(s) == 2
		except (UnicodeEncodeError, AssertionError):
			raise ValueError(val)
		for n, c in zip(("lat", "lon"), s):
			m = self._re.match(c)
			if not m: raise ValueError(val)
			self.__dict__[n] = Decimal(m.group(1))
			f = 0
			if m.group(2):
				f = Decimal(m.group(2)[1:])
			self.__dict__[n + "_fuzz"] = f
		self.__dict__["str"] = strval
		for n in ("value", "exact"):
			self.__dict__[n] = (self.lat, self.lon)
		for n in ("", "exact_"):
			self.__dict__[n + "fuzz"] = (self.lat_fuzz, self.lon_fuzz)
	
	def __str__(self):
		return self.str
	def format(self):
		return self.str
	
	# @@ Missing: comparison/min/max/overlap

valuetypes = {"string"  : VTstring,
              "word"    : VTword,
              "int"     : VTint,
              "uint"    : VTuint,
              "float"   : VTfloat,
              "f-stop"  : VTf_stop,
              "stop"    : VTstop,
              "datetime": VTdatetime,
              "gps"     : VTgps,
             }
