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

def fmt_tag(prefix, tag):
	if tag.value:
		val = " = " + str(tag.value)
	else:
		val = ""
	return prefix + tag.name + val

def show_post(m, short=False):
	post = client.get_post(m, True, ["tagname", "tagdata", "ext", "created", "width", "height", "source", "title"])
	if not post:
		print "Post not found"
		return 1
	t = localtime(post["created"])
	print m + " created " + strftime("%F %T", t)
	if not short:
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
	if short: return 0
	print "Tags:\n\t",
	tags = [fmt_tag("", t) for t in post["tags"]] + [fmt_tag("~", t) for t in post["weaktags"]]
	print "\n\t".join(map(_tagenc, sorted(tags)))
	tags = [fmt_tag("", t) for t in post["impltags"]] + [fmt_tag("~", t) for t in post["implweaktags"]]
	if tags:
		print "Implied:\n\t",
		print "\n\t".join(map(_tagenc, sorted(tags)))
	rels = client.post_rels(m)
	if rels:
		print "Related posts:\n\t" + "\n\t".join(rels)
	return 0

def show_tag(name, short=False):
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
	if "alias" in data and data["alias"]:
		print "Aliases:", " ".join(map(_tagenc, data["alias"]))
	print "GUID:", guid
	print "Type:", _tagenc(data["type"])
	if "valuetype" in data and data["valuetype"]:
		print "Valuetype:", _tagenc(data["valuetype"])
	if short: return 0
	print data["posts"], "posts"
	print data["weak_posts"], "weak posts"
	show_implies(guid, "Implies:", False)
	show_implies(guid, "Implied by:", True)
	flags = [f for f in data if data[f] is True]
	if flags:
		print "Flags:\n\t", "\n\t".join(flags)
	return 0

if __name__ == "__main__":
	new_argv = []
	short = False
	for a in argv[1:]:
		if a == "-q":
			short = True
		else:
			new_argv.append(a)
	if len(new_argv) < 1:
		print "Usage:", argv[0], "post-spec or tagname [...]"
		exit(1)
	client = dbclient()
	ret = 0
	for object in new_argv:
		object = client.postspec2md5(object, object)
		if match(r"^[0-9a-f]{32}$", object):
			ret |= show_post(object, short)
		else:
			ret |= show_tag(object, short)
		if len(new_argv) > 1: print
	exit(ret)
