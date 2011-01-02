#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

from sys import argv, exit
from dbclient import dbclient
from hashlib import md5
import Image
from cStringIO import StringIO
from pyexiv2 import Image as ExivImage
from os.path import basename, dirname, realpath, exists, islink
from os import makedirs, readlink, symlink, unlink

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

def save_thumb(m, img):
	fn = client.thumb_path(m)
	make_pdirs(fn)
	img.save(fn, "JPEG")

def make_pdirs(fn):
	dn = dirname(fn)
	if not exists(dn): makedirs(dn)

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
		w, h = img.size
		z = int(client.cfg.thumb_size)
		if w > z or h > z:
			img.thumbnail((z, z), Image.ANTIALIAS)
		save_thumb(m, img)
		args = {"md5": m, "width": w, "height": h, "filetype": ft}
		try:
			datafh.seek(0)
			args["date"] = imagetime(fn)
		except Exception:
			pass
		client.add_post(**args)
	full = []
	weak = []
	post = client.get_post(m)
	posttags = map(lambda t: t[1:] if t[0] == "~" else t, post["tagguid"])
	for tag in basename(fn).split()[:-1]:
		if tag[0] == "~":
			tags = weak
			tag = tag[1:]
		else:
			tags = full
		t = client.find_tag(tag)
		if t:
			if t not in posttags: tags.append(t)
		else:
			print "Unknown tag " + tag
	if full or weak:
		client.tag_post(m, full, weak)
