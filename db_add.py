#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

from hashlib import md5
import Image
from cStringIO import StringIO
from pyexiv2 import Image as ExivImage
from os.path import basename, dirname, realpath, exists, lexists, join, sep
from os import readlink, symlink, unlink, getcwd
from dbclient import make_pdirs

def determine_filetype(data):
	if data[:3] == "\xff\xd8\xff": return "jpeg"
	if data[:4] == "GIF8": return "gif"
	if data[:4] == "\x89PNG": return "png"
	if data[:2] == "BM": return "bmp"
	if data[:3] == "FWS" or data[:3] == "CWS": return "swf"

def needs_thumbs(m, ft):
	if force_thumbs: return True
	jpeg_fns, png_fns = client.thumb_fns(m, ft)
	for fn, z in jpeg_fns + png_fns:
		if not exists(fn): return True

def exif2rotation(exif):
	if not exif or "Exif.Image.Orientation" not in exif.exifKeys(): return -1
	o = exif["Exif.Image.Orientation"]
	orient = {1: 0, 3: 180, 6: 90, 8: 270}
	if o not in orient: return -1
	return orient[o]

def exif2tags(exif, tags):
	if not exif: return
	cfg = client.cfg
	keys = exif.exifKeys()
	if "lenstags" in cfg:
		lenstags = cfg.lenstags.split()
		for lt in lenstags:
			if lt in keys:
				v = exif[lt]
				if type(v) is tuple:
					v = " ".join([str(e) for e in v])
				lt = "lens:" + lt + ":" + v
				if lt in cfg:
					tags.add(cfg[lt])
	if "Exif.Image.Make" in keys and "Exif.Image.Model" in keys:
		make = exif["Exif.Image.Make"].strip()
		model = exif["Exif.Image.Model"].strip()
		cam = "camera:" + make + ":" + model
		if cam in cfg:
			tags.add(cfg[cam])

class tagset(set):
	def add(self, t):
		base_t = t
		prefix = ""
		if t[0] in "~-":
			base_t = t[1:]
			prefix = t[0]
		guid = client.find_tag(base_t)
		if not guid:
			print "Unknown tag " + base_t
			return
		for check_prefix in "", "~":
			check_t = check_prefix + guid
			if check_t in self:
				self.remove(check_t)
		if prefix != "-": set.add(self, prefix + guid)
	
	def update(self, l):
		map(self.add, l)

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
				record_filename(m, fn)
				if not quiet:
					print "Not updating", m, fn
		else:
			record_filename(m, ld)
			if not quiet: print "Updating", m, fn
			unlink(p)
	if not lexists(p):
		make_pdirs(p)
		symlink(fn, p)
	if not post or needs_thumbs(m, ft):
		datafh = StringIO(data)
		img = Image.open(datafh)
	try:
		exif = ExivImage(fn)
		exif.readMetadata()
	except Exception:
		exif = None
	if not post:
		w, h = img.size
		rot = exif2rotation(exif)
		if rot in (90, 270): w, h = h, w
		args = {"md5": m, "width": w, "height": h, "ext": ft}
		if rot >= 0: args["rotate"] = rot
		try:
			date = exif['Exif.Image.DateTime']
			if isinstance(date, basestring): date = int(date)
			args["imgdate"] = date
		except Exception:
			pass
		client.add_post(**args)
	if needs_thumbs(m, ft):
		rot = exif2rotation(exif)
		client.save_thumbs(m, img, ft, rot, force_thumbs)
	full = set()
	weak = set()
	post = client.get_post(m, True)
	posttags = tagset()
	posttags.update(post["tagname"])
	filetags = find_tags(fn)
	exif2tags(exif, filetags)
	for guid in filetags.difference(posttags):
		if guid[0] == "~":
			weak.add(guid[1:])
		else:
			full.add(guid)
	if full or weak:
		if no_tagging:
			full = [client.get_tag(g).name for g in full]
			weak = ["~" + client.get_tag(g).name for g in weak]
			print "Would have tagged " + m + ": " + " ".join(full + weak)
		else:
			client.tag_post(m, full, weak)

def usage():
	print "Usage:", argv[0], "[-v] [-q] [-f] [-n] filename [filename [..]]"
	print "\t-v Verbose"
	print "\t-q Quiet"
	print "\t-f Force thumbnail regeneration"
	print "\t-n No tagging (prints what would have been tagged)"
	exit(1)

if __name__ == '__main__':
	from sys import argv, exit
	from dbclient import dbclient
	if len(argv) < 2: usage()
	a = 1
	switches = ("-v", "-q", "-f", "-h", "-n")
	quiet = False
	verbose = False
	force_thumbs = False
	no_tagging = False
	while argv[a] in switches:
		if argv[a] == "-q":
			quiet = True
		elif argv[a] == "-v":
			verbose = True
		elif argv[a] == "-f":
			force_thumbs = True
		elif argv[a] == "-n":
			no_tagging = True
		else:
			usage()
		a += 1
		if len(argv) == a: usage()
	client = dbclient()
	client.begin_transaction()
	map(add_image, argv[a:])
	client.end_transaction()
