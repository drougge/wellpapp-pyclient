#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

from sys import argv, exit
from dbclient import dbclient
from re import match
from time import strftime, localtime
from os.path import exists
from hashlib import md5
from os import readlink

if len(argv) != 2:
	print "Usage:", argv[0], "filename or tagname or md5"
	exit(1)

client = dbclient()
object = argv[1]
if exists(object):
	object = md5(file(object).read()).hexdigest()

if match(r"^[0-9a-f]{32}$", object):
	post = client.get_post(object)
	if not post:
		print "Post not found"
		exit(1)
	t = localtime(post["created"])
	print object + " created " + strftime("%F %T", t)
	print post["width"], "x", post["height"], post["ext"]
	print "Original file: " + readlink(client.image_path(object))
	print "\n".join(sorted(post["tagname"]))
else:
	data = {"name": "ERROR", "type": "ERROR", "posts": -1, "weak_posts": -1}
	guid = client.find_tag(object, data)
	if not guid:
		print "Tag not found"
		exit(1)
	print "Tag:", data["name"]
	print "GUID:", guid
	print "Type:", data["type"]
	print data["posts"], "posts"
	print data["weak_posts"], "weak posts"
