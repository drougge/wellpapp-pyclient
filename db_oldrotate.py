#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

from pyexiv2 import Image as ExivImage
from db_add import exif2rotation
from dbclient import dbclient

client = dbclient()
posts = client._search_post("SPFrotate", ["rotate"])
print len(posts), "posts"
for post in posts:
	if post["rotate"] == -1:
		m = post["md5"]
		exif = ExivImage(client.image_path(m))
		exif.readMetadata()
		rot = exif2rotation(exif)
		if rot >= 0:
			client.modify_post(m, rotate=rot)
