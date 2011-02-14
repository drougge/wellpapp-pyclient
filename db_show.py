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
	print "Usage:", argv[0], "post-spec or tagname"
	exit(1)

def implfmt(impl):
	guid, prio = impl
	data = client.get_tag(guid, with_prefix=True)
	return "\n\t" + data["name"] + " " + str(prio)

def show_implies(guid, heading, reverse):
	impl = client.tag_implies(guid, reverse)
	if impl: print heading + "".join(map(implfmt, impl))

client = dbclient()
object = client.postspec2md5(argv[1], argv[1])

if match(r"^[0-9a-f]{32}$", object):
	post = client.get_post(object, True)
	if not post:
		print "Post not found"
		exit(1)
	t = localtime(post["created"])
	print object + " created " + strftime("%F %T", t)
	print post["width"], "x", post["height"], post["ext"]
	try:
		path = readlink(client.image_path(object))
		if not exists(path):
			path += " (MISSING)"
	except Exception:
		path = "MISSING"
	print "Original file: " + path
	print "Tags:\n\t",
	print "\n\t".join(sorted(post["tagname"]))
	if post["impltagname"]:
		print "Implied:\n\t",
		print "\n\t".join(sorted(post["impltagname"]))
	rels = client.post_rels(object)
	if rels:
		print "Related posts:\n\t" + "\n\t".join(rels)
else:
	guid = client.find_tag(object)
	if not guid:
		print "Tag not found"
		exit(1)
	data = client.get_tag(guid)
	print "Tag:", data["name"]
	if "alias" in data: print "Aliases:", " ".join(data["alias"])
	print "GUID:", guid
	print "Type:", data["type"]
	print data["posts"], "posts"
	print data["weak_posts"], "weak posts"
	show_implies(guid, "Implies:", False)
	show_implies(guid, "Implied by:", True)
