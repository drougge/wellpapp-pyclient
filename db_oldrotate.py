#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

import Image
from wellpapp import Client, ExifWrapper
from sys import argv

opts = argv[1] # z for size (fix for rotation), r for rotate (from exif)

client = Client()
fields = ["rotate", "width", "height"]
posts = client._search_post("SPF" + " F".join(fields), fields)
print len(posts), "posts"
count = 0
for post in filter(lambda p: p["rotate"] in (-1, 90, 270), posts):
	m = post["md5"]
	fn = client.image_path(m)
	exif = ExifWrapper(fn)
	rot = exif.rotation()
	did = False
	if rot in (90, 270) and "z" in opts:
		img = Image.open(fn)
		w, h = img.size
		if post["width"] != h:
			client.modify_post(m, width=h, height=w)
			did = True
	if rot != post["rotate"] and "r" in opts:
		client.modify_post(m, rotate=rot)
		did = True
	if did: count += 1
print "Modified", count, "posts"
