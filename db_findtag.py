#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

from sys import argv, exit
from dbclient import dbclient

def usage():
	print "Usage:", argv[0], " [-opts] partial-tag-name"
	print "  -f: Fuzzy matching"
	print "  -a: Match anywhere"
	print "  -s: Short listing (just tagnames)"
	exit(1)

def short(tag):
	print tag["name"]

def long(tag):
	names = [tag["name"]] + (tag["alias"] if "alias" in tag else [])
	print " ".join(names), tag["type"], tag["posts"], tag["weak_posts"]

def tagsort(a, b):
	return cmp(a["name"], b["name"])

opts = ""
known_opts = "fas"
part = ""
for a in argv[1:]:
	if a[0] == "-":
		for c in a[1:]:
			if c not in known_opts: usage()
			opts += c
	else:
		if part: usage()
		part = a
if not part: usage()
client = dbclient()
match = "F" if "f" in opts else "E"
where = "P" if "a" in opts else "I"
cmd = match + "A" + where
printer = short if "s" in opts else long
map(printer, sorted(client.find_tags(cmd, part), tagsort))
