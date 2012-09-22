#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

from os import walk, readlink, stat
from os.path import join
from sys import argv, exit
from dbutil import identify_raw, RawWrapper

def add(m, fn):
	try:
		dest = readlink(fn)
		s = stat(dest)
		z = s.st_size
		mt = int(s.st_mtime)
		fh = file(dest, "rb")
		if identify_raw(fh):
			fh.seek(0)
			jfh = RawWrapper(fh, True)
			jfh.seek(0, 2)
			jz = jfh.tell()
			jfh.close()
			l = "1 %s %d %d %d %s\n" % (m, z, mt, jz, dest)
		else:
			l = "0 %s %d %d %s\n" % (m, z, mt, dest)
		fh.close()
		res.write(l)
	except Exception:
		print m, "failed"

if len(argv) < 2 or argv[1][0] == "-":
	print "Usage: " + argv[0] + " . or raw or post-spec [post-spec [..]]"
	print "\t.         - Regenerate full cache"
	print "\traw       - Regenerate cache for all raw images"
	print "\tpost-spec - add post-spec to cache"
	print "Run in image_base"
	exit(1)

res = open("cache", "a")
if argv[1:] == ["."]:
	for dp, dns, fns in walk("."):
		for n in [n for n in fns if len(n) == 32]:
			add(n, join(dp, n))
elif argv[1:] == ["raw"]:
	from dbclient import dbclient
	from dbutil import raw_exts
	client = dbclient()
	ms = []
	for ext in raw_exts:
		p = client.search_post(guids=[("aaaaaa-aaaacr-faketg-FLekst", ext)])
		ms += [p.md5 for p in p[0]]
	for m in ms:
		add(m, client.image_path(m))
else:
	from dbclient import dbclient
	client = dbclient()
	for n in argv[1:]:
		m = client.postspec2md5(n)
		if m:
			add(m, client.image_path(m))
		else:
			print "Failed to convert " + n + " to post"
res.close()
