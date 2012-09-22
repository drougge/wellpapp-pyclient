#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

from sys import argv, exit
from wellpapp import Client

if len(argv) != 3:
	print "Usage:", argv[0], "post-spec rotation"
	exit(1)

spec, new_r = argv[1:]
client = Client()
md5 = client.postspec2md5(spec)
post = None
if md5: post = client.get_post(md5, wanted = ["rotate", "ext", "width", "height"])
if not post:
	print "Post not found"
	exit(1)

r = int(post.get("rotate", 0))
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

client.save_thumbs(md5, None, post.ext, new_r, True)
client.modify_post(md5, **props)
