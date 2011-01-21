#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

from sys import argv, exit
from dbclient import dbclient

if len(argv) < 2:
	print "Usage:", argv[0], "post-spec tag [tag [...]]"
	exit(1)

client = dbclient()
md5 = client.postspec2md5(argv[1])
if not md5 or not client.get_post(md5):
	print "Post not found"
	exit(1)
full = set()
weak = set()
for tag in argv[2:]:
	s = full
	if tag[0] == "~":
		s = weak
		tag = tag[1:]
	guid = client.find_tag(tag)
	if guid:
		s.add(guid)
	else:
		print "Unknown tag " + tag
if full or weak:
	client.tag_post(md5, full, weak)
