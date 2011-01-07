#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

from sys import argv, exit
from dbclient import dbclient
from hashlib import md5
import Image
from cStringIO import StringIO
from pyexiv2 import Image as ExivImage
from os.path import basename, dirname, realpath, exists, islink, join, sep
from os import makedirs, readlink, symlink, unlink, getcwd

if len(argv) < 2:
	print "Usage:", argv[0], "filename [filename [..]]"
	exit(1)

def determine_filetype(data):
	if data[:3] == "\xff\xd8\xff": return "jpeg"
	if data[:4] == "GIF8": return "gif"
	if data[:4] == "\x89PNG": return "png"
	if data[:2] == "BM": return "bmp"
	if data[:3] == "FWS" or data[:3] == "CWS": return "swf"

def imagetime(fn):
	img = ExivImage(fn)
	img.readMetadata()
	return img['Exif.Image.DateTime']

def save_thumb(m, size, img):
	fn = client.thumb_path(m, size)
	make_pdirs(fn)
	img.save(fn, "JPEG", quality=60)

def save_thumbs(m, img):
	w, h = img.size
	if img.mode not in ("RGB", "L", "1"):
		img = img.convert("RGB")
	for z in map(int, client.cfg.thumb_sizes.split()):
		t = img.copy()
		if w > z or h > z:
			t.thumbnail((z, z), Image.ANTIALIAS)
		save_thumb(m, z, t)

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

client = dbclient()
for fn in argv[1:]:
	fn = realpath(fn)
	data = file(fn).read()
	m = md5(data).hexdigest()
	ft = determine_filetype(data)
	assert ft
	post = client.get_post(m)
	p = client.image_path(m)
	if exists(p):
		ld = readlink(p)
		if fn != ld:
			print "Not updating", m, fn
	else:
		if islink(p):
			print "Updating", m, fn
			unlink(p)
		make_pdirs(p)
		symlink(fn, p)
	if not post:
		datafh = StringIO(data)
		img = Image.open(datafh)
		save_thumbs(m, img)
		w, h = img.size
		args = {"md5": m, "width": w, "height": h, "filetype": ft}
		try:
			datafh.seek(0)
			args["date"] = imagetime(fn)
		except Exception:
			pass
		client.add_post(**args)
	full = set()
	weak = set()
	post = client.get_post(m)
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
