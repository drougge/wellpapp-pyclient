#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

from os import walk, readlink, stat
from os.path import join
from sys import argv, exit

def add(fn):
	try:
		dest = readlink(fn)
		s = stat(dest)
		z = s.st_size
		mt = int(s.st_mtime)
		l = "0 %s %d %d %s\n" % (n, z, mt, dest)
		res.write(l)
	except Exception:
		print n, "failed"

if len(argv) < 2 or argv[1][0] == "-":
	print "Usage: " + argv[0] + " . or post-spec [post-spec [..]]"
	print "\t.         - Regenerate full cache"
	print "\tpost-spec - add post-spec to cache"
	print "Run in image_base"
	exit(1)

if argv[1:] == ["."]:
	res = open("cache", "a")
	for dp, dns, fns in walk("."):
		for n in [n for n in fns if len(n) == 32]:
			add(join(dp, n))
else:
	res = open("cache", "a")
	from dbclient import dbclient
	client = dbclient()
	for n in argv[1:]:
		m = client.postspec2md5(n)
		if m:
			add(client.image_path(m))
		else:
			print "Failed to convert " + n + " to post"
res.close()
