#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

from sys import argv, exit
from dbclient import dbclient
import db_add
from os.path import exists
from os import unlink, stat
import Image

if len(argv) != 3:
	print "Usage:", argv[0], "post-spec rotation"
	exit(1)

spec, new_r = argv[1:]
client = dbclient()
md5 = client.postspec2md5(spec)
post = None
if md5: post = client.get_post(md5, wanted = ["rotate", "ext", "width", "height"])
if not post:
	print "Post not found"
	exit(1)

r = post["rotate"]
if r < 0: r = 0
new_r = int(new_r)
good_r = (0, 90, 180, 270)
if r not in good_r or new_r not in good_r:
	print "Can only handle 0, 90, 180 or 270 degrees rotation"
	exit(1)
diff = new_r - r
if diff < 0: diff += 360
if diff == 0:
	exit(0)
props = {"rotate": new_r}
if diff in (90, 270):
	props["width"], props["height"] = post["height"], post["width"]

db_add.client = client
db_add.force_thumbs = True
fn = client.image_path(md5)
mtime = stat(fn).st_mtime
img = Image.open(fn)
if new_r:
	# PIL rotates CCW
	rotation = {90: Image.ROTATE_270, 180: Image.ROTATE_180, 270: Image.ROTATE_90}
	img = img.transpose(rotation[new_r])
db_add.save_thumbs(md5, post["ext"], mtime, img)
client.modify_post(md5, **props)
