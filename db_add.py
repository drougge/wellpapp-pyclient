#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

from hashlib import md5
import Image
from PIL import PngImagePlugin
from cStringIO import StringIO
from pyexiv2 import Image as ExivImage
from os.path import basename, dirname, realpath, exists, lexists, join, sep
from os import makedirs, readlink, symlink, unlink, getcwd, stat

def determine_filetype(data):
	if data[:3] == "\xff\xd8\xff": return "jpeg"
	if data[:4] == "GIF8": return "gif"
	if data[:4] == "\x89PNG": return "png"
	if data[:2] == "BM": return "bmp"
	if data[:3] == "FWS" or data[:3] == "CWS": return "swf"

def thumb_fns(m, ft):
	sizes = client.cfg.thumb_sizes.split()
	jpeg_fns = map(lambda z: (client.thumb_path(m, int(z)), int(z)), sizes)
	png_fns = map(lambda n, z: (client.pngthumb_path(m, ft, n), z),
	              ("normal", "large"), (128, 256))
	return jpeg_fns, png_fns

def save_thumbs(m, ft, mtime, img):
	w, h = img.size
	if img.mode not in ("RGB", "L", "1"):
		img = img.convert("RGB")
	jpeg_fns, png_fns = thumb_fns(m, ft)
	jpeg_opts = {"format": "JPEG", "quality": 95, "optimize": 1}
	meta = PngImagePlugin.PngInfo()
	meta.add_text("Thumb::URI", m + "." + ft, 0)
	meta.add_text("Thumb::MTime", str(int(mtime)), 0)
	png_opts = {"format": "PNG", "pnginfo": meta}
	jpeg = map(lambda t: (t[0], t[1], jpeg_opts), jpeg_fns)
	png = map(lambda t: (t[0], t[1], png_opts), png_fns)
	z = max(map(lambda d: d[1], jpeg + png)) * 2
	if w > z or h > z:
		img = img.copy()
		img.thumbnail((z, z), Image.ANTIALIAS)
	for fn, z, opts in jpeg + png:
		if force_thumbs or not exists(fn):
			t = img.copy()
			if w > z or h > z:
				t.thumbnail((z, z), Image.ANTIALIAS)
			make_pdirs(fn)
			t.save(fn, **opts)

def needs_thumbs(m, ft):
	if force_thumbs: return True
	jpeg_fns, png_fns = thumb_fns(m, ft)
	for fn, z in jpeg_fns + png_fns:
		if not exists(fn): return True

def exif2rotation(exif):
	if "Exif.Image.Orientation" not in exif.exifKeys(): return -1
	o = exif["Exif.Image.Orientation"]
	orient = {1: 0, 3: 180, 6: 90, 8: 270}
	if o not in orient: return -1
	return orient[o]

def rotate_image(img, exif):
	rot = exif2rotation(exif)
	rotation = {90: Image.ROTATE_90, 180: Image.ROTATE_180, 270: Image.ROTATE_270}
	if rot not in rotation: return img
	return img.transpose(rotation[rot])

def make_pdirs(fn):
	dn = dirname(fn)
	if not exists(dn): makedirs(dn)

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
		if exists(p):
			ld = readlink(p)
			if fn != ld and not quiet:
				print "Not updating", m, fn
		else:
			if not quiet: print "Updating", m, fn
			unlink(p)
	if not lexists(p):
		make_pdirs(p)
		symlink(fn, p)
	if not post or needs_thumbs(m, ft):
		datafh = StringIO(data)
		img = Image.open(datafh)
		exif = ExivImage(fn)
		exif.readMetadata()
	if not post:
		w, h = img.size
		args = {"md5": m, "width": w, "height": h, "filetype": ft}
		rot = exif2rotation(exif)
		if rot >= 0: args["rotate"] = rot
		try:
			args["image_date"] = exif['Exif.Image.DateTime']
		except Exception:
			pass
		client.add_post(**args)
	if needs_thumbs(m, ft):
		img = rotate_image(img, exif)
		mtime = stat(fn).st_mtime
		save_thumbs(m, ft, mtime, img)
	full = set()
	weak = set()
	post = client.get_post(m, True)
	posttags = tagset()
	posttags.update(post["tagname"])
	filetags = find_tags(fn)
	for guid in filetags.difference(posttags):
		if guid[0] == "~":
			weak.add(guid[1:])
		else:
			full.add(guid)
	if full or weak:
		client.tag_post(m, full, weak)

def usage():
	print "Usage:", argv[0], "[-v] [-q] [-f] filename [filename [..]]"
	exit(1)

if __name__ == '__main__':
	from sys import argv, exit
	from dbclient import dbclient
	if len(argv) < 2: usage()
	a = 1
	switches = ("-v", "-q", "-f", "-h")
	quiet = False
	verbose = False
	force_thumbs = False
	while argv[a] in switches:
		if argv[a] == "-q":
			quiet = True
		elif argv[a] == "-v":
			verbose = True
		elif argv[a] == "-f":
			force_thumbs = True
		else:
			usage()
		a += 1
		if len(argv) == a: usage()
	client = dbclient()
	client.begin_transaction()
	map(add_image, argv[a:])
	client.end_transaction()
