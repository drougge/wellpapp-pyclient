#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

from hashlib import md5
import Image
from cStringIO import StringIO
from os.path import basename, dirname, realpath, exists, lexists, join, sep
from os import readlink, symlink, unlink, getcwd, stat
from dbclient import dbclient, VTstring
from dbutil import make_pdirs, raw_wrapper, identify_raw, exif_wrapper
from time import gmtime, strftime

def determine_filetype(data):
	if data[:3] == "\xff\xd8\xff": return "jpeg"
	if data[:4] == "GIF8": return "gif"
	if data[:4] == "\x89PNG": return "png"
	if data[:2] == "BM": return "bmp"
	if data[:3] == "FWS" or data[:3] == "CWS": return "swf"
	if data[:4] in ("MM\0*", "II*\0"):
		return identify_raw(StringIO(data))

def needs_thumbs(m, ft):
	if force_thumbs: return True
	jpeg_fns, png_fns = client.thumb_fns(m, ft)
	for fn, z in jpeg_fns + png_fns:
		if not exists(fn): return True

def exif2rotation(exif):
	if "Exif.Image.Orientation" not in exif: return -1
	o = exif["Exif.Image.Orientation"]
	orient = {1: 0, 3: 180, 6: 90, 8: 270}
	if o not in orient: return -1
	return orient[o]

def exif2tags(exif, tags):
	cfg = client.cfg
	if "lenstags" in cfg:
		lenstags = cfg.lenstags.split()
		for lt in lenstags:
			if lt in exif:
				v = exif[lt]
				if type(v) is tuple:
					v = " ".join([str(e) for e in v])
				lt = "lens:" + lt + ":" + v
				if lt in cfg:
					tags.add_spec(cfg[lt])
	try:
		make = exif["Exif.Image.Make"].strip()
		model = exif["Exif.Image.Model"].strip()
		cam = "camera:" + make + ":" + model
		if cam in cfg:
			tags.add_spec(cfg[cam])
	except Exception:
		pass
	if "set_tags" in cfg:
		for st in cfg.set_tags.split():
			tn, et = st.split("=", 1)
			if et in exif:
				v = exif[et]
				tags.add_spec(tn + "=" + str(exif[et]))

class tagset(set):
	def add(self, t):
		guid, val = t
		prefix = ""
		if guid[0] in "~-":
			prefix = guid[0]
			guid = guid[1:]
		chk = (guid, "~" + guid)
		rem = None
		for v in self:
			if v[0] in chk: rem = v
		if rem: self.remove(rem)
		if prefix != "-": set.add(self, (prefix + guid, val))
	
	def add_spec(self, s):
		t = client.parse_tag(s)
		if t:
			self.add(t)
		else:
			print "Unknown tag " + s
	
	def update(self, l):
		[self.add_spec(s) for s in l]
	
	def update_tags(self, l, prefix=""):
		[self.add((prefix + t.guid, t.value)) for t in l]

def find_tags(fn):
	path = "/"
	tags = tagset()
	for dir in dirname(fn).split(sep):
		path = join(path, dir)
		TAGS = join(path, "TAGS")
		if exists(TAGS):
			tags.update(file(TAGS).readline().split())
	tags.update(basename(fn).split()[:-1])
	return tags

def record_filename(m, fn):
	dn = client.image_dir(m)
	rec_fn = join(dn, "FILENAMES")
	known = {}
	if exists(rec_fn):
		for line in file(rec_fn):
			r_m, r_fn = line[:-1].split(" ", 1)
			known.setdefault(r_m, []).append(r_fn)
	if m not in known or fn not in known[m]:
		open(rec_fn, "a").write(m + " " + fn + "\n")

def generate_cache(m, fn):
	cache_fn = client.cfg.image_base + "/cache"
	if exists(cache_fn):
		fh = open(cache_fn, "a")
		s = stat(fn)
		z = s.st_size
		mt = int(s.st_mtime)
		l = "0 %s %d %d %s\n" % (m, z, mt, fn)
		fh.write(l)
		fh.close()

