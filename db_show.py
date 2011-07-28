#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

from sys import argv, exit, stdout
from dbclient import dbclient
from re import match
from time import strftime, localtime
from os.path import exists
from hashlib import md5
from os import readlink

def _tagenc(t):
	return t.encode(stdout.encoding or "ascii", "replace")

def implfmt(impl):
	guid, prio = impl
	data = client.get_tag(guid, with_prefix=True)
	return "\n\t" + _tagenc(data["name"]) + " " + str(prio)

def show_implies(guid, heading, reverse):
	impl = client.tag_implies(guid, reverse)
	if impl: print heading + "".join(map(implfmt, impl))

def show_post(m):
	post = client.get_post(m, True, ["tagname", "ext", "created", "width", "height", "source", "title"])
	if not post:
		print "Post not found"
		return 1
	t = localtime(post["created"])
	print m + " created " + strftime("%F %T", t)
	print post["width"], "x", post["height"], post["ext"]
	for field in ("title", "source"):
		if field in post:
			print field.title() + ": " + _tagenc(post[field])
	try:
		path = readlink(client.image_path(m))
		if not exists(path):
			path += " (MISSING)"
	except Exception:
		path = "MISSING"
	print "Original file: " + path
	print "Tags:\n\t",
	print "\n\t".join(map(_tagenc, sorted(post["tagname"])))
	if post["impltagname"]:
		print "Implied:\n\t",
		print "\n\t".join(map(_tagenc, sorted(post["impltagname"])))
	rels = client.post_rels(m)
	if rels:
		print "Related posts:\n\t" + "\n\t".join(rels)
	return 0

def show_tag(name):
	guid = client.find_tag(name)
	if not guid and match(r"(?:\w{6}-){3}\w{6}", name):
		guid = name
	if not guid:
		print "Tag not found"
		return 1
	data = client.get_tag(guid)
	if not data:
		print "Tag not found"
		return 1
	print "Tag:", _tagenc(data["name"])
	if "alias" in data: print "Aliases:", " ".join(map(_tagenc, data["alias"]))
	print "GUID:", guid
	print "Type:", _tagenc(data["type"])
	print data["posts"], "posts"
	print data["weak_posts"], "weak posts"
	show_implies(guid, "Implies:", False)
	show_implies(guid, "Implied by:", True)
	flags = [f for f in data if data[f] is True]
	if flags:
		print "Flags:\n\t", "\n\t".join(flags)
	return 0

if __name__ == "__main__":
	if len(argv) < 2:
		print "Usage:", argv[0], "post-spec or tagname [...]"
		exit(1)
	client = dbclient()
	object = client.postspec2md5(argv[1], argv[1])
	ret = 0
	for object in argv[1:]:
		object = client.postspec2md5(object, object)
		if match(r"^[0-9a-f]{32}$", object):
			ret |= show_post(object)
		else:
			ret |= show_tag(object)
		if len(argv) > 2: print
	exit(ret)