def fmt_tagvalue(v):
	if not v: return ""
	if isinstance(v, VTstring):
		return "=" + repr(v.str)
	else:
		return "=" + v.str

def add_image(fn):
	if verbose: print fn
	fn = realpath(fn)
	data = file(fn).read()
	m = md5(data).hexdigest()
	ft = determine_filetype(data)
	assert ft
	post = client.get_post(m, True)
	p = client.image_path(m)
	if lexists(p):
		ld = readlink(p)
		if exists(p):
			if fn != ld:
				if not dummy: record_filename(m, fn)
				if not quiet:
					print "Not updating", m, fn
		else:
			if dummy:
				if not quiet: print "Would have updated", m, fn
			else:
				record_filename(m, ld)
				if not quiet: print "Updating", m, fn
				unlink(p)
	if not lexists(p) and not dummy:
		make_pdirs(p)
		symlink(fn, p)
		generate_cache(m, fn)
	if not post or needs_thumbs(m, ft):
		datafh = raw_wrapper(StringIO(data))
		img = Image.open(datafh)
	exif = exif_wrapper(fn)
	if not post:
		w, h = img.size
		rot = exif2rotation(exif)
		if rot in (90, 270): w, h = h, w
		args = {"md5": m, "width": w, "height": h, "ext": ft}
		if rot >= 0: args["rotate"] = rot
		date = exif.date()
		if date:
			date = strftime("%Y-%m-%dT%H:%M:%SZ", gmtime(date))
			args["imgdate"] = date
		if dummy:
			print "Would have created post " + m
		else:
			client.add_post(**args)
	if needs_thumbs(m, ft):
		if dummy:
			print "Would have generated thumbs for " + m
		else:
			rot = exif2rotation(exif)
			client.save_thumbs(m, img, ft, rot, force_thumbs)
	full = tagset()
	weak = tagset()
	post = client.get_post(m, True)
	posttags = tagset()
	if post:
		posttags.update_tags(post["tags"])
		posttags.update_tags(post["weaktags"], "~")
	filetags = find_tags(fn)
	exif2tags(exif, filetags)
	for guid, val in filetags.difference(posttags):
		if guid[0] == "~":
			weak.add((guid[1:], val))
		else:
			full.add((guid, val))
	if full or weak:
		if no_tagging or dummy:
			full = [client.get_tag(g).name + fmt_tagvalue(v) for g, v in full]
			weak = ["~" + client.get_tag(g).name + fmt_tagvalue(v) for g, v in weak]
			print "Would have tagged " + m + " " + " ".join(full + weak)
		else:
			client.tag_post(m, full, weak)

def usage():
	print "Usage:", argv[0], "[-v] [-q] [-f] [-n] [-d] filename [filename [..]]"
	print "\t-v Verbose"
	print "\t-q Quiet"
	print "\t-f Force thumbnail regeneration"
	print "\t-n No tagging (prints what would have been tagged)"
	print "\t-d Dummy, only print what would be done"
	exit(1)

if __name__ == '__main__':
	from sys import argv, exit
	if len(argv) < 2: usage()
	a = 1
	switches = ("-v", "-q", "-f", "-h", "-n", "-d")
	quiet = False
	verbose = False
	force_thumbs = False
	no_tagging = False
	dummy = False
	while argv[a] in switches:
		if argv[a] == "-q":
			quiet = True
		elif argv[a] == "-v":
			verbose = True
		elif argv[a] == "-f":
			force_thumbs = True
		elif argv[a] == "-n":
			no_tagging = True
		elif argv[a] == "-d":
			dummy = True
		else:
			usage()
		a += 1
		if len(argv) == a: usage()
	client = dbclient()
	client.begin_transaction()
	map(add_image, argv[a:])
	client.end_transaction()
